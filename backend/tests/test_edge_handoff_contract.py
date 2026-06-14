"""Tests for the structured Edge -> Pulse handoff endpoint."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routes import edge as edge_routes  # noqa: E402
from trading_engine import TradingEngine  # noqa: E402


class _UpdateResult:
    matched_count = 1


class _TickerCollection:
    def __init__(self):
        self.docs = {"AAPL": {"symbol": "AAPL", "enabled": True, "trailing_percent": 2.0}}
        self.updates = []

    async def find_one(self, query, projection=None):
        return self.docs.get(query.get("symbol"))

    async def update_one(self, query, update):
        self.updates.append((query, update))
        doc = self.docs.setdefault(query.get("symbol"), {"symbol": query.get("symbol")})
        doc.update(update.get("$set", {}))
        return _UpdateResult()

    async def update_many(self, query, update):
        self.updates.append((query, update))
        for doc in self.docs.values():
            doc.update(update.get("$set", {}))
        return _UpdateResult()


class _SettingsCollection:
    async def find_one(self, query, projection=None):
        if query.get("key") == "edge_api_key":
            return {"key": "edge_api_key", "value": "test-edge-key"}
        return None


class _Db:
    def __init__(self):
        self.tickers = _TickerCollection()
        self.settings = _SettingsCollection()


class _Engine:
    def __init__(self):
        self._positions = {}
        self.buy_calls = []
        self.sell_calls = []
        self.paused = False
        self.simulate_24_7 = True

    def is_market_open(self):
        return True

    async def execute_buy(self, symbol, price):
        self.buy_calls.append((symbol, price))
        self._positions[symbol] = {"qty": 1, "avg_entry": price}

    async def execute_sell(self, symbol, price):
        self.sell_calls.append((symbol, price))
        self._positions.pop(symbol, None)


class _PriceService:
    async def get_price(self, symbol):
        return 123.45


class EdgeHandoffContractTests(unittest.IsolatedAsyncioTestCase):
    def _handoff_route(self):
        for route in edge_routes.router.routes:
            if getattr(route, "path", "").endswith("/handoff") and "POST" in getattr(route, "methods", set()):
                return route
        self.fail("POST /api/edge/handoff route is not mounted")

    def _request(self, **overrides):
        payload = {
            "symbol": "AAPL",
            "action": "buy",
            "confidence": 0.85,
            "reason": "test",
            "mode": "paper",
            "orb_session": "market_open",
            "idempotency_key": "edge:AAPL:buy:market_open:123:test",
            "source": "sentinel_edge",
            "created_at": 1760000000.0,
            "metadata": {"price": 111.11},
        }
        payload.update(overrides)
        return edge_routes.PulseHandoffRequest(**payload)

    async def test_handoff_route_is_mounted(self):
        self.assertIsNotNone(self._handoff_route())

    async def test_buy_handoff_executes_buy_with_edge_price(self):
        db = _Db()
        engine = _Engine()
        route = self._handoff_route()

        with patch.object(edge_routes.deps, "db", db), patch.object(edge_routes.deps, "engine", engine):
            response = await route.endpoint(self._request())

        self.assertTrue(response["accepted"])
        self.assertEqual("accepted", response["status"])
        self.assertEqual([("AAPL", 111.11)], engine.buy_calls)

    async def test_sell_handoff_executes_sell_with_pulse_price(self):
        db = _Db()
        engine = _Engine()
        engine._positions["AAPL"] = {"qty": 2, "avg_entry": 100.0}
        route = self._handoff_route()

        with (
            patch.object(edge_routes.deps, "db", db),
            patch.object(edge_routes.deps, "engine", engine),
            patch.object(edge_routes.deps, "price_service", _PriceService()),
        ):
            response = await route.endpoint(
                self._request(
                    action="sell",
                    idempotency_key="edge:AAPL:sell:market_open:123:test",
                    metadata={},
                )
            )

        self.assertTrue(response["accepted"])
        self.assertEqual([("AAPL", 123.45)], engine.sell_calls)

    async def test_handoff_route_executes_with_real_trading_engine(self):
        db = _Db()
        db.tickers.docs["AAPL"].update({
            "base_power": 1000.0,
            "broker_ids": [],
            "broker_allocations": {},
        })
        engine = TradingEngine()
        engine.simulate_24_7 = True
        trades = []
        profit_updates = []

        async def record_trade(trade):
            trades.append(trade)

        async def update_profit(symbol, pnl, compound=False):
            profit_updates.append((symbol, pnl, compound))

        engine._record_trade = record_trade
        engine._update_profit = update_profit
        route = self._handoff_route()

        with patch.object(edge_routes.deps, "db", db), patch.object(edge_routes.deps, "engine", engine):
            buy_response = await route.endpoint(self._request(metadata={"price": 100.0}))
            sell_response = await route.endpoint(
                self._request(
                    action="sell",
                    idempotency_key="edge:AAPL:sell:market_open:123:real-engine",
                    metadata={"price": 110.0},
                )
            )

        self.assertTrue(buy_response["accepted"])
        self.assertTrue(sell_response["accepted"])
        self.assertEqual(0, engine._positions["AAPL"]["qty"])
        self.assertEqual(["BUY", "SELL"], [trade.side for trade in trades])
        self.assertEqual(100.0, trades[0].price)
        self.assertEqual(110.0, trades[1].price)
        self.assertEqual([("AAPL", 100.0, True)], profit_updates)

    async def test_opening_trailing_handoff_updates_opening_bell_settings(self):
        db = _Db()
        engine = _Engine()
        route = self._handoff_route()

        with patch.object(edge_routes.deps, "db", db), patch.object(edge_routes.deps, "engine", engine):
            response = await route.endpoint(
                self._request(
                    action="opening_trailing_stop",
                    stop_type="trailing",
                    trailing_percent=0.75,
                    idempotency_key="edge:AAPL:opening_trailing_stop:market_open:123:test",
                    metadata={},
                )
            )

        self.assertTrue(response["accepted"])
        ticker = db.tickers.docs["AAPL"]
        self.assertTrue(ticker["trailing_enabled"])
        self.assertEqual(0.75, ticker["trailing_percent"])
        self.assertTrue(ticker["opening_bell_enabled"])
        self.assertEqual(0.75, ticker["opening_bell_trail_value"])

    async def test_global_tighten_trailing_handoff_updates_all_tickers(self):
        db = _Db()
        db.tickers.docs["MSFT"] = {"symbol": "MSFT", "enabled": True, "trailing_percent": 2.5}
        engine = _Engine()
        route = self._handoff_route()

        with patch.object(edge_routes.deps, "db", db), patch.object(edge_routes.deps, "engine", engine):
            response = await route.endpoint(
                self._request(
                    symbol="GLOBAL",
                    action="tighten_trailing_stop",
                    stop_type="tighten_trailing",
                    trailing_percent=0.75,
                    idempotency_key="edge:GLOBAL:tighten_trailing_stop:market_open:123:test",
                    metadata={},
                )
            )

        self.assertTrue(response["accepted"])
        self.assertTrue(db.tickers.docs["AAPL"]["trailing_enabled"])
        self.assertEqual(0.75, db.tickers.docs["AAPL"]["trailing_percent"])
        self.assertTrue(db.tickers.docs["MSFT"]["trailing_enabled"])
        self.assertEqual(0.75, db.tickers.docs["MSFT"]["trailing_percent"])

    async def test_global_emergency_exit_handoff_sells_all_open_positions(self):
        db = _Db()
        engine = _Engine()
        engine._positions = {
            "AAPL": {"qty": 2, "avg_entry": 100.0},
            "MSFT": {"qty": 1, "avg_entry": 200.0},
            "CASH": {"qty": 0, "avg_entry": 1.0},
        }
        route = self._handoff_route()

        with patch.object(edge_routes.deps, "db", db), patch.object(edge_routes.deps, "engine", engine):
            response = await route.endpoint(
                self._request(
                    symbol="GLOBAL",
                    action="emergency_exit",
                    idempotency_key="edge:GLOBAL:emergency_exit:market_open:123:test",
                    metadata={},
                )
            )

        self.assertTrue(response["accepted"])
        self.assertEqual([("AAPL", None), ("MSFT", None)], engine.sell_calls)


if __name__ == "__main__":
    unittest.main()
