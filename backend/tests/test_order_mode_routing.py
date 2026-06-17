import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import deps  # noqa: E402
from trading_engine import TradingEngine  # noqa: E402


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass


class _Tickers:
    async def find_one(self, query, projection=None):
        return {
            "symbol": query["symbol"],
            "base_power": 100.0,
            "broker_ids": ["alpaca"],
            "broker_allocations": {"alpaca": 100.0},
            "reentry_cooldown_seconds": 0,
        }


class _Db:
    tickers = _Tickers()


class _BrokerManager:
    def __init__(self):
        self.calls = []

    async def place_orders_for_ticker(self, **kwargs):
        self.calls.append(kwargs)
        return [{"broker_id": "alpaca", "status": "filled"}]


def _engine(monkeypatch):
    broker_mgr = _BrokerManager()
    monkeypatch.setattr(deps, "db", _Db())
    monkeypatch.setattr(deps, "broker_mgr", broker_mgr)
    monkeypatch.setattr(deps, "logger", _Logger())

    engine = TradingEngine()
    engine.simulate_24_7 = False
    engine.live_during_market_hours = False
    engine.REENTRY_COOLDOWN_SECS = 0

    trades = []

    async def record_trade(trade):
        trades.append(trade)

    engine._record_trade = record_trade
    engine._test_trades = trades
    engine._test_broker_mgr = broker_mgr
    return engine


def test_broker_ticker_stays_paper_when_live_during_market_hours_disabled(monkeypatch):
    engine = _engine(monkeypatch)

    result = asyncio.run(engine.execute_buy("SPY", 50.0))

    assert result["trading_mode"] == "paper"
    assert engine._test_trades[0].trading_mode == "paper"
    assert engine._test_broker_mgr.calls == []


def test_broker_ticker_routes_live_only_when_live_during_market_hours_enabled(monkeypatch):
    engine = _engine(monkeypatch)
    engine.live_during_market_hours = True

    result = asyncio.run(engine.execute_buy("SPY", 50.0))

    assert result["trading_mode"] == "live"
    assert engine._test_trades[0].trading_mode == "live"
    assert len(engine._test_broker_mgr.calls) == 1
