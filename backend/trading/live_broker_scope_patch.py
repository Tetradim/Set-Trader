"""Ensure sell reconciliation includes assigned brokers even at zero future allocation."""

from trading.broker_execution import BrokerExecutionMixin


def _assigned_live_broker_ids(self, broker_ids: list, broker_allocs: dict) -> list:
    """Return assigned broker accounts in stable order.

    Buy planning still skips zero-dollar allocations. Sell planning must inspect
    every assigned broker because an account may retain holdings after its
    future allocation is reduced to zero.
    """
    return list(dict.fromkeys(str(broker_id) for broker_id in (broker_ids or []) if broker_id))


BrokerExecutionMixin._live_broker_ids_with_allocations = _assigned_live_broker_ids
