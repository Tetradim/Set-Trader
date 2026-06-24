import asyncio
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import deps  # noqa: E402
from risk_controls import KillSwitchLevel  # noqa: E402
from trading_engine import TradingEngine  # noqa: E402


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass


def _ticker_doc(**overrides):
    doc = {
        "symbol": "SPY",
        "base_power": 100.0,
        "broker_ids": ["alpaca"],
        "broker_allocations": {"alpaca": 100.0},
        "reentry_cooldown_seconds": 0,
    }
    doc.update(overrides)
    return doc


class _Tickers:
    def __init__(self, doc=None):
        self.doc = doc or _ticker_doc()

    async def find_one(self, query, projection=None):
        return {**self.doc, "symbol": query["symbol"]}


class _Db:
    def __init__(self, ticker_doc=None):
        self.tickers = _Tickers(ticker_doc)


class _BrokerManager:
    def __init__(self, results=None):
        self.calls = []
        self.results = results or [
            {
                "broker_id": "alpaca",
                "status": "filled",
                "broker_order_id": "alpaca-order-1",
            }
        ]

    async def place_orders_for_ticker(self, **kwargs):
        self.calls.append(kwargs)
        return self.results


def _engine(monkeypatch, ticker_doc=None, broker_results=None):
    broker_mgr = _BrokerManager(broker_results)
    monkeypatch.setattr(deps, "db", _Db(ticker_doc))
    monkeypatch.setattr(deps, "broker_mgr", broker_mgr)
    monkeypatch.setattr(deps, "logger", _Logger())

    engine = TradingEngine()
    engine.simulate_24_7 = False
    engine.live_during_market_hours = False
    engine.REENTRY_COOLDOWN_SECS = 0

    trades = []

    async def record_trade(trade):
        trades.append(trade)

    async def update_profit(*_args, **_kwargs):
        pass

    engine._record_trade = record_trade
    engine._update_profit = update_profit
    engine._test_trades = trades
    engine._test_broker_mgr = broker_mgr
    return engine


def test_broker_ticker_stays_paper_when_live_during_market_hours_disabled(monkeypatch):
    engine = _engine(monkeypatch)

    result = asyncio.run(engine.execute_buy("SPY", 50.0))

    assert result["trading_mode"] == "paper"
    assert engine._test_trades[0].trading_mode == "paper"
    assert engine._test_broker_mgr.calls == []


def test_broker_ticker_routes_to_paper_broker_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("SENTINEL_PULSE_ENABLE_BROKER_PAPER_EXECUTION", "true")
    engine = _engine(
        monkeypatch,
        ticker_doc=_ticker_doc(
            base_power=100.0,
            broker_ids=["alpaca"],
            broker_allocations={"alpaca": 50.0},
        ),
    )

    result = asyncio.run(engine.execute_buy("SPY", 50.0))

    assert result["trading_mode"] == "paper"
    assert result["quantity"] == 1.0
    assert engine._test_trades[0].trading_mode == "paper"
    assert len(engine._test_broker_mgr.calls) == 1
    assert engine._test_broker_mgr.calls[0]["allocations"] == {"alpaca": 50.0}


def test_dry_run_blocks_broker_paper_handoff_even_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("SENTINEL_PULSE_ENABLE_BROKER_PAPER_EXECUTION", "true")
    engine = _engine(monkeypatch)
    engine.live_during_market_hours = True
    engine.set_dry_run(True)

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


def test_live_buy_rejects_broker_allocations_above_ticker_buy_power(monkeypatch):
    engine = _engine(
        monkeypatch,
        ticker_doc=_ticker_doc(
            base_power=100.0,
            broker_ids=["alpaca"],
            broker_allocations={"alpaca": 150.0},
        ),
    )
    engine.live_during_market_hours = True

    with pytest.raises(ValueError, match="exceed ticker buy power"):
        asyncio.run(engine.execute_buy("SPY", 50.0))

    assert engine._test_broker_mgr.calls == []
    assert engine._test_trades == []
    assert engine._positions.get("SPY") is None


def test_live_buy_records_actual_active_broker_allocation_quantity(monkeypatch):
    engine = _engine(
        monkeypatch,
        ticker_doc=_ticker_doc(
            base_power=100.0,
            broker_ids=["alpaca"],
            broker_allocations={"alpaca": 50.0},
        ),
    )
    engine.live_during_market_hours = True

    result = asyncio.run(engine.execute_buy("SPY", 50.0))

    assert result["trading_mode"] == "live"
    assert result["quantity"] == 1.0
    assert engine._positions["SPY"]["qty"] == 1.0
    assert engine._test_trades[0].quantity == 1.0
    assert engine._test_trades[0].buy_power == 50.0
    assert engine._test_broker_mgr.calls[0]["allocations"] == {"alpaca": 50.0}


def test_live_buy_records_actual_broker_partial_fill_quantity(monkeypatch):
    engine = _engine(
        monkeypatch,
        ticker_doc=_ticker_doc(
            base_power=100.0,
            broker_ids=["alpaca"],
            broker_allocations={"alpaca": 100.0},
        ),
        broker_results=[
            {
                "broker_id": "alpaca",
                "status": "partially_filled",
                "broker_order_id": "alpaca-order-1",
                "filled_quantity": 0.75,
                "filled_price": 50.0,
            }
        ],
    )
    engine.live_during_market_hours = True

    result = asyncio.run(engine.execute_buy("SPY", 50.0))

    assert result["trading_mode"] == "live"
    assert result["quantity"] == 0.75
    assert engine._positions["SPY"]["qty"] == 0.75
    assert engine._test_trades[0].quantity == 0.75
    assert engine._test_trades[0].buy_power == 37.5


def test_live_buy_rejects_confirmation_without_broker_order_identifier(monkeypatch):
    engine = _engine(
        monkeypatch,
        broker_results=[{"broker_id": "alpaca", "status": "filled"}],
    )
    engine.live_during_market_hours = True

    with pytest.raises(RuntimeError, match="missing broker order identifier"):
        asyncio.run(engine.execute_buy("SPY", 50.0))

    assert len(engine._test_broker_mgr.calls) == 1
    assert engine._test_trades == []
    assert engine._positions.get("SPY") is None


def test_live_buy_blocks_before_broker_handoff_when_global_kill_switch_active(monkeypatch):
    engine = _engine(monkeypatch)
    engine.live_during_market_hours = True
    engine.risk_controls.add_kill_switch(KillSwitchLevel.GLOBAL, "global")
    engine.risk_controls.activate_kill_switch(
        KillSwitchLevel.GLOBAL,
        "global",
        "test",
        "panic stop",
    )

    with pytest.raises(RuntimeError, match="GLOBAL KILL SWITCH ACTIVE"):
        asyncio.run(engine.execute_buy("SPY", 50.0))

    assert engine._test_broker_mgr.calls == []
    assert engine._test_trades == []
    assert engine._positions.get("SPY") is None


def test_live_sell_blocks_before_broker_handoff_when_global_kill_switch_active(monkeypatch):
    engine = _engine(monkeypatch)
    engine.live_during_market_hours = True
    engine._prices["SPY"] = 50.0
    engine._positions["SPY"] = {"qty": 2.0, "avg_entry": 45.0, "high": 55.0}
    engine.risk_controls.add_kill_switch(KillSwitchLevel.GLOBAL, "global")
    engine.risk_controls.activate_kill_switch(
        KillSwitchLevel.GLOBAL,
        "global",
        "test",
        "panic stop",
    )

    with pytest.raises(RuntimeError, match="GLOBAL KILL SWITCH ACTIVE"):
        asyncio.run(engine.execute_sell("SPY", 50.0))

    assert engine._test_broker_mgr.calls == []
    assert engine._test_trades == []
    assert engine._positions["SPY"]["qty"] == 2.0


def test_live_buy_runs_one_pretrade_check(monkeypatch):
    engine = _engine(monkeypatch)
    engine.live_during_market_hours = True
    checks = []

    async def pre_trade_check(symbol, side, quantity, price):
        checks.append((symbol, side, quantity, price))
        return True, ""

    engine.pre_trade_check = pre_trade_check

    result = asyncio.run(engine.execute_buy("SPY", 50.0))

    assert result["trading_mode"] == "live"
    assert checks == [("SPY", "BUY", 2.0, 50.0)]


def test_live_sell_runs_one_pretrade_check(monkeypatch):
    engine = _engine(monkeypatch)
    engine.live_during_market_hours = True
    engine._prices["SPY"] = 50.0
    engine._positions["SPY"] = {"qty": 2.0, "avg_entry": 45.0, "high": 55.0}
    checks = []

    async def pre_trade_check(symbol, side, quantity, price):
        checks.append((symbol, side, quantity, price))
        return True, ""

    engine.pre_trade_check = pre_trade_check

    result = asyncio.run(engine.execute_sell("SPY", 50.0))

    assert result["trading_mode"] == "live"
    assert checks == [("SPY", "SELL", 2.0, 50.0)]


def test_live_sell_rejects_confirmation_without_broker_order_identifier(monkeypatch):
    engine = _engine(
        monkeypatch,
        broker_results=[{"broker_id": "alpaca", "status": "filled"}],
    )
    engine.live_during_market_hours = True
    engine._prices["SPY"] = 50.0
    engine._positions["SPY"] = {"qty": 2.0, "avg_entry": 45.0, "high": 55.0}

    with pytest.raises(RuntimeError, match="missing broker order identifier"):
        asyncio.run(engine.execute_sell("SPY", 50.0))

    assert len(engine._test_broker_mgr.calls) == 1
    assert engine._test_trades == []
    assert engine._positions["SPY"]["qty"] == 2.0


def test_live_sell_preserves_unfilled_remainder_after_broker_partial_fill(monkeypatch):
    engine = _engine(
        monkeypatch,
        broker_results=[
            {
                "broker_id": "alpaca",
                "status": "partially_filled",
                "broker_order_id": "alpaca-order-1",
                "filled_quantity": 0.75,
                "filled_price": 50.0,
            }
        ],
    )
    engine.live_during_market_hours = True
    engine._prices["SPY"] = 50.0
    engine._positions["SPY"] = {"qty": 2.0, "avg_entry": 45.0, "high": 55.0}

    result = asyncio.run(engine.execute_sell("SPY", 50.0))

    assert result["trading_mode"] == "live"
    assert result["quantity"] == 0.75
    assert result["pnl"] == 3.75
    assert engine._positions["SPY"]["qty"] == 1.25
    assert engine._positions["SPY"]["avg_entry"] == 45.0
    assert engine._test_trades[0].quantity == 0.75


def test_dry_run_blocks_live_broker_handoff_even_when_live_mode_enabled(monkeypatch):
    engine = _engine(monkeypatch)
    engine.live_during_market_hours = True
    engine.set_dry_run(True)

    result = asyncio.run(engine.execute_buy("SPY", 50.0))

    assert result["trading_mode"] == "paper"
    assert engine._test_trades[0].trading_mode == "paper"
    assert engine._test_broker_mgr.calls == []
