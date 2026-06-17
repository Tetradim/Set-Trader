import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import deps  # noqa: E402
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


class _Logger:
    def debug(self, *_args, **_kwargs):
        pass

    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


class _PriceService:
    async def get_price(self, _symbol):
        return 95.0

    async def get_avg_price(self, _symbol, _days):
        return 100.0

    async def get_enriched_market_data(self, _ticker_doc):
        return {}


class _Tickers:
    async def find_one(self, query, projection=None):
        return {"symbol": query["symbol"], "base_power": 1_000.0, "broker_ids": []}


class _Db:
    tickers = _Tickers()


class _BuySignalStrategy:
    metadata = SimpleNamespace(name="TEST", is_signal_strategy=True)

    async def validate_ticker(self, _ticker_doc):
        return True

    def get_params(self, _ticker_doc):
        return {}

    async def generate_signals(self, *_args, **_kwargs):
        return SimpleNamespace(action="BUY", reason="test re-entry", confidence=0.9)


class _ExitSignalStrategy:
    metadata = SimpleNamespace(name="TEST", is_signal_strategy=True)

    async def validate_ticker(self, _ticker_doc):
        return True

    def get_params(self, _ticker_doc):
        return {}

    async def generate_signals(self, *_args, **_kwargs):
        return SimpleNamespace(action="SELL", reason="flat exit signal", confidence=0.9)


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr(deps, "tracer", _Tracer())
    monkeypatch.setattr(deps, "logger", _Logger())
    monkeypatch.setattr(deps, "price_service", _PriceService())
    monkeypatch.setattr(deps, "db", _Db())

    instance = TradingEngine()
    instance.simulate_24_7 = True
    instance._is_ticker_market_open = lambda _ticker_doc: True
    instance._get_market = lambda _ticker_doc: SimpleNamespace(to_dict=lambda: {})
    instance._last_exit_ts = {"SPY": datetime.now(timezone.utc)}

    trades = []

    async def record_trade(trade):
        trades.append(trade)

    instance._record_trade = record_trade
    instance._test_trades = trades
    return instance


def test_recent_exit_blocks_bracket_reentry(engine):
    ticker_doc = {
        "symbol": "SPY",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "buy_percent": False,
        "buy_offset": 100.0,
        "buy_order_type": "limit",
        "broker_ids": [],
        "broker_allocations": {},
    }

    asyncio.run(engine.evaluate_ticker(ticker_doc))

    assert engine._test_trades == []
    assert engine._positions.get("SPY", {}).get("qty", 0) == 0


def test_recent_exit_blocks_partial_fill_reentry(engine):
    ticker_doc = {
        "symbol": "SPY",
        "partial_fills_enabled": True,
        "buy_legs": [{"offset": 100.0, "is_percent": False, "alloc_pct": 100}],
        "sell_legs": [],
        "stop_percent": True,
        "stop_offset": -6.0,
        "auto_rebracket": False,
    }

    asyncio.run(engine._evaluate_partial_fills(
        ticker_doc,
        "SPY",
        95.0,
        100.0,
        {"qty": 0, "avg_entry": 0},
        0,
        1_000.0,
        [],
        {},
        94.0,
        True,
        "limit",
        True,
    ))

    assert engine._test_trades == []
    assert engine._positions.get("SPY", {}).get("qty", 0) == 0


def test_partial_fill_trailing_stop_exits_remaining_position(engine):
    engine._last_exit_ts = {}
    engine._trailing_highs["SPY"] = 110.0
    pos = {
        "qty": 10.0,
        "avg_entry": 100.0,
        "buy_legs_filled": [0, 1, 2],
        "sell_legs_filled": [0, 1],
    }
    engine._positions["SPY"] = dict(pos)

    async def update_profit(symbol, pnl, compound=False):
        engine._test_profit_update = (symbol, pnl, compound)

    engine._update_profit = update_profit

    ticker_doc = {
        "symbol": "SPY",
        "partial_fills_enabled": True,
        "buy_legs": [],
        "sell_legs": [],
        "stop_percent": True,
        "stop_offset": -6.0,
        "trailing_enabled": True,
        "trailing_percent": 1.0,
        "trailing_percent_mode": True,
        "trailing_order_type": "limit",
        "auto_rebracket": False,
    }

    asyncio.run(engine._evaluate_partial_fills(
        ticker_doc,
        "SPY",
        108.0,
        100.0,
        pos,
        100.0,
        1_000.0,
        [],
        {},
        94.0,
        True,
        "limit",
        True,
    ))

    assert len(engine._test_trades) == 1
    assert engine._test_trades[0].side == "TRAILING_STOP"
    assert engine._positions["SPY"]["qty"] == 0
    assert "SPY" not in engine._trailing_highs


def test_partial_fill_trailing_stop_initializes_high_water_mark(engine):
    engine._last_exit_ts = {}
    pos = {
        "qty": 10.0,
        "avg_entry": 100.0,
        "buy_legs_filled": [0, 1, 2],
        "sell_legs_filled": [0, 1],
    }
    engine._positions["SPY"] = dict(pos)

    ticker_doc = {
        "symbol": "SPY",
        "partial_fills_enabled": True,
        "buy_legs": [],
        "sell_legs": [],
        "stop_percent": True,
        "stop_offset": -6.0,
        "trailing_enabled": True,
        "trailing_percent": 1.0,
        "trailing_percent_mode": True,
        "trailing_order_type": "limit",
        "auto_rebracket": False,
    }

    asyncio.run(engine._evaluate_partial_fills(
        ticker_doc,
        "SPY",
        108.0,
        100.0,
        pos,
        100.0,
        1_000.0,
        [],
        {},
        94.0,
        True,
        "limit",
        True,
    ))

    assert engine._test_trades == []
    assert engine._trailing_highs["SPY"] == 108.0
    assert engine._positions["SPY"]["qty"] == 10.0


def test_recent_exit_blocks_strategy_buy_and_skips_fallback(engine):
    handled = asyncio.run(engine._run_strategy_signal(
        _BuySignalStrategy(),
        {"symbol": "SPY"},
        "SPY",
        95.0,
        {"qty": 0, "avg_entry": 0},
        0,
        1_000.0,
        [],
        {},
        110.0,
        90.0,
        True,
        100.0,
    ))

    assert handled is True
    assert engine._test_trades == []
    assert engine._positions.get("SPY", {}).get("qty", 0) == 0


def test_recent_exit_blocks_edge_handoff_buy(engine):
    async def run():
        with pytest.raises(ValueError, match="re-entry cooldown"):
            await engine.execute_buy("SPY", 95.0)

    asyncio.run(run())

    assert engine._test_trades == []
    assert engine._positions.get("SPY", {}).get("qty", 0) == 0


def test_flat_strategy_exit_signal_is_handled_without_bracket_fallback(engine):
    engine._last_exit_ts = {}

    handled = asyncio.run(engine._run_strategy_signal(
        _ExitSignalStrategy(),
        {"symbol": "SPY"},
        "SPY",
        95.0,
        {"qty": 0, "avg_entry": 0},
        0,
        1_000.0,
        [],
        {},
        110.0,
        90.0,
        True,
        100.0,
    ))

    assert handled is True
    assert engine._test_trades == []
    assert engine._positions.get("SPY", {}).get("qty", 0) == 0


class _TradeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    async def to_list(self, _length):
        return self.docs


class _Trades:
    def __init__(self, docs):
        self.docs = docs

    def find(self, *_args, **_kwargs):
        return _TradeCursor(self.docs)


class _ExitDb:
    def __init__(self, docs):
        self.trades = _Trades(docs)


def test_recent_exit_cooldowns_hydrate_from_trade_history(monkeypatch):
    recent_exit = datetime(2026, 6, 15, 12, 5, tzinfo=timezone.utc)
    older_exit = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        deps,
        "db",
        _ExitDb(
            [
                {"symbol": "SPY", "side": "BUY", "timestamp": datetime(2026, 6, 15, 12, 6, tzinfo=timezone.utc).isoformat()},
                {"symbol": "SPY", "side": "STOP", "timestamp": recent_exit.isoformat()},
                {"symbol": "SPY", "side": "SELL", "timestamp": older_exit.isoformat()},
            ]
        ),
    )
    monkeypatch.setattr(deps, "logger", _Logger())

    instance = TradingEngine()

    asyncio.run(instance.load_recent_exit_cooldowns())

    assert instance._last_exit_ts["SPY"] == recent_exit
    assert instance._reentry_cooldown_remaining(
        "SPY",
        now=recent_exit + timedelta(seconds=60),
    ) == 240
