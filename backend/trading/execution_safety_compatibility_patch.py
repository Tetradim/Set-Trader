"""Preserve established execution ABI while retaining the safety gateway."""
from __future__ import annotations

from typing import Any

from risk_controls import OrderRestriction
from trading import execution_order_safety_patch as safety
from trading.broker_execution import BrokerExecutionMixin, LiveOrderExecutionError


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _enforce_with_public_pretrade_contract(
    self,
    *,
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    broker_ids: list[str],
) -> None:
    """Run the public pre-trade hook exactly once, then supplemental controls."""
    if hasattr(self, "pre_trade_check"):
        allowed, reason = await self.pre_trade_check(
            symbol, side, quantity, price
        )
        if not allowed:
            raise LiveOrderExecutionError(reason)

    controls = self.risk_controls
    symbol = str(symbol or "").upper()
    side = str(side or "").upper()
    order_value = max(0.0, quantity * price)

    # These controls were not part of the legacy pre_trade_check implementation.
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

    # Re-evaluate projections with the corrected notional/quantity unit model.
    if hasattr(self, "ensure_symbol_exposure_limit"):
        self.ensure_symbol_exposure_limit(symbol)
    for level, level_id in (("portfolio", "global"), ("symbol", symbol)):
        result = safety.projected_risk_result(
            self,
            level=level,
            level_id=level_id,
            side=side,
            quantity=quantity,
            price=price,
        )
        if not result.is_allowed:
            raise LiveOrderExecutionError(f"RISK REJECTED: {result.message}")


async def _place_live_order_composed(
    self,
    *,
    sym: str,
    broker_ids: list,
    broker_allocs: dict,
    order_template: dict,
    action_label: str,
) -> list[dict]:
    return await safety.place_live_order_safely(
        self,
        sym=sym,
        broker_ids=broker_ids,
        broker_allocs=broker_allocs,
        order_template=order_template,
        action_label=action_label,
    )


safety.enforce_execution_risk = _enforce_with_public_pretrade_contract
BrokerExecutionMixin._place_live_order_or_raise = _place_live_order_composed
