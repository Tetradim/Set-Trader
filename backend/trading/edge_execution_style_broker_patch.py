"""Carry Pulse's selected Edge execution style into concrete broker orders."""
from __future__ import annotations

import asyncio
from typing import Any

from broker_manager import BrokerConnectionManager
from brokers import BrokerOrder


_ORIGINAL_PLACE_ORDERS = BrokerConnectionManager.place_orders_for_ticker
_PATCH_MARKER = "_pulse_edge_execution_style_broker_v1"


async def _place_orders_with_execution_style(
    self: BrokerConnectionManager,
    broker_ids: list[str],
    allocations: dict,
    order_template: dict,
) -> list[dict]:
    template = dict(order_template or {})
    tasks = []
    valid_brokers = []

    for broker_id in broker_ids:
        adapter = self.get_adapter(broker_id)
        allocation = allocations.get(broker_id, 0)
        if not adapter:
            # Preserve the manager's established failover and alert behavior for
            # disconnected brokers by falling back to the original implementation.
            return await _ORIGINAL_PLACE_ORDERS(self, broker_ids, allocations, template)
        if allocation <= 0:
            continue

        valid_brokers.append(broker_id)
        price = max(float(template.get("price", 1) or 1), 0.01)
        order = BrokerOrder(
            symbol=template["symbol"],
            side=self._order_side(template["side"]),
            order_type=self._order_type(template["order_type"]),
            quantity=template.get("quantity", 0) or round(allocation / price, 4),
            limit_price=template.get("limit_price"),
            stop_price=template.get("stop_price"),
            time_in_force=str(template.get("time_in_force") or "day"),
            timeout_seconds=(
                max(1, int(template["timeout_seconds"]))
                if template.get("timeout_seconds") is not None else None
            ),
            execution_style=str(template.get("execution_style") or ""),
        )
        tasks.append(self._place_single(adapter, broker_id, order, template.get("symbol", "")))

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    output: list[dict[str, Any]] = []
    for broker_id, result in zip(valid_brokers, results):
        if isinstance(result, Exception):
            self._failed[broker_id] = str(result)
            payload = {"broker_id": broker_id, "status": "error", "error": str(result)}
        else:
            payload = {"broker_id": broker_id, **result}
        payload.update(
            {
                "execution_style": template.get("execution_style"),
                "requested_order_type": template.get("order_type"),
                "limit_price": template.get("limit_price"),
                "stop_price": template.get("stop_price"),
                "timeout_seconds": template.get("timeout_seconds"),
                "arrival_price": template.get("price"),
                "execution_style_selection": template.get("execution_style_selection"),
            }
        )
        output.append(payload)
    return output


if not getattr(BrokerConnectionManager.place_orders_for_ticker, _PATCH_MARKER, False):
    setattr(_place_orders_with_execution_style, _PATCH_MARKER, True)
    BrokerConnectionManager.place_orders_for_ticker = _place_orders_with_execution_style
