"""Reconciliation API routes.

Provides endpoints for broker/internal reconciliation, break detection, and EOD sign-off.
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth import get_current_user, TokenData, require_roles, Role


router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])


# In-memory storage (replace with database in production)
_records_db = []
_signoffs = []


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


class ReconciliationSummary(BaseModel):
    total_records: int
    matched: int
    breaks: int
    pending: int
    total_pnl: float
    last_sync: str


class SignoffRequest(BaseModel):
    timestamp: str


@router.get("/records", response_model=List[ReconciliationRecord])
async def get_records(
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    current_user: TokenData = Depends(get_current_user)
):
    """Get reconciliation records."""
    records = _records_db
    
    if status:
        records = [r for r in records if r["status"] == status]
    if symbol:
        records = [r for r in records if r["symbol"] == symbol]
    
    return records[:limit]


@router.get("/summary", response_model=ReconciliationSummary)
async def get_summary(
    current_user: TokenData = Depends(get_current_user)
):
    """Get reconciliation summary."""
    records = _records_db
    
    matched = len([r for r in records if r["status"] == "matched"])
    breaks = len([r for r in records if r["status"] == "break"])
    pending = len([r for r in records if r["status"] == "pending"])
    total_pnl = sum(r.get("pnl", 0) for r in records)
    last_sync = max([r["broker_timestamp"] for r in records], default=None)
    
    return ReconciliationSummary(
        total_records=len(records),
        matched=matched,
        breaks=breaks,
        pending=pending,
        total_pnl=round(total_pnl, 2),
        last_sync=last_sync or ""
    )


@router.post("/signoff")
async def eod_signoff(
    request: SignoffRequest,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Perform EOD sign-off."""
    records = _records_db
    
    # Check for unresolved breaks
    breaks = [r for r in records if r["status"] == "break"]
    if breaks:
        return {
            "success": False,
            "message": f"Cannot sign off with {len(breaks)} unresolved breaks",
            "breaks": len(breaks)
        }
    
    # Record signoff
    signoff = {
        "signoff_id": f"SO{len(_signoffs) + 1:04d}",
        "timestamp": request.timestamp,
        "user_id": current_user.sub,
        "username": current_user.username,
        "record_count": len(records),
        "total_pnl": sum(r.get("pnl", 0) for r in records)
    }
    _signoffs.append(signoff)
    
    return {
        "success": True,
        "message": "EOD sign-off completed",
        "signoff": signoff
    }


@router.get("/signoffs")
async def get_signoffs(
    current_user: TokenData = Depends(get_current_user)
):
    """Get past sign-offs."""
    return {"signoffs": _signoffs}


@router.post("/resolve-break/{record_id}")
async def resolve_break(
    record_id: str,
    resolution: str,
    current_user: TokenData = Depends(require_roles([Role.ADMIN, Role.RISK_OFFICER]))
):
    """Resolve a reconciliation break."""
    for record in _records_db:
        if record["record_id"] == record_id:
            record["status"] = "resolved"
            record["resolution"] = resolution
            record["resolved_by"] = current_user.sub
            record["resolved_at"] = datetime.utcnow().isoformat()
            return {"success": True, "record": record}
    
    return {"success": False, "message": "Record not found"}


# Helper functions for trading engine integration
def add_reconciliation_record(record: dict):
    """Add a reconciliation record from trading engine."""
    _records_db.append(record)


def sync_broker_statements(broker: str, statements: list):
    """Sync broker statements and detect breaks."""
    for stmt in statements:
        # Find matching internal record
        matching = None
        for rec in _records_db:
            if (rec["symbol"] == stmt["symbol"] and 
                rec["side"] == stmt["side"] and 
                rec["broker"] == broker and
                rec["status"] == "pending"):
                matching = rec
                break
        
        if matching:
            # Check for breaks
            price_diff = abs(matching["price"] - stmt["price"])
            qty_diff = abs(matching["quantity"] - stmt["quantity"])
            time_diff = abs(
                datetime.fromisoformat(matching["internal_timestamp"].replace('Z', '+00:00')) -
                datetime.fromisoformat(stmt["timestamp"].replace('Z', '+00:00'))
            ).total_seconds()
            
            if price_diff > 0.01 or qty_diff > 0 or time_diff > 5:
                matching["status"] = "break"
                matching["break_reason"] = f"Price: {price_diff}, Qty: {qty_diff}, Time: {time_diff}s"
            else:
                matching["status"] = "matched"
                matching["broker_timestamp"] = stmt["timestamp"]
        else:
            # Orphaned broker record
            new_record = {
                "record_id": f"REC{len(_records_db) + 1:06d}",
                "symbol": stmt["symbol"],
                "side": stmt["side"],
                "quantity": stmt["quantity"],
                "price": stmt["price"],
                "broker": broker,
                "internal_timestamp": stmt["timestamp"],
                "broker_timestamp": stmt["timestamp"],
                "status": "break",
                "break_reason": "No matching internal record"
            }
            _records_db.append(new_record)


__all__ = ["router", "add_reconciliation_record", "sync_broker_statements"]