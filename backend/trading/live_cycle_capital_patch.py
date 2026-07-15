"""Broker-capacity-bounded net-P&L compounding for live equity cycles."""
from __future__ import annotations

from datetime import datetime, timezone
import math
import os
from typing import Any

import deps
from trading.trade_accounting import TradeAccountingMixin


_current_update_profit = TradeAccountingMixin._update_profit
_ACTIVE_ORDER_STATUSES = {
    "new",
    "accepted",
    "submitted",
    "pending",
    "open",
    "partially_filled",
    "partial",
}


def _num(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trade_fees(trade: Any) -> float:
    total = 0.0
    for result in list(getattr(trade, "broker_results", None) or []):
        explicit_total = _num(result.get("total_fees"))
        if explicit_total > 0:
            total += explicit_total
            continue
        total += sum(
            max(0.0, _num(result.get(field)))
            for field in (
                "fee",
                "fees",
                "commission",
                "commissions",
                "regulatory_fee",
                "transaction_fee",
                "exchange_fee",
            )
        )
    return round(total, 8)


def _account_capacity(account: Any) -> float:
    balance = _num(getattr(account, "balance", None))
    buying_power = _num(getattr(account, "buying_power", None))
    if str(os.getenv("PULSE_ALLOW_MARGIN_COMPOUNDING", "false")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return max(0.0, buying_power or balance)
    positive = [value for value in (balance, buying_power) if value > 0]
    return min(positive) if positive else 0.0


async def _reserved_open_buy_notional(broker_id: str) -> float:
    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return 0.0
    try:
        rows = await collection.find(
            {
                "broker_id": broker_id,
                "side": "BUY",
                "status": {"$in": sorted(_ACTIVE_ORDER_STATUSES)},
            },
            {
                "_id": 0,
                "requested_quantity": 1,
                "filled_quantity": 1,
                "reference_price": 1,
            },
        ).to_list(1000)
    except Exception as exc:
        deps.logger.warning(
            "Could not calculate working-order reserve for %s: %s",
            broker_id,
            exc,
        )
        return 0.0
    return round(
        sum(
            max(
                0.0,
                _num(row.get("requested_quantity"))
                - _num(row.get("filled_quantity")),
            )
            * max(0.0, _num(row.get("reference_price")))
            for row in rows
        ),
        8,
    )


async def _other_strategy_allocations(symbol: str, broker_id: str) -> float:
    try:
        tickers = await deps.db.tickers.find(
            {"symbol": {"$ne": symbol}},
            {"_id": 0, "broker_allocations": 1},
        ).to_list(1000)
    except Exception as exc:
        deps.logger.warning(
            "Could not calculate other strategy allocations for %s: %s",
            broker_id,
            exc,
        )
        return 0.0
    return round(
        sum(
            max(
                0.0,
                _num((ticker.get("broker_allocations") or {}).get(broker_id)),
            )
            for ticker in tickers
        ),
        8,
    )


async def _broker_cycle_capacity(symbol: str, broker_ids: list[str]) -> tuple[float, dict[str, float], list[str]]:
    capacities: dict[str, float] = {}
    errors: list[str] = []
    manager = getattr(deps, "broker_mgr", None)
    for broker_id in broker_ids:
        adapter = manager.get_adapter(broker_id) if manager and hasattr(manager, "get_adapter") else None
        if adapter is None or not hasattr(adapter, "get_account"):
            errors.append(f"{broker_id}: account capacity unavailable")
            continue
        try:
            account = await adapter.get_account()
            gross_capacity = _account_capacity(account)
            other_allocated = await _other_strategy_allocations(symbol, broker_id)
            working_reserve = await _reserved_open_buy_notional(broker_id)
            capacities[broker_id] = round(
                max(0.0, gross_capacity - other_allocated - working_reserve),
                8,
            )
        except Exception as exc:
            errors.append(f"{broker_id}: {exc}")
    return round(sum(capacities.values()), 8), capacities, errors


def _scaled_allocations(
    broker_ids: list[str],
    existing: dict,
    next_capital: float,
    capacities: dict[str, float],
) -> dict[str, float]:
    weighted = {
        broker_id: max(0.0, _num(existing.get(broker_id)))
        for broker_id in broker_ids
        if capacities.get(broker_id, 0) > 0
    }
    weight_total = sum(weighted.values())
    if weight_total <= 0:
        weighted = {
            broker_id: capacity
            for broker_id, capacity in capacities.items()
            if broker_id in broker_ids and capacity > 0
        }
        weight_total = sum(weighted.values())
    if weight_total <= 0:
        return {}

    scaled: dict[str, float] = {}
    remaining = next_capital
    eligible = list(weighted)
    for index, broker_id in enumerate(eligible):
        if index == len(eligible) - 1:
            allocation = remaining
        else:
            allocation = next_capital * (weighted[broker_id] / weight_total)
            allocation = min(allocation, capacities.get(broker_id, 0))
        allocation = round(max(0.0, allocation), 8)
        scaled[broker_id] = allocation
        remaining = round(max(0.0, remaining - allocation), 8)
    return scaled


async def _update_profit_with_live_cycle_capital(
    self,
    symbol: str,
    pnl: float,
    compound: bool = False,
):
    trade = getattr(self, "_last_broker_truth_trade", None)
    gross_pnl = _num(getattr(trade, "pnl", pnl)) if trade is not None else _num(pnl)
    fees = _trade_fees(trade) if trade is not None else 0.0
    net_pnl = round(gross_pnl - fees, 8)

    # Preserve existing profit/risk bookkeeping but prevent its positive-only
    # base-power mutation. This patch owns the complete cycle-capital update.
    await _current_update_profit(self, symbol, net_pnl, False)

    if trade is not None and getattr(trade, "id", None):
        try:
            await deps.db.trades.update_one(
                {"id": trade.id},
                {
                    "$set": {
                        "gross_pnl": gross_pnl,
                        "broker_fees": fees,
                        "net_pnl": net_pnl,
                        "cycle_accounted_at": _now(),
                    }
                },
            )
        except Exception as exc:
            deps.logger.warning(
                "Could not annotate net cycle P&L for trade %s: %s",
                trade.id,
                exc,
            )

    if not compound:
        return

    ticker = await deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
    if not ticker:
        return
    current_capital = max(0.0, _num(ticker.get("base_power")))
    desired_capital = max(0.0, current_capital + net_pnl)
    broker_ids = list(ticker.get("broker_ids") or [])
    existing_allocations = dict(ticker.get("broker_allocations") or {})

    capacity_total = 0.0
    capacities: dict[str, float] = {}
    capacity_errors: list[str] = []
    if broker_ids:
        capacity_total, capacities, capacity_errors = await _broker_cycle_capacity(
            symbol,
            broker_ids,
        )

    state = "accounted"
    if broker_ids and capacity_total <= 0:
        if net_pnl > 0:
            next_capital = current_capital
            state = "awaiting_broker_capacity"
        else:
            next_capital = desired_capital
            state = "loss_applied_capacity_unavailable"
    elif broker_ids:
        next_capital = min(desired_capital, capacity_total)
        state = "capacity_capped" if next_capital + 1e-8 < desired_capital else "compounded"
    else:
        next_capital = desired_capital
        state = "compounded_without_broker_assignment"

    updates: dict[str, Any] = {
        "base_power": round(next_capital, 8),
        "last_cycle_gross_pnl": gross_pnl,
        "last_cycle_fees": fees,
        "last_cycle_net_pnl": net_pnl,
        "last_cycle_capital": round(next_capital, 8),
        "last_cycle_state": state,
        "last_cycle_accounted_at": _now(),
    }
    if broker_ids and capacities and next_capital >= 0:
        scaled = _scaled_allocations(
            broker_ids,
            existing_allocations,
            next_capital,
            capacities,
        )
        if scaled:
            updates["broker_allocations"] = scaled

    await deps.db.tickers.update_one(
        {"symbol": symbol},
        {"$set": updates},
    )

    ledger = getattr(deps.db, "strategy_cycles", None)
    if ledger is not None:
        await ledger.update_one(
            {"symbol": symbol},
            {
                "$inc": {"cycle_number": 1},
                "$set": {
                    "symbol": symbol,
                    "strategy_id": str(ticker.get("strategy") or "custom"),
                    "previous_cycle_capital": current_capital,
                    "desired_cycle_capital": desired_capital,
                    "cycle_capital": round(next_capital, 8),
                    "gross_pnl": gross_pnl,
                    "fees": fees,
                    "net_pnl": net_pnl,
                    "broker_capacity": capacity_total,
                    "broker_capacities": capacities,
                    "capacity_errors": capacity_errors,
                    "state": state,
                    "updated_at": _now(),
                },
                "$setOnInsert": {"created_at": _now()},
            },
            upsert=True,
        )

    updated = await deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
    if updated:
        await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": updated})
    deps.logger.info(
        "CYCLE CAPITAL: %s gross=%+.4f fees=%.4f net=%+.4f capital=%.4f state=%s",
        symbol,
        gross_pnl,
        fees,
        net_pnl,
        next_capital,
        state,
    )


TradeAccountingMixin._update_profit = _update_profit_with_live_cycle_capital
