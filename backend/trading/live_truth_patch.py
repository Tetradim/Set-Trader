"""Live-money compatibility guards for broker-truth execution.

This module is imported once from :mod:`trading.__init__`. It installs the
broker-evidence implementation on the existing mixin classes without changing
their public API. Live state transitions depend on broker fills rather than
quotes or requested quantities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import deps
from trading.broker_execution import BrokerExecutionMixin, LiveOrderExecutionError
from trading.order_lifecycle import OrderLifecycleMixin
from trading.trade_accounting import TradeAccountingMixin


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _result_order_id(self, result: dict) -> str:
    for key in ("broker_order_id", "order_id", "external_id"):
        value = str((result or {}).get(key) or "").strip()
        if value:
            return value
    return ""


def _result_filled_qty(self, result: dict) -> float:
    for key in ("filled_quantity", "filled_qty", "cumulative_filled_quantity"):
        value = _number((result or {}).get(key))
        if value > 0:
            return value
    return 0.0


def _result_fill_price(self, result: dict) -> float:
    for key in ("avg_fill_price", "filled_price", "average_fill_price"):
        value = _number((result or {}).get(key))
        if value > 0:
            return value
    return 0.0


def _results_filled_qty(self, results: list[dict]) -> float:
    return round(sum(_result_filled_qty(self, result) for result in results or []), 8)


def _results_weighted_price(self, results: list[dict]) -> float:
    qty = _results_filled_qty(self, results)
    if qty <= 0:
        return 0.0
    notional = sum(
        _result_filled_qty(self, result) * _result_fill_price(self, result)
        for result in results or []
    )
    return round(notional / qty, 8) if notional > 0 else 0.0


def _result_confirmed(self, result: dict) -> bool:
    status = str((result or {}).get("status") or "").strip().lower()
    return (
        status in self._BROKER_CONFIRMED_STATUSES
        and not str((result or {}).get("error") or "").strip()
        and bool(_result_order_id(self, result))
        and _result_filled_qty(self, result) > 0
        and _result_fill_price(self, result) > 0
    )


def _result_pending(self, result: dict) -> bool:
    status = str((result or {}).get("status") or "").strip().lower()
    return (
        status in (self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES)
        and not str((result or {}).get("error") or "").strip()
        and bool(_result_order_id(self, result))
    )


async def _pending_reason(self, intent_key: str) -> str:
    pending = self._pending_live_order_intents().get(intent_key)
    if pending:
        order_ids = ", ".join(pending.get("order_ids") or [])
        return f"broker order is still pending fill ({order_ids})"

    try:
        collection = getattr(deps.db, "broker_orders", None)
        if collection is None:
            return ""
        doc = await collection.find_one(
            {
                "intent_key": intent_key,
                "status": {
                    "$in": sorted(
                        self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES
                    )
                },
            },
            {"_id": 0, "broker_id": 1, "broker_order_id": 1},
        )
        if doc:
            return (
                "broker order is still pending reconciliation "
                f"({doc.get('broker_id', 'broker')}:{doc.get('broker_order_id', 'unknown')})"
            )
    except Exception as exc:
        deps.logger.warning("Could not read durable broker-order ledger: %s", exc)
    return ""


async def _available_sell_quantities(
    self,
    symbol: str,
    broker_ids: list[str],
) -> dict[str, float]:
    available: dict[str, float] = {}
    missing = []
    for broker_id in broker_ids:
        actual = await self._broker_position_quantity(broker_id, symbol)
        if actual is None:
            missing.append(broker_id)
            continue
        reserved = await self._broker_open_sell_quantity(broker_id, symbol)
        available[broker_id] = round(max(0.0, actual - reserved), 8)
    if missing:
        raise LiveOrderExecutionError(
            f"SELL for {symbol} blocked: broker position evidence unavailable for {missing}"
        )
    return available


async def _verify_sell_quantities(
    self,
    symbol: str,
    quantity: float,
    broker_ids: list[str],
) -> None:
    if quantity <= 0:
        return
    available = await _available_sell_quantities(self, symbol, broker_ids)
    total = round(sum(available.values()), 8)
    if total + 1e-8 < quantity:
        details = ", ".join(f"{broker}={qty:.8f}" for broker, qty in available.items())
        raise LiveOrderExecutionError(
            f"SELL for {symbol} blocked: broker position is insufficient "
            f"(available {total:.8f}, requested {quantity:.8f}; {details})"
        )


async def _persist_results(
    self,
    *,
    intent_key: str,
    symbol: str,
    side: str,
    order_type: str,
    reference_price: float,
    plans: list[dict],
    results: list[dict],
) -> None:
    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return

    plan_by_broker = {plan["broker_id"]: plan for plan in plans}
    now = datetime.now(timezone.utc).isoformat()
    try:
        for result in results:
            broker_id = str(result.get("broker_id") or "")
            plan = plan_by_broker.get(broker_id, {})
            broker_order_id = _result_order_id(self, result)
            durable_id = broker_order_id or str(result.get("idempotency_key") or "")
            if not durable_id:
                durable_id = f"unidentified:{intent_key}:{broker_id}"
            await collection.update_one(
                {
                    "intent_key": intent_key,
                    "broker_id": broker_id,
                    "durable_order_id": durable_id,
                },
                {
                    "$set": {
                        "intent_key": intent_key,
                        "broker_id": broker_id,
                        "durable_order_id": durable_id,
                        "broker_order_id": broker_order_id,
                        "idempotency_key": str(result.get("idempotency_key") or ""),
                        "symbol": symbol,
                        "side": side,
                        "order_type": order_type,
                        "reference_price": reference_price,
                        "requested_quantity": _number(plan.get("quantity")),
                        "status": str(result.get("status") or "unknown").lower(),
                        "filled_quantity": _result_filled_qty(self, result),
                        "avg_fill_price": _result_fill_price(self, result),
                        "error": str(result.get("error") or ""),
                        "updated_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
    except Exception as exc:
        raise LiveOrderExecutionError(
            f"{side} for {symbol} submitted but broker-order ledger persistence failed: {exc}"
        ) from exc


async def _build_plans(
    self,
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    broker_ids: list[str],
    allocations: dict,
) -> list[dict]:
    if side == "BUY":
        total_allocation = sum(
            max(0.0, _number(allocations.get(broker_id)))
            for broker_id in broker_ids
        )
        if total_allocation <= 0 or price <= 0:
            raise LiveOrderExecutionError(
                f"BUY for {symbol} has no positive allocation or reference price"
            )
        plans = []
        for broker_id in broker_ids:
            allocation = max(0.0, _number(allocations.get(broker_id)))
            child_qty = allocation / price
            if quantity > 0:
                child_qty = quantity * (allocation / total_allocation)
            child_qty = round(child_qty, 8)
            if child_qty > 0:
                plans.append(
                    {
                        "broker_id": broker_id,
                        "allocation": allocation,
                        "quantity": child_qty,
                    }
                )
        return plans

    if side != "SELL":
        raise LiveOrderExecutionError(f"Unsupported live side for {symbol}: {side}")

    available = await _available_sell_quantities(self, symbol, broker_ids)
    total_available = round(sum(available.values()), 8)
    desired = quantity if quantity > 0 else total_available
    if desired <= 0 or total_available + 1e-8 < desired:
        details = ", ".join(f"{broker}={qty:.8f}" for broker, qty in available.items())
        raise LiveOrderExecutionError(
            f"SELL for {symbol} blocked: broker position is insufficient "
            f"(available {total_available:.8f}, requested {desired:.8f}; {details})"
        )

    plans = []
    remaining = desired
    holdings = [(broker, qty) for broker, qty in available.items() if qty > 0]
    for index, (broker_id, held_qty) in enumerate(holdings):
        if index == len(holdings) - 1:
            child_qty = min(held_qty, remaining)
        else:
            child_qty = min(
                held_qty,
                remaining,
                desired * (held_qty / total_available),
            )
        child_qty = round(max(0.0, child_qty), 8)
        if child_qty <= 0:
            continue
        plans.append(
            {
                "broker_id": broker_id,
                "allocation": max(
                    _number(allocations.get(broker_id)),
                    child_qty * max(price, 0.01),
                ),
                "quantity": child_qty,
            }
        )
        remaining = round(max(0.0, remaining - child_qty), 8)

    if remaining > 1e-8:
        raise LiveOrderExecutionError(
            f"SELL for {symbol} could not allocate {remaining:.8f} shares across brokers"
        )
    return plans


async def _place_live_order_or_raise(
    self,
    *,
    sym: str,
    broker_ids: list,
    broker_allocs: dict,
    order_template: dict,
    action_label: str,
) -> list[dict]:
    broker_ids = broker_ids or []
    broker_allocs = broker_allocs or {}
    if not self._should_place_broker_orders(broker_ids):
        return []

    active = self._live_broker_ids_with_allocations(broker_ids, broker_allocs)
    if not active:
        raise LiveOrderExecutionError(
            f"{action_label} for {sym} has broker IDs but no positive broker allocations"
        )

    side, quantity, price = self._live_pretrade_values(order_template, broker_allocs)
    order_type = str((order_template or {}).get("order_type") or "").upper()
    intent_key = f"{sym.upper()}:{side.upper()}:{order_type}"
    reason = await _pending_reason(self, intent_key)
    if reason:
        raise LiveOrderExecutionError(f"{action_label} for {sym} skipped: {reason}")

    plans = await _build_plans(
        self,
        symbol=sym,
        side=side,
        quantity=quantity,
        price=price,
        broker_ids=active,
        allocations=broker_allocs,
    )
    parent_qty = round(sum(plan["quantity"] for plan in plans), 8)
    if hasattr(self, "pre_trade_check"):
        allowed, reason = await self.pre_trade_check(sym, side, parent_qty, price)
        if not allowed:
            raise LiveOrderExecutionError(reason)

    results: list[dict] = []
    for plan in plans:
        child_template = {**(order_template or {}), "quantity": plan["quantity"]}
        try:
            child = await deps.broker_mgr.place_orders_for_ticker(
                broker_ids=[plan["broker_id"]],
                allocations={plan["broker_id"]: plan["allocation"]},
                order_template=child_template,
            )
        except Exception as exc:
            child = [
                {
                    "broker_id": plan["broker_id"],
                    "status": "error",
                    "error": str(exc),
                }
            ]
        if not child:
            child = [
                {
                    "broker_id": plan["broker_id"],
                    "status": "error",
                    "error": "broker produced no order result",
                }
            ]
        results.extend(child)

    await _persist_results(
        self,
        intent_key=intent_key,
        symbol=sym,
        side=side,
        order_type=order_type,
        reference_price=price,
        plans=plans,
        results=results,
    )

    expected = {plan["broker_id"] for plan in plans}
    observed = {
        str(result.get("broker_id") or "")
        for result in results
        if result.get("broker_id")
    }
    missing = sorted(expected - observed)
    pending = [result for result in results if _result_pending(self, result)]
    failed = [
        result
        for result in results
        if not _result_confirmed(self, result)
        and not _result_pending(self, result)
    ]

    if pending:
        self._mark_live_order_pending(intent_key, pending)

    filled_qty = _results_filled_qty(self, results)
    if missing or pending or failed:
        order_ids = [
            _result_order_id(self, result)
            for result in results
            if _result_order_id(self, result)
        ]
        raise LiveOrderExecutionError(
            f"{action_label} for {sym} is not fully filled; "
            f"filled={filled_qty:.8f}/{parent_qty:.8f}, "
            f"missing={missing}, pending={len(pending)}, failed={len(failed)}, "
            f"broker_order_ids={order_ids}. Broker reconciliation is required before retry."
        )

    avg_fill_price = _results_weighted_price(self, results)
    if abs(filled_qty - parent_qty) > 1e-6 or avg_fill_price <= 0:
        self._mark_live_order_pending(intent_key, results)
        raise LiveOrderExecutionError(
            f"{action_label} for {sym} returned inconsistent fill evidence "
            f"(filled={filled_qty:.8f}, requested={parent_qty:.8f}, "
            f"avg_fill_price={avg_fill_price:.8f})"
        )

    self._clear_live_order_pending(intent_key)
    return results


_original_record_trade = TradeAccountingMixin._record_trade
_original_update_profit = TradeAccountingMixin._update_profit
_original_execute_buy = OrderLifecycleMixin.execute_buy
_original_execute_sell = OrderLifecycleMixin.execute_sell
_original_shared_sell = OrderLifecycleMixin._execute_sell


async def _record_trade_from_broker_truth(self, trade):
    if str(getattr(trade, "trading_mode", "")).lower() == "live":
        results = list(getattr(trade, "broker_results", None) or [])
        if not results or not all(_result_confirmed(self, result) for result in results):
            raise LiveOrderExecutionError(
                f"Refusing to record live trade for {trade.symbol} without complete broker fill evidence"
            )

        filled_qty = _results_filled_qty(self, results)
        fill_price = _results_weighted_price(self, results)
        if filled_qty <= 0 or fill_price <= 0:
            raise LiveOrderExecutionError(
                f"Refusing to record live trade for {trade.symbol}: invalid fill quantity/price"
            )

        trade.quantity = round(filled_qty, 8)
        trade.price = round(fill_price, 8)
        trade.total_value = round(filled_qty * fill_price, 2)
        if str(trade.side).upper() == "BUY":
            trade.buy_power = trade.total_value
            self._positions[trade.symbol] = {
                "qty": trade.quantity,
                "avg_entry": trade.price,
                "high": trade.price,
            }
        else:
            entry = _number(getattr(trade, "entry_price", 0))
            trade.pnl = round((fill_price - entry) * filled_qty, 2)

    self._last_broker_truth_trade = trade
    return await _original_record_trade(self, trade)


async def _update_profit_from_recorded_trade(self, symbol: str, pnl: float, compound: bool = False):
    normalized = getattr(self, "_last_broker_truth_trade", None)
    if (
        normalized is not None
        and str(getattr(normalized, "symbol", "")).upper() == symbol.upper()
        and str(getattr(normalized, "side", "")).upper() != "BUY"
        and str(getattr(normalized, "trading_mode", "")).lower() == "live"
    ):
        pnl = _number(getattr(normalized, "pnl", pnl))

    await _original_update_profit(self, symbol, pnl, compound)

    if not compound or pnl <= 0:
        return

    ticker = await deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
    if not ticker:
        return
    broker_ids = ticker.get("broker_ids", []) or []
    allocations = ticker.get("broker_allocations", {}) or {}
    weights = {
        broker_id: max(0.0, _number(allocations.get(broker_id)))
        for broker_id in broker_ids
    }
    total = sum(weights.values())
    if total <= 0:
        return
    increments = {
        f"broker_allocations.{broker_id}": round(pnl * (weight / total), 8)
        for broker_id, weight in weights.items()
        if weight > 0
    }
    if increments:
        await deps.db.tickers.update_one({"symbol": symbol}, {"$inc": increments})


async def _execute_buy_result_from_truth(self, symbol: str, price: float) -> dict:
    result = await _original_execute_buy(self, symbol, price)
    trade = getattr(self, "_last_broker_truth_trade", None)
    if trade and str(getattr(trade, "symbol", "")).upper() == symbol.upper():
        result.update(
            {
                "price": trade.price,
                "quantity": trade.quantity,
                "total_value": trade.total_value,
            }
        )
    return result


async def _execute_sell_result_from_truth(self, symbol: str, price: float = None) -> dict:
    result = await _original_execute_sell(self, symbol, price)
    trade = getattr(self, "_last_broker_truth_trade", None)
    if trade and str(getattr(trade, "symbol", "")).upper() == symbol.upper():
        result.update(
            {
                "price": trade.price,
                "quantity": trade.quantity,
                "pnl": trade.pnl,
                "total_value": trade.total_value,
            }
        )
    return result


async def _shared_sell_result_from_truth(
    self,
    sym: str,
    price: float,
    qty: float,
    entry: float,
    order_type: str,
    reason: str,
) -> dict:
    result = await _original_shared_sell(
        self,
        sym,
        price,
        qty,
        entry,
        order_type,
        reason,
    )
    trade = getattr(self, "_last_broker_truth_trade", None)
    if trade and str(getattr(trade, "symbol", "")).upper() == sym.upper():
        result.update(
            {
                "price": trade.price,
                "quantity": trade.quantity,
                "pnl": trade.pnl,
                "total_value": trade.total_value,
            }
        )
    return result


BrokerExecutionMixin._broker_result_order_identifier = _result_order_id
BrokerExecutionMixin._broker_result_filled_quantity = _result_filled_qty
BrokerExecutionMixin._broker_result_fill_price = _result_fill_price
BrokerExecutionMixin._broker_results_filled_quantity = _results_filled_qty
BrokerExecutionMixin._broker_results_weighted_fill_price = _results_weighted_price
BrokerExecutionMixin._broker_result_confirmed = _result_confirmed
BrokerExecutionMixin._broker_result_pending = _result_pending
BrokerExecutionMixin._pending_live_order_reason = _pending_reason
BrokerExecutionMixin._available_sell_quantities = _available_sell_quantities
BrokerExecutionMixin._verify_live_sell_quantities = _verify_sell_quantities
BrokerExecutionMixin._place_live_order_or_raise = _place_live_order_or_raise

TradeAccountingMixin._record_trade = _record_trade_from_broker_truth
TradeAccountingMixin._update_profit = _update_profit_from_recorded_trade
OrderLifecycleMixin.execute_buy = _execute_buy_result_from_truth
OrderLifecycleMixin.execute_sell = _execute_sell_result_from_truth
OrderLifecycleMixin._execute_sell = _shared_sell_result_from_truth
