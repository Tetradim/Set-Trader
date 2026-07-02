import os
from datetime import datetime, timedelta, timezone

import deps


class LiveOrderExecutionError(RuntimeError):
    """Raised when a live broker order did not produce confirmed broker results."""


class BrokerExecutionMixin:
    _BROKER_CONFIRMED_STATUSES = {
        "complete",
        "completed",
        "done",
        "executed",
        "filled",
    }
    _BROKER_PARTIAL_STATUSES = {
        "partial",
        "partially-filled",
        "partially_filled",
    }
    _BROKER_PENDING_STATUSES = {
        "accepted",
        "held",
        "new",
        "pending",
        "pending_cancel",
        "pending_new",
        "pending_replace",
    }
    _BROKER_FAILURE_STATUSES = {
        "cancelled",
        "canceled",
        "circuit_open",
        "duplicate",
        "error",
        "expired",
        "failed",
        "rejected",
    }

    def _live_broker_ids_with_allocations(self, broker_ids: list, broker_allocs: dict) -> list:
        active = []
        for broker_id in broker_ids or []:
            try:
                alloc = float((broker_allocs or {}).get(broker_id, 0) or 0)
            except (TypeError, ValueError):
                alloc = 0
            if alloc > 0:
                active.append(broker_id)
        return active

    def _broker_paper_execution_enabled(self) -> bool:
        if bool(getattr(self, "_dry_run_mode", False)):
            return False
        return os.getenv("SENTINEL_PULSE_ENABLE_BROKER_PAPER_EXECUTION", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _should_place_broker_orders(self, broker_ids: list) -> bool:
        if not broker_ids:
            return False
        if self.is_paper_trading():
            return self._broker_paper_execution_enabled()
        return True

    def _broker_result_confirmed(self, result: dict) -> bool:
        if not result:
            return False
        if str(result.get("error") or "").strip():
            return False
        status = str(result.get("status") or "").lower()
        has_order_identifier = bool(self._broker_result_order_identifier(result))
        if status in self._BROKER_PARTIAL_STATUSES:
            return has_order_identifier and self._broker_result_filled_quantity(result) > 0
        return status in self._BROKER_CONFIRMED_STATUSES and has_order_identifier

    def _broker_result_pending(self, result: dict) -> bool:
        if not result:
            return False
        if str(result.get("error") or "").strip():
            return False
        status = str(result.get("status") or "").lower()
        return status in self._BROKER_PENDING_STATUSES and bool(self._broker_result_order_identifier(result))

    def _broker_result_filled_quantity(self, result: dict) -> float:
        if not result:
            return 0.0
        for key in ("filled_quantity", "filled_qty"):
            try:
                quantity = float(result.get(key) or 0)
            except (TypeError, ValueError):
                quantity = 0.0
            if quantity > 0:
                return quantity
        return 0.0

    def _broker_results_filled_quantity(self, broker_results: list[dict]) -> float:
        total = 0.0
        for result in broker_results or []:
            total += self._broker_result_filled_quantity(result)
        return round(total, 8)

    def _broker_result_order_identifier(self, result: dict) -> str:
        if not result:
            return ""
        for key in ("broker_order_id", "order_id", "external_id"):
            value = str(result.get(key) or "").strip()
            if value:
                return value
        return ""

    def _triggered_exit_order_template(
        self,
        *,
        symbol: str,
        order_type: str,
        price: float,
        quantity: float,
    ) -> dict:
        """Build an immediate broker exit after a local stop/trailing trigger fires."""
        normalized = str(order_type or "limit").strip().lower()
        if normalized == "market":
            return {
                "symbol": symbol,
                "side": "SELL",
                "order_type": "MARKET",
                "price": price,
                "quantity": quantity,
        }
        return {
            "symbol": symbol,
            "side": "SELL",
            "order_type": "LIMIT",
            "price": price,
            "quantity": quantity,
            "limit_price": price,
        }

    async def _broker_position_quantity(self, broker_id: str, symbol: str) -> float | None:
        adapter = deps.broker_mgr.get_adapter(broker_id) if hasattr(deps.broker_mgr, "get_adapter") else None
        if not adapter or not hasattr(adapter, "get_positions"):
            return None
        positions = await adapter.get_positions()
        for position in positions:
            if str(getattr(position, "symbol", "")).upper() == symbol.upper():
                try:
                    return float(getattr(position, "quantity", 0) or 0)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    async def _broker_open_sell_quantity(self, broker_id: str, symbol: str) -> float:
        adapter = deps.broker_mgr.get_adapter(broker_id) if hasattr(deps.broker_mgr, "get_adapter") else None
        if not adapter or not hasattr(adapter, "get_open_orders"):
            return 0.0
        total = 0.0
        for order in await adapter.get_open_orders():
            if str(getattr(order, "symbol", "")).upper() != symbol.upper():
                continue
            side = getattr(order, "side", "")
            side_value = getattr(side, "value", side)
            if str(side_value).upper() != "SELL":
                continue
            try:
                total += max(0.0, float(getattr(order, "quantity", 0) or 0))
            except (TypeError, ValueError):
                continue
        return round(total, 8)

    async def _verify_live_sell_quantities(self, sym: str, quantity: float, broker_ids: list[str]) -> None:
        if quantity <= 0:
            return
        shortages = []
        for broker_id in broker_ids:
            actual_qty = await self._broker_position_quantity(broker_id, sym)
            if actual_qty is None:
                continue
            reserved_qty = await self._broker_open_sell_quantity(broker_id, sym)
            available_qty = max(0.0, actual_qty - reserved_qty)
            if available_qty + 1e-8 < quantity:
                if reserved_qty > 0:
                    shortages.append(
                        f"{broker_id} holds {actual_qty:.4f}, has {reserved_qty:.4f} already in open sell orders, needs {quantity:.4f}"
                    )
                else:
                    shortages.append(f"{broker_id} holds {actual_qty:.4f}, needs {quantity:.4f}")
        if shortages:
            raise LiveOrderExecutionError(
                f"SELL for {sym} blocked: broker position is insufficient ({'; '.join(shortages)})"
            )

    def _live_order_intent_key(self, sym: str, side: str, quantity: float, order_type: str) -> str:
        return f"{sym.upper()}:{side.upper()}:{str(order_type or '').upper()}"

    def _pending_live_order_intents(self) -> dict:
        if not hasattr(self, "_pending_live_order_intents_cache"):
            self._pending_live_order_intents_cache = {}
        return self._pending_live_order_intents_cache

    def _clear_expired_live_order_intents(self, ttl_seconds: int = 120) -> None:
        now = datetime.now(timezone.utc)
        cache = self._pending_live_order_intents()
        expired = []
        for key, value in cache.items():
            created_at = value.get("created_at")
            if isinstance(created_at, datetime) and now - created_at > timedelta(seconds=ttl_seconds):
                expired.append(key)
        for key in expired:
            cache.pop(key, None)

    def _pending_live_order_reason(self, intent_key: str) -> str:
        self._clear_expired_live_order_intents()
        pending = self._pending_live_order_intents().get(intent_key)
        if not pending:
            return ""
        order_ids = ", ".join(pending.get("order_ids") or [])
        return f"broker order is still pending fill ({order_ids})"

    def _mark_live_order_pending(self, intent_key: str, broker_results: list[dict]) -> None:
        order_ids = [
            self._broker_result_order_identifier(result)
            for result in broker_results
            if self._broker_result_pending(result)
        ]
        self._pending_live_order_intents()[intent_key] = {
            "created_at": datetime.now(timezone.utc),
            "order_ids": [order_id for order_id in order_ids if order_id],
        }

    def _clear_live_order_pending(self, intent_key: str) -> None:
        self._pending_live_order_intents().pop(intent_key, None)

    def _live_pretrade_values(self, order_template: dict, broker_allocs: dict) -> tuple[str, float, float]:
        order_template = order_template or {}
        side = str(order_template.get("side") or "").upper()
        try:
            price = float(order_template.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0

        try:
            quantity = float(order_template.get("quantity") or 0)
        except (TypeError, ValueError):
            quantity = 0.0

        if quantity <= 0 and side == "BUY" and price > 0:
            total_allocation = 0.0
            for allocation in (broker_allocs or {}).values():
                try:
                    total_allocation += max(0.0, float(allocation or 0))
                except (TypeError, ValueError):
                    continue
            quantity = round(total_allocation / price, 4)

        return side, quantity, price

    async def _place_live_order_or_raise(
        self,
        *,
        sym: str,
        broker_ids: list,
        broker_allocs: dict,
        order_template: dict,
        action_label: str,
    ) -> list[dict]:
        """Place a live order and require every allocated broker to confirm it."""
        broker_ids = broker_ids or []
        broker_allocs = broker_allocs or {}

        if not self._should_place_broker_orders(broker_ids):
            return []

        active_broker_ids = self._live_broker_ids_with_allocations(broker_ids, broker_allocs)
        if not active_broker_ids:
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} has broker IDs but no positive broker allocations"
            )

        side, quantity, price = self._live_pretrade_values(order_template, broker_allocs)
        order_type = str((order_template or {}).get("order_type") or "").upper()
        intent_key = self._live_order_intent_key(sym, side, quantity, order_type)
        pending_reason = self._pending_live_order_reason(intent_key)
        if pending_reason:
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} skipped: {pending_reason}"
            )

        if hasattr(self, "pre_trade_check"):
            allowed, reason = await self.pre_trade_check(sym, side, quantity, price)
            if not allowed:
                raise LiveOrderExecutionError(reason)
            if side == "SELL":
                await self._verify_live_sell_quantities(sym, quantity, active_broker_ids)

        broker_results = await deps.broker_mgr.place_orders_for_ticker(
            broker_ids=broker_ids,
            allocations=broker_allocs,
            order_template=order_template,
        )
        if not broker_results:
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} produced no broker order results"
            )

        result_broker_ids = {result.get("broker_id") for result in broker_results if result.get("broker_id")}
        missing_brokers = [broker_id for broker_id in active_broker_ids if broker_id not in result_broker_ids]
        missing_order_identifiers = [
            result.get("broker_id")
            for result in broker_results
            if str(result.get("status") or "").lower()
            in self._BROKER_CONFIRMED_STATUSES | self._BROKER_PARTIAL_STATUSES
            and not self._broker_result_order_identifier(result)
        ]
        failed_results = [
            result for result in broker_results
            if not self._broker_result_confirmed(result) and not self._broker_result_pending(result)
        ]
        pending_results = [
            result for result in broker_results
            if self._broker_result_pending(result)
        ]
        if missing_brokers or failed_results:
            details = f"missing={missing_brokers}, failed={len(failed_results)}"
            if missing_order_identifiers:
                details = (
                    f"{details}, missing broker order identifier="
                    f"{missing_order_identifiers}"
                )
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} was not confirmed by all live brokers "
                f"({details})"
            )

        if pending_results:
            self._mark_live_order_pending(intent_key, pending_results)
            order_ids = [
                self._broker_result_order_identifier(result)
                for result in pending_results
                if self._broker_result_order_identifier(result)
            ]
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} submitted to broker and is pending fill "
                f"(broker_order_ids={order_ids})"
            )

        self._clear_live_order_pending(intent_key)
        return broker_results
