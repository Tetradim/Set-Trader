import os

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

        if hasattr(self, "pre_trade_check"):
            side, quantity, price = self._live_pretrade_values(order_template, broker_allocs)
            allowed, reason = await self.pre_trade_check(sym, side, quantity, price)
            if not allowed:
                raise LiveOrderExecutionError(reason)

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
            if not self._broker_result_confirmed(result)
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

        return broker_results
