"""Final live-order orchestration: risk first, then broker evidence and fills."""

from __future__ import annotations

import deps
from trading.broker_execution import BrokerExecutionMixin, LiveOrderExecutionError
from trading.live_truth_patch import (
    _build_plans,
    _number,
    _pending_reason,
    _persist_results,
    _result_confirmed,
    _result_order_id,
    _result_pending,
    _results_filled_qty,
    _results_weighted_price,
)


async def _preflight_sell_evidence(
    self,
    symbol: str,
    quantity: float,
    broker_ids: list[str],
) -> None:
    total_available = 0.0
    details = []
    for broker_id in broker_ids:
        actual = await self._broker_position_quantity(broker_id, symbol)
        if actual is None:
            raise LiveOrderExecutionError(
                f"SELL for {symbol} blocked: broker position evidence unavailable for [{broker_id!r}]"
            )
        reserved = await self._broker_open_sell_quantity(broker_id, symbol)
        available = max(0.0, actual - reserved)
        total_available += available
        if reserved > 0:
            details.append(
                f"{broker_id} holds {actual:.8f}, has {reserved:.8f} already in open sell orders"
            )
        else:
            details.append(f"{broker_id} available={available:.8f}")

    if total_available + 1e-8 < quantity:
        raise LiveOrderExecutionError(
            f"SELL for {symbol} blocked: broker position is insufficient "
            f"(available {total_available:.8f}, requested {quantity:.8f}; "
            f"{'; '.join(details)})"
        )


async def _place_live_order_risk_first(
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

    side, quantity, price = self._live_pretrade_values(order_template, broker_allocs)
    order_type = str((order_template or {}).get("order_type") or "").upper()
    intent_key = f"{sym.upper()}:{side.upper()}:{order_type}"

    if side == "BUY" and quantity <= 0 and price > 0:
        quantity = round(
            sum(max(0.0, _number(broker_allocs.get(broker_id))) for broker_id in broker_ids)
            / price,
            8,
        )
    if quantity <= 0:
        raise LiveOrderExecutionError(
            f"{action_label} for {sym} has no positive requested quantity"
        )

    # Risk/kill-switch decisions must not depend on broker connectivity.
    if hasattr(self, "pre_trade_check"):
        allowed, reason = await self.pre_trade_check(sym, side, quantity, price)
        if not allowed:
            raise LiveOrderExecutionError(reason)

    pending_reason = await _pending_reason(self, intent_key)
    if pending_reason:
        raise LiveOrderExecutionError(f"{action_label} for {sym} skipped: {pending_reason}")

    active = self._live_broker_ids_with_allocations(broker_ids, broker_allocs)
    if not active:
        raise LiveOrderExecutionError(
            f"{action_label} for {sym} has no assigned broker accounts"
        )

    if side == "SELL":
        await _preflight_sell_evidence(self, sym, quantity, active)

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
    missing_brokers = sorted(expected - observed)
    missing_order_ids = [
        str(result.get("broker_id") or "unknown")
        for result in results
        if str(result.get("status") or "").lower()
        in (
            self._BROKER_CONFIRMED_STATUSES
            | self._BROKER_PARTIAL_STATUSES
            | self._BROKER_PENDING_STATUSES
        )
        and not _result_order_id(self, result)
    ]
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
    order_ids = [
        _result_order_id(self, result)
        for result in results
        if _result_order_id(self, result)
    ]

    if missing_order_ids:
        raise LiveOrderExecutionError(
            f"{action_label} for {sym} missing broker order identifier for {missing_order_ids}; "
            "broker reconciliation is required before retry"
        )

    if pending:
        raise LiveOrderExecutionError(
            f"{action_label} for {sym} is pending fill/reconciliation; "
            f"filled={filled_qty:.8f}/{parent_qty:.8f}, "
            f"broker_order_ids={order_ids}"
        )

    if missing_brokers or failed:
        raise LiveOrderExecutionError(
            f"{action_label} for {sym} is not fully filled; "
            f"filled={filled_qty:.8f}/{parent_qty:.8f}, "
            f"missing={missing_brokers}, failed={len(failed)}, "
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


BrokerExecutionMixin._place_live_order_or_raise = _place_live_order_risk_first
