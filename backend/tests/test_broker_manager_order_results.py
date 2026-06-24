import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from broker_manager import BrokerConnectionManager  # noqa: E402
from brokers.base import BrokerOrder, OrderSide, OrderType  # noqa: E402


class _AuditService:
    async def log_broker_api(self, *_args, **_kwargs):
        pass


class _BrokerResilience:
    async def before_call(self, *_args, **_kwargs):
        pass

    async def record_success(self, *_args, **_kwargs):
        pass

    async def record_failure(self, *_args, **_kwargs):
        pass


class _Adapter:
    def __init__(self):
        self.orders = []

    async def place_order(self, order):
        self.orders.append(order)
        return BrokerOrder(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            broker_order_id="broker-order-123",
            status="filled",
            filled_price=50.25,
        )


class _UnexpectedAdapter:
    async def place_order(self, _order):
        raise AssertionError("duplicate idempotency keys must not hit broker adapters")


class _RejectedAdapter:
    async def place_order(self, order):
        return BrokerOrder(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            broker_order_id="",
            status="rejected",
            error="client_order_id must be unique",
        )


class _PartialAdapter:
    async def place_order(self, order):
        return BrokerOrder(
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=order.quantity,
            broker_order_id="broker-order-partial",
            status="partially_filled",
            filled_price=50.25,
            filled_quantity=0.5,
        )


def _patch_runtime_services(monkeypatch):
    import audit_service
    import resilience

    monkeypatch.setattr(audit_service, "audit_service", _AuditService())
    monkeypatch.setattr(resilience, "broker_resilience", _BrokerResilience())


def _order(idempotency_key=""):
    return BrokerOrder(
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        idempotency_key=idempotency_key,
    )


def test_place_single_returns_canonical_broker_order_identifier(monkeypatch):
    _patch_runtime_services(monkeypatch)
    manager = BrokerConnectionManager(db=None)

    result = asyncio.run(
        manager._place_single(_Adapter(), "alpaca", _order(), "SPY")
    )

    assert result["broker_order_id"] == "broker-order-123"
    assert result["order_id"] == "broker-order-123"


def test_place_orders_normalizes_string_order_template_to_broker_enums(monkeypatch):
    _patch_runtime_services(monkeypatch)
    adapter = _Adapter()
    manager = BrokerConnectionManager(db=None)
    manager._adapters["alpaca"] = adapter

    result = asyncio.run(
        manager.place_orders_for_ticker(
            broker_ids=["alpaca"],
            allocations={"alpaca": 25.0},
            order_template={
                "symbol": "SOUN",
                "side": "BUY",
                "order_type": "MARKET",
                "price": 25.0,
            },
        )
    )

    assert result[0]["status"] == "filled"
    assert adapter.orders[0].side is OrderSide.BUY
    assert adapter.orders[0].order_type is OrderType.MARKET


def test_duplicate_order_result_returns_canonical_broker_order_identifier(monkeypatch):
    _patch_runtime_services(monkeypatch)
    manager = BrokerConnectionManager(db=None)
    manager._submitted_orders["intent-1"] = {
        "symbol": "SPY",
        "side": "BUY",
        "quantity": 1.0,
        "status": "filled",
        "broker_order_id": "broker-order-123",
    }

    result = asyncio.run(
        manager._place_single(_UnexpectedAdapter(), "alpaca", _order("intent-1"), "SPY")
    )

    assert result["status"] == "duplicate"
    assert result["broker_order_id"] == "broker-order-123"
    assert result["order_id"] == "broker-order-123"


def test_rejected_broker_order_records_failure_not_success(monkeypatch):
    class RecordingAudit:
        def __init__(self):
            self.calls = []

        async def log_broker_api(self, *_args, **kwargs):
            self.calls.append(kwargs)

    class RecordingResilience:
        def __init__(self):
            self.successes = []
            self.failures = []

        async def before_call(self, *_args, **_kwargs):
            pass

        async def record_success(self, broker_id):
            self.successes.append(broker_id)

        async def record_failure(self, broker_id, error=None):
            self.failures.append((broker_id, str(error)))

    import audit_service
    import resilience

    audit = RecordingAudit()
    broker_resilience = RecordingResilience()
    monkeypatch.setattr(audit_service, "audit_service", audit)
    monkeypatch.setattr(resilience, "broker_resilience", broker_resilience)

    manager = BrokerConnectionManager(db=None)
    result = asyncio.run(
        manager._place_single(_RejectedAdapter(), "alpaca", _order(), "SPY")
    )

    assert result["status"] == "rejected"
    assert result["error"] == "client_order_id must be unique"
    assert broker_resilience.successes == []
    assert broker_resilience.failures == [("alpaca", "client_order_id must be unique")]
    assert audit.calls[-1]["success"] is False
    assert audit.calls[-1]["error_message"] == "client_order_id must be unique"


def test_partial_fill_result_includes_filled_quantity_and_blocks_duplicate(monkeypatch):
    _patch_runtime_services(monkeypatch)
    manager = BrokerConnectionManager(db=None)

    first = asyncio.run(
        manager._place_single(_PartialAdapter(), "alpaca", _order("intent-partial"), "SPY")
    )
    duplicate = asyncio.run(
        manager._place_single(_UnexpectedAdapter(), "alpaca", _order("intent-partial"), "SPY")
    )

    assert first["status"] == "partially_filled"
    assert first["broker_order_id"] == "broker-order-partial"
    assert first["filled_quantity"] == 0.5
    assert duplicate["status"] == "duplicate"
    assert duplicate["broker_order_id"] == "broker-order-partial"
