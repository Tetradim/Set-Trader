"""Expose live connectivity only for adapters with submit/status reconciliation."""

from __future__ import annotations

from brokers.registry import BROKER_REGISTRY
from brokers.tradier_adapter import TradierAdapter


async def _tradier_get_order_status(self, broker_order_id: str) -> dict:
    if not broker_order_id:
        return {"status": "error", "error": "missing broker order id"}
    session = await self._get_session()
    async with session.get(
        f"https://api.tradier.com/v1/accounts/{self._acct()}/orders/{broker_order_id}",
        headers=self._headers(),
    ) as response:
        data = await response.json()
        if response.status != 200:
            errors = data.get("errors") if isinstance(data, dict) else None
            error = errors.get("error") if isinstance(errors, dict) else None
            if isinstance(error, dict):
                reason = error.get("description") or error.get("message")
            else:
                reason = error
            return {
                "status": "error",
                "broker_order_id": broker_order_id,
                "error": str(reason or f"HTTP {response.status}"),
            }

        order = data.get("order") if isinstance(data, dict) else {}
        if not isinstance(order, dict):
            order = {}
        raw_status = str(order.get("status") or "unknown").lower()
        status = {
            "partially_filled": "partially_filled",
            "canceled": "canceled",
            "cancelled": "canceled",
            "open": "submitted",
            "pending": "submitted",
        }.get(raw_status, raw_status)
        try:
            filled_quantity = float(
                order.get("exec_quantity")
                or order.get("filled_quantity")
                or 0
            )
        except (TypeError, ValueError):
            filled_quantity = 0.0
        try:
            filled_price = float(
                order.get("avg_fill_price")
                or order.get("last_fill_price")
                or 0
            )
        except (TypeError, ValueError):
            filled_price = 0.0
        return {
            "status": status,
            "broker_order_id": str(order.get("id") or broker_order_id),
            "filled_quantity": filled_quantity,
            "filled_price": filled_price,
            "error": str(order.get("reason_description") or ""),
        }


TradierAdapter.get_order_status = _tradier_get_order_status

# These adapters can submit orders but do not yet expose a verified cumulative
# order-status contract in this codebase. Treating them as production-live would
# allow accepted orders to become unrecoverable after a restart.
for broker_id in (
    "ibkr",
    "tradestation",
    "robinhood",
    "webull",
    "wealthsimple",
):
    info = BROKER_REGISTRY.get(broker_id)
    if info is None:
        continue
    info.supported = False
    info.readiness = "unavailable"
    info.readiness_note = (
        "Live connectivity disabled until cumulative order status, partial fills, "
        "cancellation, and restart reconciliation are implemented and certified."
    )
