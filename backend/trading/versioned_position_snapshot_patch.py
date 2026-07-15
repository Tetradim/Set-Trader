"""Publish monotonic broker-backed position snapshots to Sentinel Edge."""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Literal, Optional

from pydantic import Field

import deps
from shared import commands
import shared.edge_integration as integration


_current_on_trade_executed = integration.on_trade_executed


def _num(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


class VersionedPositionUpdateCommand(commands.BaseCommand):
    command_type: Literal[commands.CommandType.POSITION_UPDATE] = commands.CommandType.POSITION_UPDATE
    position_size: float = 0.0
    entry_price: Optional[float] = None
    current_pnl_pct: float = 0.0
    current_pnl_dollar: float = 0.0
    market_value: Optional[float] = None
    ledger_version: int = 0
    snapshot_id: str = ""
    snapshot_timestamp: datetime = Field(default_factory=_now)
    broker_ids: list[str] = Field(default_factory=list)
    available_quantity: float = 0.0
    reserved_exit_quantity: float = 0.0
    bid: Optional[float] = None
    ask: Optional[float] = None
    mark: Optional[float] = None
    peak_price: Optional[float] = None
    drawdown_pct: float = 0.0
    trailing_enabled: bool = False
    trailing_percent: Optional[float] = None
    working_order_ids: list[str] = Field(default_factory=list)
    truth_source: str = "broker_fill_ledger"


async def _next_version(symbol: str) -> int:
    collection = getattr(deps.db, "position_snapshot_versions", None)
    if collection is None:
        engine = getattr(deps, "engine", None)
        versions = getattr(engine, "_position_snapshot_versions", {})
        version = int(versions.get(symbol, 0)) + 1
        if engine is not None:
            engine._position_snapshot_versions = {**versions, symbol: version}
        return version
    await collection.update_one(
        {"symbol": symbol},
        {
            "$inc": {"ledger_version": 1},
            "$set": {"updated_at": _now().isoformat()},
            "$setOnInsert": {"created_at": _now().isoformat()},
        },
        upsert=True,
    )
    document = await collection.find_one(
        {"symbol": symbol},
        {"_id": 0, "ledger_version": 1},
    )
    return max(1, int((document or {}).get("ledger_version") or 1))


async def _working_orders(symbol: str) -> tuple[list[str], float]:
    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return [], 0.0
    statuses = [
        "new",
        "accepted",
        "submitted",
        "pending",
        "open",
        "partially_filled",
        "partial",
    ]
    try:
        rows = await collection.find(
            {"symbol": symbol, "status": {"$in": statuses}},
            {
                "_id": 0,
                "side": 1,
                "broker_order_id": 1,
                "requested_quantity": 1,
                "filled_quantity": 1,
            },
        ).to_list(500)
    except Exception:
        return [], 0.0
    order_ids = [
        str(row.get("broker_order_id") or "")
        for row in rows
        if str(row.get("broker_order_id") or "")
    ]
    reserved_sell = round(
        sum(
            max(
                0.0,
                _num(row.get("requested_quantity"))
                - _num(row.get("filled_quantity")),
            )
            for row in rows
            if str(row.get("side") or "").upper() == "SELL"
        ),
        8,
    )
    return order_ids, reserved_sell


async def _executable_quote(symbol: str, broker_ids: list[str]) -> tuple[float, float]:
    bids: list[float] = []
    asks: list[float] = []
    manager = getattr(deps, "broker_mgr", None)
    if manager is None or not hasattr(manager, "get_adapter"):
        return 0.0, 0.0
    for broker_id in broker_ids:
        adapter = manager.get_adapter(broker_id)
        getter = getattr(adapter, "get_quote_snapshot", None) if adapter else None
        if not callable(getter):
            continue
        try:
            quote = await getter(symbol)
            bid = _num(quote.get("bid"))
            ask = _num(quote.get("ask"))
            if bid > 0:
                bids.append(bid)
            if ask > 0:
                asks.append(ask)
        except Exception:
            continue
    return (min(bids) if bids else 0.0, max(asks) if asks else 0.0)


async def _publish_versioned_position_snapshot(trade_data: dict) -> bool:
    if not integration.edge_client.is_enabled or not integration.edge_client.is_connected:
        return False
    symbol = str(trade_data.get("symbol") or "").upper()
    if not symbol:
        return False

    engine = deps.engine
    position = dict(getattr(engine, "_positions", {}).get(symbol, {}) or {})
    quantity = max(0.0, _num(position.get("qty")))
    entry = _num(position.get("avg_entry"))
    peak = _num(position.get("high"))
    ticker = await deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0}) or {}
    broker_ids = list(ticker.get("broker_ids") or [])
    working_ids, reserved_exit = await _working_orders(symbol)
    bid, ask = await _executable_quote(symbol, broker_ids)
    try:
        mark = await deps.price_service.get_price(symbol) if quantity > 0 else 0.0
    except Exception:
        mark = _num(trade_data.get("price"))
    if bid > 0 and ask > 0:
        mark = (bid + ask) / 2.0
    elif bid > 0:
        mark = bid
    elif ask > 0:
        mark = ask

    market_value = quantity * mark
    unrealized = (mark - entry) * quantity if quantity > 0 and entry > 0 else 0.0
    pnl_pct = ((mark - entry) / entry * 100.0) if quantity > 0 and entry > 0 else 0.0
    drawdown = ((peak - mark) / peak * 100.0) if quantity > 0 and peak > 0 and mark < peak else 0.0
    version = await _next_version(symbol)
    timestamp = _now()
    command = VersionedPositionUpdateCommand(
        symbol=symbol,
        position_size=quantity,
        entry_price=entry or None,
        current_pnl_pct=pnl_pct,
        current_pnl_dollar=unrealized,
        market_value=market_value,
        ledger_version=version,
        snapshot_id=f"{symbol}:{version}",
        snapshot_timestamp=timestamp,
        broker_ids=broker_ids,
        available_quantity=max(0.0, quantity - reserved_exit),
        reserved_exit_quantity=reserved_exit,
        bid=bid or None,
        ask=ask or None,
        mark=mark or None,
        peak_price=peak or None,
        drawdown_pct=drawdown,
        trailing_enabled=bool(ticker.get("trailing_enabled", False)),
        trailing_percent=ticker.get("trailing_percent"),
        working_order_ids=working_ids,
        metadata={
            "trade_id": trade_data.get("id"),
            "side": trade_data.get("side"),
            "trading_mode": trade_data.get("trading_mode"),
        },
    )
    sent = await integration.edge_client.send_position_update(command)
    snapshot_collection = getattr(deps.db, "position_snapshots", None)
    if snapshot_collection is not None:
        await snapshot_collection.update_one(
            {"symbol": symbol},
            {"$set": command.model_dump(mode="json")},
            upsert=True,
        )
    return bool(sent)


async def _on_trade_executed_with_versioned_snapshot(trade_data: dict) -> None:
    await _current_on_trade_executed(trade_data)
    try:
        await _publish_versioned_position_snapshot(trade_data)
    except Exception as exc:
        deps.logger.error(
            "Failed to publish versioned position snapshot for %s: %s",
            trade_data.get("symbol"),
            exc,
            exc_info=True,
        )


integration.on_trade_executed = _on_trade_executed_with_versioned_snapshot
commands.VersionedPositionUpdateCommand = VersionedPositionUpdateCommand
