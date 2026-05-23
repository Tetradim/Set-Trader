"""Broker/internal reconciliation API routes backed by MongoDB."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo import ReturnDocument
from pydantic import BaseModel

import deps
from auth import Role, TokenData, get_current_user, require_roles


router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


class ReconciliationRecord(BaseModel):
    record_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    broker: str
    internal_timestamp: str
    broker_timestamp: str
    status: str
    break_reason: Optional[str] = None
    pnl: Optional[float] = None
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None


class ReconciliationSummary(BaseModel):
    total_records: int
    matched: int
    breaks: int
    pending: int
    total_pnl: float
    last_sync: str


class SignoffRequest(BaseModel):
    timestamp: str


def _record_filter(status_value: Optional[str] = None, symbol: Optional[str] = None) -> dict:
    query = {}
    if status_value:
        query["status"] = status_value
    if symbol:
        query["symbol"] = symbol.upper()
    return query


@router.get("/records", response_model=list[ReconciliationRecord])
async def get_records(
    limit: int = Query(100, ge=1, le=1000),
    status_value: Optional[str] = Query(None, alias="status"),
    symbol: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get reconciliation records."""
    return await deps.db.reconciliation_records.find(
        _record_filter(status_value, symbol),
        {"_id": 0},
    ).sort("broker_timestamp", -1).to_list(limit)


@router.get("/summary", response_model=ReconciliationSummary)
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    """Get reconciliation summary."""
    records = await deps.db.reconciliation_records.find({}, {"_id": 0}).to_list(5000)
    matched = sum(1 for record in records if record.get("status") == "matched")
    breaks = sum(1 for record in records if record.get("status") == "break")
    pending = sum(1 for record in records if record.get("status") == "pending")
    total_pnl = sum(float(record.get("pnl", 0) or 0) for record in records)
    last_sync = max([record.get("broker_timestamp", "") for record in records], default="")
    return ReconciliationSummary(
        total_records=len(records),
        matched=matched,
        breaks=breaks,
        pending=pending,
        total_pnl=round(total_pnl, 2),
        last_sync=last_sync,
    )


@router.post("/signoff")
async def eod_signoff(
    request: SignoffRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER])),
):
    """Perform EOD sign-off when no unresolved breaks remain."""
    break_count = await deps.db.reconciliation_records.count_documents({"status": "break"})
    if break_count:
        return {
            "success": False,
            "message": f"Cannot sign off with {break_count} unresolved breaks",
            "breaks": break_count,
        }

    records = await deps.db.reconciliation_records.find({}, {"_id": 0}).to_list(5000)
    signoff = {
        "signoff_id": f"SO{await deps.db.reconciliation_signoffs.count_documents({}) + 1:06d}",
        "timestamp": request.timestamp,
        "user_id": current_user.sub,
        "username": current_user.username,
        "record_count": len(records),
        "total_pnl": round(sum(float(record.get("pnl", 0) or 0) for record in records), 2),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await deps.db.reconciliation_signoffs.insert_one(signoff)
    return {"success": True, "message": "EOD sign-off completed", "signoff": signoff}


@router.get("/signoffs")
async def get_signoffs(current_user: TokenData = Depends(get_current_user)):
    """Get past sign-offs."""
    signoffs = await deps.db.reconciliation_signoffs.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"signoffs": signoffs}


@router.post("/resolve-break/{record_id}")
async def resolve_break(
    record_id: str,
    resolution: str,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER])),
):
    """Resolve a reconciliation break."""
    record = await deps.db.reconciliation_records.find_one_and_update(
        {"record_id": record_id},
        {
            "$set": {
                "status": "resolved",
                "resolution": resolution,
                "resolved_by": current_user.sub,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        projection={"_id": 0},
        return_document=ReturnDocument.AFTER,
    )
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"success": True, "record": record}


async def add_reconciliation_record(record: dict):
    """Add a reconciliation record from trading engine integration."""
    doc = {**record}
    doc.setdefault("record_id", f"REC{await deps.db.reconciliation_records.count_documents({}) + 1:06d}")
    await deps.db.reconciliation_records.update_one({"record_id": doc["record_id"]}, {"$set": doc}, upsert=True)
    return doc


async def sync_broker_statements(broker: str, statements: list):
    """Sync broker statements and mark matched or broken records."""
    results = []
    for statement in statements:
        matching = await deps.db.reconciliation_records.find_one({
            "symbol": statement["symbol"],
            "side": statement["side"],
            "broker": broker,
            "status": "pending",
        })

        if matching:
            price_diff = abs(float(matching["price"]) - float(statement["price"]))
            qty_diff = abs(int(matching["quantity"]) - int(statement["quantity"]))
            time_diff = abs(
                datetime.fromisoformat(matching["internal_timestamp"].replace("Z", "+00:00"))
                - datetime.fromisoformat(statement["timestamp"].replace("Z", "+00:00"))
            ).total_seconds()

            updates = {"broker_timestamp": statement["timestamp"]}
            if price_diff > 0.01 or qty_diff > 0 or time_diff > 5:
                updates.update({
                    "status": "break",
                    "break_reason": f"Price: {price_diff}, Qty: {qty_diff}, Time: {time_diff}s",
                })
            else:
                updates["status"] = "matched"
            await deps.db.reconciliation_records.update_one({"record_id": matching["record_id"]}, {"$set": updates})
            results.append({**matching, **updates})
            continue

        orphan = {
            "record_id": f"REC{await deps.db.reconciliation_records.count_documents({}) + 1:06d}",
            "symbol": statement["symbol"],
            "side": statement["side"],
            "quantity": statement["quantity"],
            "price": statement["price"],
            "broker": broker,
            "internal_timestamp": statement["timestamp"],
            "broker_timestamp": statement["timestamp"],
            "status": "break",
            "break_reason": "No matching internal record",
        }
        await deps.db.reconciliation_records.insert_one(orphan)
        results.append(orphan)
    return results


__all__ = ["router", "add_reconciliation_record", "sync_broker_statements"]
