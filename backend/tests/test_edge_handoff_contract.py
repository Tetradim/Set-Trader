"""Tests for the structured Edge -> Pulse handoff endpoint."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routes import edge as edge_routes  # noqa: E402
from trading_engine import TradingEngine  # noqa: E402


class _UpdateResult:
    matched_count = 1


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, *_args, **_kwargs):
        self.docs.reverse()
        return self

    def limit(self, limit):
        self.docs = self.docs[:limit]
        return self

    def skip(self, skip):
        self.docs = self.docs[skip:]
        return self

    async def to_list(self, limit):
        return self.docs[:limit]


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query=None, projection=None):
        query = query or {}
        docs = []
        for doc in self.docs:
            if query.get("symbol") and doc.get("symbol") != query["symbol"]:
                continue
            if query.get("status") and doc.get("status") != query["status"]:
                continue
            clean = {k: v for k, v in doc.items() if k != "_id"} if projection and projection.get("_id") == 0 else dict(doc)
            docs.append(clean)
        return _Cursor(docs)

    async def find_one(self, query=None, projection=None, **kwargs):
        query = query or {}
        for doc in self.docs:
            matched = True
            for key, value in query.items():
                if doc.get(key) != value:
                    matched = False
                    break
            if matched:
                return {k: v for k, v in doc.items() if k != "_id"} if projection and projection.get("_id") == 0 else dict(doc)
        return None

    async def count_documents(self, query):
        return len(await self.find(query).to_list(10000))


class _TickerCollection:
    def __init__(self):
        self.docs = {"AAPL": {"symbol": "AAPL", "enabled": True, "trailing_percent": 2.0}}
        self.updates = []
        self.inserted = []

    async def find_one(self, query=None, projection=None, **kwargs):
        query = query or {}
        if not query:
            docs = sorted(self.docs.values(), key=lambda doc: doc.get("sort_order", 0), reverse=True)
            return docs[0] if docs else None
        return self.docs.get(query.get("symbol"))

    def find(self, query=None, projection=None):
        docs = []
        for doc in self.docs.values():
            clean = {k: v for k, v in doc.items() if k != "_id"} if projection and projection.get("_id") == 0 else dict(doc)
            docs.append(clean)
        return _Cursor(docs)

    async def insert_one(self, doc):
        self.inserted.append(doc)
        self.docs[doc["symbol"]] = doc
        return object()

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
    def __init__(self):
        self.docs = {
            "edge_api_key": {"key": "edge_api_key", "value": "test-edge-key"},
            "telegram": {"key": "telegram", "value": {"bot_token": "secret-token", "chat_ids": ["1"]}},
            "account_balance": {"key": "account_balance", "value": 10000.0},
            "cash_reserve": {"key": "cash_reserve", "value": 100.0},
        }

    async def find_one(self, query, projection=None):
        return self.docs.get(query.get("key"))


class _Db:
    def __init__(self):
        self.tickers = _TickerCollection()
        self.settings = _SettingsCollection()
        self.trades = _Collection([
            {"symbol": "AAPL", "side": "BUY", "quantity": 1, "timestamp": "2026-06-24T15:00:00+00:00"},
        ])
        self.orders = _Collection([
            {"order_id": "ord-1", "symbol": "AAPL", "side": "BUY", "status": "filled", "slippage_bps": 1.5},
        ])
        self.profits = _Collection([])
        self.audit_logs = _Collection([])
        self.replay_sessions = _Collection([
            {"session_id": "session-1", "bar_count": 10, "imported_at": "2026-06-24T15:00:00+00:00"},
        ])
        self.reconciliation_records = _Collection([
            {"record_id": "rec-1", "status": "matched", "broker_timestamp": "2026-06-24T15:00:00+00:00", "pnl": 1.25},
        ])

    def __getitem__(self, name):
        return getattr(self, name)

    async def command(self, *_args, **_kwargs):
        return {"ok": 1}


class _Engine:
    def __init__(self):
        self._positions = {}
        self._prices = {}
        self._pending_sells = set()
        self.buy_calls = []
        self.sell_calls = []
        self.paused = False
        self.running = True
        self.saved_states = 0
        self.simulate_24_7 = True
        self.market_hours_only = False
        self.live_during_market_hours = False
        self.paper_after_hours = True

    def is_market_open(self):
        return True

    def get_trading_mode(self):
        return "paper" if self.simulate_24_7 or not self.live_during_market_hours else "live"

    async def execute_buy(self, symbol, price):
        self.buy_calls.append((symbol, price))
        self._positions[symbol] = {"qty": 1, "avg_entry": price}

    async def execute_sell(self, symbol, price):
        self.sell_calls.append((symbol, price))
        self._positions.pop(symbol, None)

    async def save_state(self):
        self.saved_states += 1


class _WsManager:
    def __init__(self):
        self.messages = []

    async def broadcast(self, message):
        self.messages.append(message)


class _PriceService:
    async def get_price(self, symbol):
        return 123.45

    async def get_fx_rates(self):
        return {"USD": 1.0, "CAD": 0.73}


class _TelegramService:
    running = False


class _RiskControls:
    def isTradingAllowed(self):
        return (True, None, "")

    def get_all_limits(self):
        return [{"limit_id": "portfolio-default", "level": "portfolio"}]

    def get_all_kill_switches(self):
        return []


class _BrokerManager:
    def __init__(self):
        self.reconnect_calls = 0
        self.disconnected = []

    def get_status(self):
        return {"alpaca": {"connected": True, "failed": None, "name": "Alpaca"}}

    async def reconnect_all(self):
        self.reconnect_calls += 1
        return {"alpaca": "connected"}

    async def disconnect_broker(self, broker_id):
        self.disconnected.append(broker_id)


class _NonFinitePriceService:
    async def get_price(self, symbol):
        return float("inf")


class EdgeHandoffContractTests(unittest.IsolatedAsyncioTestCase):
    def _handoff_route(self):
        for route in edge_routes.router.routes:
            if getattr(route, "path", "").endswith("/handoff") and "POST" in getattr(route, "methods", set()):
                return route
        self.fail("POST /api/edge/handoff route is not mounted")

    def _edge_post_route(self, suffix):
        for route in edge_routes.router.routes:
            if getattr(route, "path", "").endswith(suffix) and "POST" in getattr(route, "methods", set()):
                return route
        self.fail(f"POST /api/edge{suffix} route is not mounted")

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

    async def test_edge_start_bot_route_starts_pulse_without_enabling_all_tickers(self):
        engine = _Engine()
        engine.running = False
        engine.paused = True
        ws_manager = _WsManager()
        route = self._edge_post_route("/bot/start")

        with patch.object(edge_routes.deps, "engine", engine), patch.object(edge_routes.deps, "ws_manager", ws_manager):
            response = await route.endpoint(edge_routes.BotControlRequest(enable_all=False))

        self.assertEqual({"running": True, "paused": False, "tickers": None}, response)
        self.assertTrue(engine.running)
        self.assertFalse(engine.paused)
        self.assertEqual(1, engine.saved_states)
        self.assertEqual([{"type": "BOT_STATUS", "running": True, "paused": False}], ws_manager.messages)

    async def test_edge_stop_bot_route_stops_pulse_without_disabling_all_tickers(self):
        engine = _Engine()
        engine._pending_sells.add("AAPL")
        ws_manager = _WsManager()
        route = self._edge_post_route("/bot/stop")

        with patch.object(edge_routes.deps, "engine", engine), patch.object(edge_routes.deps, "ws_manager", ws_manager):
            response = await route.endpoint(edge_routes.BotControlRequest(disable_all=False))

        self.assertEqual({"running": False, "paused": False, "tickers": None}, response)
        self.assertFalse(engine.running)
        self.assertFalse(engine.paused)
        self.assertEqual(set(), engine._pending_sells)
        self.assertEqual(1, engine.saved_states)
        self.assertEqual([{"type": "BOT_STATUS", "running": False, "paused": False}], ws_manager.messages)

    async def test_edge_broker_status_route_reports_connected_brokers(self):
        broker_mgr = _BrokerManager()
        route = self._edge_post_route("/brokers/reconnect")

        with patch.object(edge_routes.deps, "broker_mgr", broker_mgr):
            status = await edge_routes.edge_broker_status()
            response = await route.endpoint()
            disconnect = await edge_routes.edge_disconnect_broker("alpaca")

        self.assertTrue(status["alpaca"]["connected"])
        self.assertEqual({"results": {"alpaca": "connected"}}, response)
        self.assertEqual({"status": "disconnected", "broker_id": "alpaca"}, disconnect)
        self.assertEqual(1, broker_mgr.reconnect_calls)
        self.assertEqual(["alpaca"], broker_mgr.disconnected)

    async def test_edge_read_only_routes_expose_operational_state_for_tandem(self):
        db = _Db()
        engine = _Engine()
        engine._positions["AAPL"] = {"qty": 2, "avg_entry": 100.0}
        engine._pending_sells = {}
        engine._pending_sells["MSFT"] = {"limit_price": 125.0, "qty": 1, "entry": 120.0}
        engine.risk_controls = _RiskControls()

        with (
            patch.object(edge_routes.deps, "db", db),
            patch.object(edge_routes.deps, "engine", engine),
            patch.object(edge_routes.deps, "price_service", _PriceService()),
            patch.object(edge_routes.deps, "telegram_service", _TelegramService()),
            patch.object(edge_routes, "build_bot_snapshot", side_effect=AssertionError("heavy snapshot should not be used")),
        ):
            status = await edge_routes.edge_bot_status()
            snapshot = await edge_routes.edge_bot_snapshot()
            trades = await edge_routes.edge_get_trades(50)
            positions = await edge_routes.edge_get_positions()
            pending = await edge_routes.edge_get_pending_sells()
            risk_status = await edge_routes.edge_risk_status()
            risk_limits = await edge_routes.edge_risk_limits()
            orders = await edge_routes.edge_get_orders(100, None, None)
            order_stats = await edge_routes.edge_get_order_stats()
            strategies = await edge_routes.edge_strategy_registry()
            presets = await edge_routes.edge_strategy_presets()
            markets = await edge_routes.edge_markets()
            fx_rates = await edge_routes.edge_fx_rates()
            replay_status = await edge_routes.edge_replay_status()
            replay_sessions = await edge_routes.edge_replay_sessions(50, False)
            rate_limits = await edge_routes.edge_rate_limits()
            audit_logs = await edge_routes.edge_audit_logs(None, None, None, None, 100, 0)
            settings = await edge_routes.edge_settings()
            reconciliation = await edge_routes.edge_reconciliation_summary()
            analytics = await edge_routes.edge_analytics_portfolio()
            ops_services = await edge_routes.edge_ops_services()
            slo_summary = await edge_routes.edge_slo_summary()

        self.assertEqual({"running": True, "paused": False}, {k: status[k] for k in ("running", "paused")})
        self.assertEqual("paper", status["trading_mode"])
        self.assertEqual("paper", snapshot["trading_mode"])
        self.assertEqual(1, len(snapshot["trades"]))
        self.assertEqual(1, len(snapshot["positions"]))
        self.assertEqual("AAPL", trades[0]["symbol"])
        self.assertEqual([{"symbol": "AAPL", "quantity": 2, "avg_entry": 100.0, "current_price": 123.45, "market_value": 246.9, "unrealized_pnl": 46.9}], positions)
        self.assertEqual({"MSFT": {"limit_price": 125.0, "quantity": 1, "entry": 120.0}}, pending)
        self.assertTrue(risk_status["trading_allowed"])
        self.assertEqual([{"limit_id": "portfolio-default", "level": "portfolio"}], risk_limits["limits"])
        self.assertEqual("ord-1", orders[0]["order_id"])
        self.assertEqual({"total_orders": 1, "filled_orders": 1, "rejected_orders": 0, "pending_orders": 0, "avg_slippage": 1.5, "avg_execution_lag_ms": 0, "fill_rate": 100.0}, order_stats)
        self.assertIn("strategies", strategies)
        self.assertIsInstance(presets, dict)
        self.assertIn("markets", markets)
        self.assertEqual({"rates": {"USD": 1.0, "CAD": 0.73}}, fx_rates)
        self.assertEqual({"replay": {"active": False}}, replay_status)
        self.assertEqual(1, len(replay_sessions["sessions"]))
        self.assertIn("brokers", rate_limits)
        self.assertEqual({"logs": [], "count": 0}, audit_logs)
        self.assertTrue(settings["telegram"]["bot_token_configured"])
        self.assertNotIn("bot_token", settings["telegram"])
        self.assertEqual(1, reconciliation["total_records"])
        self.assertEqual(1, analytics["trade_count"])
        self.assertGreaterEqual(len(ops_services), 3)
        self.assertIn("total_slos", slo_summary)

    async def test_buy_handoff_executes_buy_with_edge_price(self):
        db = _Db()
        engine = _Engine()
        route = self._handoff_route()

        with patch.object(edge_routes.deps, "db", db), patch.object(edge_routes.deps, "engine", engine):
            response = await route.endpoint(self._request())

        self.assertTrue(response["accepted"])
        self.assertEqual("accepted", response["status"])
        self.assertEqual([("AAPL", 111.11)], engine.buy_calls)

    async def test_paper_handoff_is_rejected_when_pulse_is_live(self):
        db = _Db()
        engine = _Engine()
        engine.simulate_24_7 = False
        engine.live_during_market_hours = True
        route = self._handoff_route()

        with patch.object(edge_routes.deps, "db", db), patch.object(edge_routes.deps, "engine", engine):
            response = await route.endpoint(self._request(mode="paper"))

        self.assertFalse(response["accepted"])
        self.assertEqual("rejected", response["status"])
        self.assertEqual("mode_mismatch", response["reason"])
        self.assertEqual([], engine.buy_calls)

    async def test_legacy_buy_decision_is_rejected_when_pulse_is_live(self):
        db = _Db()
        engine = _Engine()
        engine.simulate_24_7 = False
        engine.live_during_market_hours = True

        with patch.object(edge_routes.deps, "db", db), patch.object(edge_routes.deps, "engine", engine):
            response = await edge_routes.post_decision(
                "AAPL",
                edge_routes.DecisionRequest(symbol="AAPL", decision="buy", price=111.11),
            )

        self.assertEqual("error", response["status"])
        self.assertEqual("legacy_live_handoff_blocked", response["reason"])
        self.assertEqual([], engine.buy_calls)

    async def test_buy_handoff_creates_missing_ticker_before_buy(self):
        db = _Db()
        engine = _Engine()
        route = self._handoff_route()

        with patch.object(edge_routes.deps, "db", db), patch.object(edge_routes.deps, "engine", engine):
            response = await route.endpoint(
                self._request(
                    symbol="PLTR",
                    idempotency_key="edge:PLTR:buy:market_open:123:test",
                    metadata={"price": 25.0},
                )
            )

        self.assertTrue(response["accepted"])
        self.assertEqual("accepted", response["status"])
        self.assertEqual([("PLTR", 25.0)], engine.buy_calls)
        self.assertEqual(1, len(db.tickers.inserted))
        created = db.tickers.docs["PLTR"]
        self.assertEqual(100.0, created["base_power"])
        self.assertTrue(created["enabled"])

    async def test_buy_handoff_rejects_non_finite_edge_price(self):
        db = _Db()
        engine = _Engine()
        route = self._handoff_route()

        with patch.object(edge_routes.deps, "db", db), patch.object(edge_routes.deps, "engine", engine):
            response = await route.endpoint(self._request(metadata={"price": float("inf")}))

        self.assertFalse(response["accepted"])
        self.assertEqual("rejected", response["status"])
        self.assertEqual("price_unavailable", response["reason"])
        self.assertEqual([], engine.buy_calls)

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

    async def test_sell_handoff_rejects_non_finite_price_service_value(self):
        db = _Db()
        engine = _Engine()
        engine._positions["AAPL"] = {"qty": 2, "avg_entry": 100.0}
        route = self._handoff_route()

        with (
            patch.object(edge_routes.deps, "db", db),
            patch.object(edge_routes.deps, "engine", engine),
            patch.object(edge_routes.deps, "price_service", _NonFinitePriceService()),
        ):
            response = await route.endpoint(
                self._request(
                    action="sell",
                    idempotency_key="edge:AAPL:sell:market_open:123:test",
                    metadata={},
                )
            )

        self.assertFalse(response["accepted"])
        self.assertEqual("rejected", response["status"])
        self.assertEqual("price_unavailable", response["reason"])
        self.assertEqual([], engine.sell_calls)

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

    async def test_structured_trailing_handoff_rejects_non_finite_percent(self):
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as raised:
                    self._request(
                        action="trailing_stop",
                        stop_type="trailing",
                        trailing_percent=value,
                        idempotency_key="edge:AAPL:trailing_stop:market_open:123:test",
                        metadata={},
                    )

                self.assertIn("trailing_percent", str(raised.exception))

    async def test_legacy_trailing_request_rejects_non_finite_percent(self):
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as raised:
                    edge_routes.TrailingRequest(trailing_percent=value)

                self.assertIn("trailing_percent", str(raised.exception))

    async def test_legacy_decision_rejects_non_finite_trailing_percent(self):
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError) as raised:
                    edge_routes.DecisionRequest(
                        symbol="AAPL",
                        decision="enable_trailing_stop",
                        trailing_percent=value,
                    )

                self.assertIn("trailing_percent", str(raised.exception))

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
