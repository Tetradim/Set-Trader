import asyncio
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import deps  # noqa: E402
from bot_event_bus import EventBusStore  # noqa: E402
from risk_controls import ExposureLimit  # noqa: E402
from schemas import TradeRecord  # noqa: E402
from trading_engine import TradingEngine  # noqa: E402


class _Span:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def set_attribute(self, *_args, **_kwargs):
        pass

    def add_event(self, *_args, **_kwargs):
        pass


class _Tracer:
    def start_as_current_span(self, *_args, **_kwargs):
        return _Span()


class _Trades:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(doc)


class _Settings:
    async def update_one(self, *_args, **_kwargs):
        pass


class _Db:
    def __init__(self):
        self.trades = _Trades()
        self.settings = _Settings()


class _WsManager:
    async def broadcast(self, *_args, **_kwargs):
        pass


class _TelegramService:
    async def send_trade_alert(self, *_args, **_kwargs):
        pass


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


def _install_record_trade_deps(monkeypatch, tmp_path):
    edge_integration = types.ModuleType("shared.edge_integration")

    async def on_trade_executed(_doc):
        pass

    edge_integration.on_trade_executed = on_trade_executed
    monkeypatch.setitem(sys.modules, "shared.edge_integration", edge_integration)
    monkeypatch.setenv("BOT_EVENT_BUS_DIR", str(tmp_path / "event-bus"))
    monkeypatch.setattr(deps, "db", _Db())
    monkeypatch.setattr(deps, "tracer", _Tracer())
    monkeypatch.setattr(deps, "ws_manager", _WsManager())
    monkeypatch.setattr(deps, "telegram_service", _TelegramService())
    monkeypatch.setattr(deps, "logger", _Logger())


def test_record_trade_updates_portfolio_exposure_after_successful_buy(monkeypatch, tmp_path):
    _install_record_trade_deps(monkeypatch, tmp_path)
    engine = TradingEngine()
    engine.risk_controls.add_exposure_limit(
        ExposureLimit(
            limit_id="spy_notional",
            level="symbol",
            level_id="SPY",
            max_notional=500.0,
        )
    )
    trade = TradeRecord(
        symbol="SPY",
        side="BUY",
        price=50.0,
        quantity=2.0,
        total_value=100.0,
        trading_mode="live",
    )

    asyncio.run(engine._record_trade(trade))

    global_limit = engine.risk_controls.get_exposure_limit("portfolio", "global")
    assert global_limit.current_notional == 100.0
    assert global_limit.current_position == 2.0
    assert global_limit.orders_count == 1

    symbol_limit = engine.risk_controls.get_exposure_limit("symbol", "SPY")
    assert symbol_limit.current_notional == 100.0
    assert symbol_limit.current_position == 2.0


def test_record_trade_publishes_pulse_trade_event_for_sentinel_core_bus(monkeypatch, tmp_path):
    _install_record_trade_deps(monkeypatch, tmp_path)
    engine = TradingEngine()
    trade = TradeRecord(
        symbol="SPY",
        side="SELL",
        price=51.0,
        quantity=2.0,
        total_value=102.0,
        pnl=2.0,
        trading_mode="paper",
        order_type="LIMIT",
    )

    asyncio.run(engine._record_trade(trade))

    events = EventBusStore(tmp_path / "event-bus").list_events(limit=10)
    assert [event["event_type"] for event in events] == ["pulse.trade.recorded"]
    assert events[0]["source"] == "sentinel-pulse"
    assert events[0]["payload"]["symbol"] == "SPY"
    assert events[0]["payload"]["side"] == "SELL"
    assert events[0]["payload"]["trading_mode"] == "paper"
    assert events[0]["payload"]["pnl"] == 2.0
