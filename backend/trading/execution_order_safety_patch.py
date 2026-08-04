"""Final live order gateway with partial-leg sizing and complete risk checks."""
from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any

import deps
from risk_controls import OrderRestriction, RiskCheckResult
from trading import live_execution_orchestrator_patch as orchestrator
from trading import live_execution_quality_patch as quality
from trading import live_pretrade_patch as pretrade
from trading.broker_execution import BrokerExecutionMixin, LiveOrderExecutionError
from trading.risk_safety_patch import effective_notional_limit


_PARTIAL_ACTION = re.compile(r"^PARTIAL_(BUY|SELL)_LEG_(\d+)$")


def _number(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def partial_contexts(self) -> dict[str, dict[str, Any]]:
    contexts = getattr(self, "_partial_execution_contexts", None)
    if contexts is None:
        contexts = {}
        self._partial_execution_contexts = contexts
    return contexts


async def prepare_partial_order(
    self,
    *,
    sym: str,
    broker_ids: list[str],
    broker_allocs: dict,
    order_template: dict,
    action_label: str,
) -> tuple[dict, dict]:
    match = _PARTIAL_ACTION.match(str(action_label or "").upper())
    if not match:
        return broker_allocs, order_template

    side, raw_index = match.groups()
    leg_index = int(raw_index) - 1
    context_key = f"{sym.upper()}:{side}"
    partial_contexts(self)[context_key] = {
        "position": deepcopy((self._positions or {}).get(sym, {}) or {}),
        "leg_index": leg_index,
        "side": side,
    }

    if side != "BUY":
        return broker_allocs, order_template

    ticker = await deps.db.tickers.find_one(
        {"symbol": sym}, {"_id": 0, "buy_legs": 1}
    )
    legs = list((ticker or {}).get("buy_legs") or [])
    if leg_index < 0 or leg_index >= len(legs):
        partial_contexts(self).pop(context_key, None)
        raise LiveOrderExecutionError(
            f"{action_label} for {sym} has no matching configured buy leg"
        )

    allocation_pct = max(0.0, _number(legs[leg_index].get("alloc_pct")))
    price = max(0.0, _number(order_template.get("price")))
    total_allocation = sum(
        max(0.0, _number((broker_allocs or {}).get(broker_id)))
        for broker_id in broker_ids
    )
    quantity = (
        total_allocation * allocation_pct / 100.0 / price
        if price > 0
        else 0.0
    )
    if quantity <= 0:
        partial_contexts(self).pop(context_key, None)
        raise LiveOrderExecutionError(
            f"{action_label} for {sym} has no positive leg quantity"
        )

    scaled_allocations = {
        broker_id: round(
            max(0.0, _number((broker_allocs or {}).get(broker_id)))
            * allocation_pct
            / 100.0,
            8,
        )
        for broker_id in broker_ids
    }
    updated_template = dict(order_template)
    updated_template["quantity"] = round(quantity, 8)
    updated_template["partial_leg_index"] = leg_index
    return scaled_allocations, updated_template


def projected_risk_result(
    self,
    *,
    level: str,
    level_id: str,
    side: str,
    quantity: float,
    price: float,
) -> RiskCheckResult:
    controls = self.risk_controls
    limit = controls.get_exposure_limit(level, level_id)
    if not limit or not limit.is_enabled:
        return RiskCheckResult(is_allowed=True)
    if str(side or "").upper() != "BUY":
        return RiskCheckResult(is_allowed=True)

    projected_notional = max(
        0.0, _number(limit.current_notional) + max(0.0, quantity * price)
    )
    max_notional = effective_notional_limit(limit)
    if max_notional > 0 and projected_notional > max_notional:
        return RiskCheckResult(
            is_allowed=False,
            restriction=OrderRestriction.HARD_BLOCK,
            message=(
                f"Projected {level} notional limit exceeded: "
                f"${projected_notional:.2f} > ${max_notional:.2f}"
            ),
            rejected_fields={"notional": projected_notional},
        )

    max_quantity = max(0.0, _number(getattr(limit, "max_quantity", 0)))
    projected_quantity = max(
        0.0, _number(limit.current_position) + quantity
    )
    if max_quantity > 0 and projected_quantity > max_quantity:
        return RiskCheckResult(
            is_allowed=False,
            restriction=OrderRestriction.HARD_BLOCK,
            message=(
                f"Projected {level} quantity limit exceeded: "
                f"{projected_quantity:.8f} > {max_quantity:.8f}"
            ),
            rejected_fields={"position": projected_quantity},
        )

    return controls.check_exposure_limit(level, level_id)


async def enforce_execution_risk(
    self,
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    broker_ids: list[str],
) -> None:
    if bool(getattr(self, "_dry_run_mode", False)):
        raise LiveOrderExecutionError("DRY-RUN MODE: No real orders allowed")

    controls = self.risk_controls
    symbol = str(symbol or "").upper()
    side = str(side or "").upper()
    order_value = max(0.0, quantity * price)

    global_switch = controls.get_kill_switch("global", "global")
    if global_switch and global_switch.is_active:
        raise LiveOrderExecutionError(
            f"GLOBAL KILL SWITCH ACTIVE: {global_switch.reason}"
        )

    if not controls.is_symbol_allowed(symbol):
        raise LiveOrderExecutionError(f"Symbol {symbol} is restricted")

    fat_finger = controls.check_fat_finger(symbol, order_value)
    if not fat_finger.is_allowed:
        raise LiveOrderExecutionError(fat_finger.message)

    for broker_id in broker_ids:
        broker_switch = controls.get_kill_switch("broker", str(broker_id))
        if broker_switch and broker_switch.is_active:
            raise LiveOrderExecutionError(
                f"BROKER {broker_id} KILL SWITCH ACTIVE: "
                f"{broker_switch.reason}"
            )

    if hasattr(self, "ensure_symbol_exposure_limit"):
        self.ensure_symbol_exposure_limit(symbol)
    for level, level_id in (("portfolio", "global"), ("symbol", symbol)):
        result = projected_risk_result(
            self,
            level=level,
            level_id=level_id,
            side=side,
            quantity=quantity,
            price=price,
        )
        if not result.is_allowed:
            raise LiveOrderExecutionError(f"RISK REJECTED: {result.message}")


async def place_live_order_safely(
    self,
    *,
    sym: str,
    broker_ids: list,
    broker_allocs: dict,
    order_template: dict,
    action_label: str,
) -> list[dict]:
    broker_ids = list(broker_ids or [])
    broker_allocs = dict(broker_allocs or {})
    order_template = dict(order_template or {})
    if not self._should_place_broker_orders(broker_ids):
        return []

    broker_allocs, order_template = await prepare_partial_order(
        self,
        sym=sym,
        broker_ids=broker_ids,
        broker_allocs=broker_allocs,
        order_template=order_template,
        action_label=action_label,
    )
    partial_match = _PARTIAL_ACTION.match(str(action_label or "").upper())
    partial_key = (
        f"{sym.upper()}:{partial_match.group(1)}" if partial_match else None
    )

    try:
        side, quantity, reference_price = self._live_pretrade_values(
            order_template, broker_allocs
        )
        if side == "BUY" and quantity <= 0 and reference_price > 0:
            quantity = round(
                sum(
                    max(0.0, _number(broker_allocs.get(broker_id)))
                    for broker_id in broker_ids
                )
                / reference_price,
                8,
            )
        if quantity <= 0:
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} has no positive requested quantity"
            )

        active = self._live_broker_ids_with_allocations(
            broker_ids, broker_allocs
        )
        if not active:
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} has no assigned broker accounts"
            )

        await enforce_execution_risk(
            self,
            symbol=sym,
            side=side,
            quantity=quantity,
            price=reference_price,
            broker_ids=active,
        )
        order_template["_risk_prechecked"] = True

        manager = getattr(deps, "broker_mgr", None)
        if not orchestrator._engine_is_live(self) or not hasattr(
            manager, "get_adapter"
        ):
            return await pretrade._place_live_order_risk_first(
                self,
                sym=sym,
                broker_ids=broker_ids,
                broker_allocs=broker_allocs,
                order_template=order_template,
                action_label=action_label,
            )

        quote_adapters = orchestrator._production_quote_adapters(
            manager, active, action_label, sym
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
                    f"{action_label} for {sym} blocked: {broker_id} "
                    "lacks executable bid/ask quote support"
                )
            try:
                raw = dict(await getter(sym))
                source_epoch = orchestrator._source_epoch(
                    raw.get("source_timestamp")
                )
                if source_epoch > 0:
                    raw["received_at_epoch"] = source_epoch
                snapshots.append(quality._validated_quote(raw))
            except LiveOrderExecutionError:
                raise
            except Exception as exc:
                raise LiveOrderExecutionError(
                    f"{action_label} for {sym} blocked: {broker_id} "
                    f"quote lookup failed: {exc}"
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
    except Exception:
        if partial_key:
            partial_contexts(self).pop(partial_key, None)
        raise


BrokerExecutionMixin._place_live_order_or_raise = place_live_order_safely
