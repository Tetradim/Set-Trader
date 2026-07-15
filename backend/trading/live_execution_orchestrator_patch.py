"""Compose risk, executable quotes, sizing and broker-truth submission once.

This is the final live-order wrapper. It deliberately calls the risk-first
orchestrator directly after quote enrichment rather than stacking a second risk
check through another wrapper.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import math
from typing import Any

import deps
from brokers.alpaca_adapter import AlpacaAdapter
from brokers.tradier_adapter import TradierAdapter
from trading import live_execution_quality_patch as quality
from trading import live_pretrade_patch as pretrade
from trading.broker_execution import BrokerExecutionMixin, LiveOrderExecutionError


_QUOTE_REQUIRED_BROKERS = {"alpaca", "tradier"}
_REAL_ADAPTER_TYPES = (AlpacaAdapter, TradierAdapter)
_original_quantity_increment = quality._quantity_increment


def _quantity_increment_for_known_broker(broker_id: str) -> Decimal:
    """Apply restrictions only to brokers whose contract is known here.

    Generic broker doubles and future adapters preserve eight-decimal quantity
    precision. Tradier remains whole-share; Alpaca retains its configured
    fractional increment.
    """
    broker = str(broker_id or "").lower()
    if broker in _QUOTE_REQUIRED_BROKERS:
        return _original_quantity_increment(broker)
    return Decimal("0.00000001")


def _number(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _source_epoch(value: Any) -> float:
    if isinstance(value, (int, float)):
        number = float(value)
        while number > 10_000_000_000:
            number /= 1000.0
        return number
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        number = float(raw)
        while number > 10_000_000_000:
            number /= 1000.0
        return number
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _engine_is_live(self) -> bool:
    getter = getattr(self, "get_trading_mode", None)
    if callable(getter):
        try:
            return str(getter() or "").lower() == "live"
        except Exception:
            return False
    return False


async def _risk_check_once(
    self,
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    broker_ids: list[str],
    broker_allocs: dict,
    action_label: str,
) -> None:
    if side == "BUY" and quantity <= 0 and price > 0:
        quantity = round(
            sum(
                max(0.0, _number(broker_allocs.get(broker_id)))
                for broker_id in broker_ids
            )
            / price,
            8,
        )
    if quantity <= 0:
        raise LiveOrderExecutionError(
            f"{action_label} for {symbol} has no positive requested quantity"
        )
    if hasattr(self, "pre_trade_check"):
        allowed, reason = await self.pre_trade_check(symbol, side, quantity, price)
        if not allowed:
            raise LiveOrderExecutionError(reason)


def _production_quote_adapters(manager: Any, broker_ids: list[str], action_label: str, symbol: str):
    production_manager = manager.__class__.__name__ == "BrokerConnectionManager"
    selected: list[tuple[str, Any]] = []
    for broker_id in broker_ids:
        broker = str(broker_id or "").lower()
        if broker not in _QUOTE_REQUIRED_BROKERS:
            continue
        adapter = manager.get_adapter(broker_id)
        if isinstance(adapter, _REAL_ADAPTER_TYPES):
            selected.append((broker_id, adapter))
            continue
        if production_manager:
            if adapter is None:
                raise LiveOrderExecutionError(
                    f"{action_label} for {symbol} blocked: assigned broker {broker_id} is not connected"
                )
            raise LiveOrderExecutionError(
                f"{action_label} for {symbol} blocked: {broker_id} is not using its certified live adapter"
            )
        # Unit-test and integration doubles are intentionally not treated as a
        # certified live market-data adapter merely because their ID is alpaca.
    return selected


async def _place_live_order_composed(
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
    order_template = dict(order_template or {})
    if not self._should_place_broker_orders(broker_ids):
        return await pretrade._place_live_order_risk_first(
            self,
            sym=sym,
            broker_ids=broker_ids,
            broker_allocs=broker_allocs,
            order_template=order_template,
            action_label=action_label,
        )

    side, quantity, reference_price = self._live_pretrade_values(
        order_template,
        broker_allocs,
    )
    await _risk_check_once(
        self,
        symbol=sym,
        side=side,
        quantity=quantity,
        price=reference_price,
        broker_ids=broker_ids,
        broker_allocs=broker_allocs,
        action_label=action_label,
    )
    order_template["_risk_prechecked"] = True

    # Paper execution, legacy broker doubles and non-production broker IDs retain
    # the existing contract. Production live Alpaca/Tradier paths must supply an
    # executable bid/ask quote before quantity planning or broker submission.
    manager = getattr(deps, "broker_mgr", None)
    if not _engine_is_live(self) or not hasattr(manager, "get_adapter"):
        return await pretrade._place_live_order_risk_first(
            self,
            sym=sym,
            broker_ids=broker_ids,
            broker_allocs=broker_allocs,
            order_template=order_template,
            action_label=action_label,
        )

    active = self._live_broker_ids_with_allocations(broker_ids, broker_allocs)
    quote_adapters = _production_quote_adapters(
        manager,
        active,
        action_label,
        sym,
    )
    if not quote_adapters:
        return await pretrade._place_live_order_risk_first(
            self,
            sym=sym,
            broker_ids=broker_ids,
            broker_allocs=broker_allocs,
            order_template=order_template,
            action_label=action_label,
        )

    snapshots: list[dict] = []
    for broker_id, adapter in quote_adapters:
        getter = getattr(adapter, "get_quote_snapshot", None)
        if not callable(getter):
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} blocked: {broker_id} lacks executable bid/ask quote support"
            )
        try:
            raw = dict(await getter(sym))
            source_epoch = _source_epoch(raw.get("source_timestamp"))
            if source_epoch > 0:
                raw["received_at_epoch"] = source_epoch
            snapshots.append(quality._validated_quote(raw))
        except LiveOrderExecutionError:
            raise
        except Exception as exc:
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} blocked: {broker_id} quote lookup failed: {exc}"
            ) from exc

    executable_price = (
        max(snapshot["ask"] for snapshot in snapshots)
        if side == "BUY"
        else min(snapshot["bid"] for snapshot in snapshots)
    )
    order_template.update(
        {
            "price": executable_price,
            "execution_quotes": snapshots,
            "quote_checked_at": quality._iso_now(),
        }
    )
    return await pretrade._place_live_order_risk_first(
        self,
        sym=sym,
        broker_ids=broker_ids,
        broker_allocs=broker_allocs,
        order_template=order_template,
        action_label=action_label,
    )


quality._quantity_increment = _quantity_increment_for_known_broker
BrokerExecutionMixin._place_live_order_or_raise = _place_live_order_composed
