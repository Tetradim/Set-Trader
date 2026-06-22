import deps


class LiveOrderExecutionError(RuntimeError):
    """Raised when a live broker order did not produce confirmed broker results."""


class BrokerExecutionMixin:
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

    def _broker_result_confirmed(self, result: dict) -> bool:
        if not result:
            return False
        if str(result.get("error") or "").strip():
            return False
        status = str(result.get("status") or "").lower()
        return bool(status) and status not in self._BROKER_FAILURE_STATUSES

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

        if self.is_paper_trading() or not broker_ids:
            return []

        active_broker_ids = self._live_broker_ids_with_allocations(broker_ids, broker_allocs)
        if not active_broker_ids:
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} has broker IDs but no positive broker allocations"
            )

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
        failed_results = [
            result for result in broker_results
            if not self._broker_result_confirmed(result)
        ]
        if missing_brokers or failed_results:
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} was not confirmed by all live brokers "
                f"(missing={missing_brokers}, failed={len(failed_results)})"
            )

        return broker_results
