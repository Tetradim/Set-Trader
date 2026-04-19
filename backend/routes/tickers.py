"""Ticker CRUD, strategies, reorder, take-profit, cash-reserve endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

import deps
from schemas import TickerConfig, TickerCreate, TickerUpdate
from strategies import PRESET_STRATEGIES

router = APIRouter()


async def _broadcast_account_update():
    balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
    tickers = await deps.db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
    allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)
    await deps.ws_manager.broadcast({
        "type": "ACCOUNT_UPDATE",
        "account_balance": account_balance,
        "allocated": allocated,
        "available": round(account_balance - allocated, 2),
    })


@router.get("/tickers")
async def get_tickers():
    docs = await deps.db.tickers.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)
    return docs


@router.post("/tickers")
async def add_ticker(body: TickerCreate):
    sym = body.symbol.upper().strip()
    existing = await deps.db.tickers.find_one({"symbol": sym})
    if existing:
        raise HTTPException(400, f"{sym} already exists")
    max_order = await deps.db.tickers.find_one(sort=[("sort_order", -1)], projection={"sort_order": 1})
    next_order = (max_order.get("sort_order", 0) + 1) if max_order else 0
    from markets import detect_market_from_symbol
    market = body.market or detect_market_from_symbol(sym)
    t = TickerConfig(symbol=sym, base_power=body.base_power, sort_order=next_order, market=market)
    doc = t.model_dump()
    await deps.db.tickers.insert_one(doc)
    doc.pop("_id", None)
    await deps.ws_manager.broadcast({"type": "TICKER_ADDED", "ticker": doc})
    await _broadcast_account_update()
    return doc


@router.put("/tickers/{symbol}")
async def update_ticker(symbol: str, body: TickerUpdate):
    sym = symbol.upper()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No updates provided")
    result = await deps.db.tickers.update_one({"symbol": sym}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, f"{sym} not found")
    doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
    if "base_power" in updates:
        await _broadcast_account_update()
    return doc


@router.delete("/tickers/{symbol}")
async def delete_ticker(symbol: str):
    sym = symbol.upper()
    result = await deps.db.tickers.delete_one({"symbol": sym})
    if result.deleted_count == 0:
        raise HTTPException(404, f"{sym} not found")
    deps.engine._positions.pop(sym, None)
    deps.engine._trailing_highs.pop(sym, None)
    await deps.ws_manager.broadcast({"type": "TICKER_DELETED", "symbol": sym})
    await _broadcast_account_update()
    return {"deleted": sym}


@router.post("/tickers/reorder")
async def reorder_tickers(body: dict):
    order = body.get("order", [])
    if not order:
        raise HTTPException(400, "No order provided")
    for i, sym in enumerate(order):
        await deps.db.tickers.update_one({"symbol": sym.upper()}, {"$set": {"sort_order": i}})
    docs = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
    await deps.ws_manager.broadcast({"type": "TICKERS_REORDERED", "tickers": docs})
    return {"status": "ok"}


@router.post("/tickers/{symbol}/strategy/{preset}")
async def apply_strategy(symbol: str, preset: str):
    sym = symbol.upper()
    current_doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    if not current_doc:
        raise HTTPException(404, f"{sym} not found")

    if current_doc.get("strategy") == preset:
        backup = current_doc.get("custom_backup", {})
        if backup:
            backup["strategy"] = "custom"
            await deps.db.tickers.update_one({"symbol": sym}, {"$set": backup, "$unset": {"custom_backup": ""}})
        else:
            await deps.db.tickers.update_one({"symbol": sym}, {"$set": {"strategy": "custom"}})
        doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
        return doc

    strategy = PRESET_STRATEGIES.get(preset)
    if not strategy:
        raise HTTPException(400, f"Unknown preset: {preset}")
    backup_fields = {
        "avg_days": current_doc.get("avg_days"), "buy_offset": current_doc.get("buy_offset"),
        "buy_percent": current_doc.get("buy_percent"), "buy_order_type": current_doc.get("buy_order_type", "limit"),
        "sell_offset": current_doc.get("sell_offset"), "sell_percent": current_doc.get("sell_percent"),
        "sell_order_type": current_doc.get("sell_order_type", "limit"),
        "stop_offset": current_doc.get("stop_offset"), "stop_percent": current_doc.get("stop_percent"),
        "stop_order_type": current_doc.get("stop_order_type", "limit"),
        "trailing_enabled": current_doc.get("trailing_enabled"), "trailing_percent": current_doc.get("trailing_percent"),
        "trailing_percent_mode": current_doc.get("trailing_percent_mode", True),
        "trailing_order_type": current_doc.get("trailing_order_type", "limit"),
    }
    updates = strategy.model_dump()
    updates.pop("name")
    updates["strategy"] = preset
    updates["custom_backup"] = backup_fields
    await deps.db.tickers.update_one({"symbol": sym}, {"$set": updates})
    doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    return doc


@router.get("/strategies")
async def get_strategies():
    return {k: v.model_dump() for k, v in PRESET_STRATEGIES.items()}


@router.post("/tickers/{symbol}/take-profit")
async def take_profit(symbol: str):
    sym = symbol.upper()
    profit_doc = await deps.db.profits.find_one({"symbol": sym}, {"_id": 0})
    if not profit_doc or profit_doc.get("total_pnl", 0) <= 0:
        raise HTTPException(400, f"No positive profit to take for {sym}")
    amount = profit_doc.get("total_pnl", 0)
    await deps.db.cash_ledger.insert_one({
        "symbol": sym, "amount": amount, "timestamp": datetime.now(timezone.utc).isoformat(), "type": "TAKE_PROFIT",
    })
    await deps.db.settings.update_one({"key": "cash_reserve"}, {"$inc": {"value": amount}}, upsert=True)
    await deps.db.profits.update_one({"symbol": sym}, {"$set": {"total_pnl": 0, "updated_at": datetime.now(timezone.utc).isoformat()}})
    ticker_doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    if ticker_doc and ticker_doc.get("compound_profits", True):
        new_bp = max(1.0, round(ticker_doc.get("base_power", 100) - amount, 2))
        await deps.db.tickers.update_one({"symbol": sym}, {"$set": {"base_power": new_bp}})
        updated_ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
        if updated_ticker:
            await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": updated_ticker})
    deps.logger.info(f"TAKE PROFIT: {sym} ${amount:.2f} moved to cash reserve")
    profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
    profits = {p["symbol"]: p.get("total_pnl", 0) for p in profits_list}
    cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    cash_total = cash_doc.get("value", 0) if cash_doc else 0
    await deps.ws_manager.broadcast({"type": "PROFITS_UPDATE", "profits": profits, "cash_reserve": round(cash_total, 2)})
    return {"taken": round(amount, 2), "symbol": sym, "cash_reserve": round(cash_total, 2)}


@router.get("/cash-reserve")
async def get_cash_reserve():
    cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    cash_total = cash_doc.get("value", 0) if cash_doc else 0
    ledger = await deps.db.cash_ledger.find({}, {"_id": 0}).sort("timestamp", -1).to_list(50)
    return {"total": round(cash_total, 2), "ledger": ledger}
