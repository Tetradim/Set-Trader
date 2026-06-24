import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from brokers.alpaca_adapter import AlpacaAdapter  # noqa: E402
from brokers.base import BrokerOrder, OrderSide, OrderType  # noqa: E402


class _Response:
    def __init__(self, payload=None, status=201):
        self._payload = payload or {"id": "alpaca-order-1", "status": "accepted"}
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload


class _Session:
    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, url, *, headers=None, json=None):
        self.posts.append({"url": url, "headers": headers, "json": json})
        return _Response()

    def get(self, url, *, headers=None):
        self.gets.append({"url": url, "headers": headers})
        return _Response()


class _Adapter(AlpacaAdapter):
    def __init__(self):
        super().__init__({"api_key": "key", "api_secret": "secret", "paper": "true"})
        self.session = _Session()

    async def _get_session(self):
        return self.session


def test_limit_order_payload_includes_limit_price_for_order_type_enum():
    adapter = _Adapter()
    order = BrokerOrder(
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=1.0,
        limit_price=1.23,
    )

    result = asyncio.run(adapter.place_order(order))

    assert result.status == "accepted"
    assert adapter.session.posts[0]["json"]["type"] == "limit"
    assert adapter.session.posts[0]["json"]["limit_price"] == "1.23"


def test_market_order_polls_until_terminal_fill_status():
    class _PollingSession(_Session):
        def get(self, url, *, headers=None):
            self.gets.append({"url": url, "headers": headers})
            return _Response(
                {
                    "id": "alpaca-order-1",
                    "status": "filled",
                    "filled_avg_price": "6.37",
                    "filled_qty": "1",
                },
                status=200,
            )

    adapter = _Adapter()
    adapter.session = _PollingSession()
    order = BrokerOrder(
        symbol="SOUN",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
    )

    result = asyncio.run(adapter.place_order(order))

    assert result.status == "filled"
    assert result.filled_price == 6.37
    assert result.filled_quantity == 1.0
    assert adapter.session.gets[0]["url"].endswith("/v2/orders/alpaca-order-1")


def test_place_order_forwards_idempotency_key_as_client_order_id():
    adapter = _Adapter()
    order = BrokerOrder(
        symbol="SPY",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        idempotency_key="sp_12345678-1234-1234-1234-123456789abc",
    )

    result = asyncio.run(adapter.place_order(order))

    assert adapter.session.posts[0]["json"]["client_order_id"] == order.idempotency_key
    assert result.client_order_id == order.idempotency_key


def test_place_order_hashes_long_edge_idempotency_key_for_client_order_id():
    adapter = _Adapter()
    order = BrokerOrder(
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        idempotency_key="edge:AAPL:opening_trailing_stop:market_open:123:test",
    )

    result = asyncio.run(adapter.place_order(order))
    client_order_id = adapter.session.posts[0]["json"]["client_order_id"]

    assert client_order_id.startswith("sp_")
    assert len(client_order_id) <= 48
    assert ":" not in client_order_id
    assert result.client_order_id == client_order_id
