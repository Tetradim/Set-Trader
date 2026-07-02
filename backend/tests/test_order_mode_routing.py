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


class _Settings:
    def __init__(self):
        self.updated = None

    async def update_one(self, query, update, upsert=False):
        self.updated = {"query": query, "update": update, "upsert": upsert}

    async def find_one(self, *_args, **_kwargs):
        return None


class _Db:
    def __init__(self, ticker_doc=None):
        self.tickers = _Tickers(ticker_doc)
        self.settings = _Settings()


class _PriceService:
    def __init__(self, price=50.0, avg=50.0):
        self.price = price
        self.avg = avg

    async def get_price(self, _symbol):
        return self.price

    async def get_avg_price(self, _symbol, _days):
        return self.avg


class _Span:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Tracer:
    def start_as_current_span(self, *_args, **_kwargs):
        return _Span()


class _BrokerManager:
    def __init__(self, results=None, adapter=None, broker_positions=None):
        self.calls = []
        self.results = results or [
            {
                "broker_id": "alpaca",
                "status": "filled",
                "broker_order_id": "alpaca-order-1",
            }
        ]
        self.adapter = adapter
        self.broker_positions = broker_positions or {}

    async def place_orders_for_ticker(self, **kwargs):
        self.calls.append(kwargs)
        return self.results

    def get_adapter(self, _broker_id):
        return self.adapter

    async def reconcile_positions(self, _broker_id):
        return self.broker_positions


class _BrokerPosition:
    def __init__(self, symbol, quantity):
        self.symbol = symbol
        self.quantity = quantity


class _OpenOrder:
    def __init__(self, symbol, side, quantity):
        self.symbol = symbol
        self.side = side
        self.quantity = quantity


class _PositionAdapter:
    def __init__(self, positions, open_orders=None):
        self.positions = positions
        self.open_orders = open_orders or []

    async def get_positions(self):
        return self.positions

    async def get_open_orders(self):
        return self.open_orders


def _engine(monkeypatch, ticker_doc=None, broker_results=None, broker_adapter=None, broker_positions=None):
    broker_mgr = _BrokerManager(broker_results, broker_adapter, broker_positions)
    db = _Db(ticker_doc)
    monkeypatch.setattr(deps, "db", db)
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
    engine._test_db = db
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


def test_pending_live_order_blocks_immediate_duplicate_submission(monkeypatch):
    engine = _engine(
        monkeypatch,
        broker_results=[
            {
                "broker_id": "alpaca",
                "status": "accepted",
                "broker_order_id": "alpaca-order-pending",
            }
        ],
    )
    engine.live_during_market_hours = True

    with pytest.raises(RuntimeError, match="pending fill"):
        asyncio.run(engine.execute_buy("SPY", 50.0))

    assert len(engine._test_broker_mgr.calls) == 1
    assert engine._test_trades == []
    assert engine._positions.get("SPY") is None

    with pytest.raises(RuntimeError, match="still pending fill"):
        asyncio.run(engine.execute_buy("SPY", 50.1))

    assert len(engine._test_broker_mgr.calls) == 1


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


def test_live_sell_blocks_when_broker_position_is_missing(monkeypatch):
    engine = _engine(
        monkeypatch,
        broker_adapter=_PositionAdapter([]),
    )
    engine.live_during_market_hours = True
    engine._prices["SPY"] = 50.0
    engine._positions["SPY"] = {"qty": 2.0, "avg_entry": 45.0, "high": 55.0}

    with pytest.raises(RuntimeError, match="broker position is insufficient"):
        asyncio.run(engine.execute_sell("SPY", 50.0))

    assert engine._test_broker_mgr.calls == []
    assert engine._test_trades == []
    assert engine._positions["SPY"]["qty"] == 2.0


def test_live_sell_blocks_when_open_sell_order_already_reserves_position(monkeypatch):
    engine = _engine(
        monkeypatch,
        broker_adapter=_PositionAdapter(
            [_BrokerPosition("SPY", 2.0)],
            [_OpenOrder("SPY", "SELL", 2.0)],
        ),
    )
    engine.live_during_market_hours = True
    engine._prices["SPY"] = 50.0
    engine._positions["SPY"] = {"qty": 2.0, "avg_entry": 45.0, "high": 55.0}

    with pytest.raises(RuntimeError, match="already in open sell orders"):
        asyncio.run(engine.execute_sell("SPY", 50.0))

    assert engine._test_broker_mgr.calls == []
    assert engine._test_trades == []
    assert engine._positions["SPY"]["qty"] == 2.0


def test_live_sell_ignores_open_buy_orders_for_available_quantity(monkeypatch):
    engine = _engine(
        monkeypatch,
        broker_adapter=_PositionAdapter(
            [_BrokerPosition("SPY", 2.0)],
            [_OpenOrder("SPY", "BUY", 2.0)],
        ),
    )
    engine.live_during_market_hours = True
    engine._prices["SPY"] = 50.0
    engine._positions["SPY"] = {"qty": 2.0, "avg_entry": 45.0, "high": 55.0}

    result = asyncio.run(engine.execute_sell("SPY", 50.0))

    assert result["trading_mode"] == "live"
    assert len(engine._test_broker_mgr.calls) == 1


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


def test_live_trailing_stop_uses_configured_limit_order_type(monkeypatch):
    ticker = _ticker_doc(
        enabled=True,
        avg_days=1,
        buy_percent=False,
        buy_offset=40.0,
        sell_percent=False,
        sell_offset=60.0,
        stop_percent=False,
        stop_offset=45.0,
        trailing_enabled=True,
        trailing_percent=1.0,
        trailing_percent_mode=True,
        trailing_order_type="limit",
    )
    engine = _engine(monkeypatch, ticker_doc=ticker)
    engine.live_during_market_hours = True
    engine._positions["SPY"] = {"qty": 2.0, "avg_entry": 45.0, "high": 55.0}
    engine._trailing_highs["SPY"] = 55.0
    engine._is_ticker_market_open = lambda _ticker: True

    async def persist_trade_state():
        pass

    engine._persist_trade_state = persist_trade_state
    monkeypatch.setattr(deps, "price_service", _PriceService(price=54.0, avg=50.0))
    monkeypatch.setattr(deps, "tracer", _Tracer())

    asyncio.run(engine.evaluate_ticker(ticker))

    order_template = engine._test_broker_mgr.calls[0]["order_template"]
    assert order_template["order_type"] == "LIMIT"
    assert order_template["limit_price"] == 54.0
    assert "stop_price" not in order_template


def test_live_stop_loss_uses_configured_limit_order_type(monkeypatch):
    ticker = _ticker_doc(
        enabled=True,
        avg_days=1,
        buy_percent=False,
        buy_offset=40.0,
        sell_percent=False,
        sell_offset=60.0,
        stop_percent=False,
        stop_offset=55.0,
        stop_order_type="limit",
        trailing_enabled=False,
    )
    engine = _engine(monkeypatch, ticker_doc=ticker)
    engine.live_during_market_hours = True
    engine._positions["SPY"] = {"qty": 2.0, "avg_entry": 58.0, "high": 59.0}
    engine._is_ticker_market_open = lambda _ticker: True
    monkeypatch.setattr(deps, "price_service", _PriceService(price=54.0, avg=50.0))
    monkeypatch.setattr(deps, "tracer", _Tracer())

    asyncio.run(engine.evaluate_ticker(ticker))

    order_template = engine._test_broker_mgr.calls[0]["order_template"]
    assert order_template["order_type"] == "LIMIT"
    assert order_template["limit_price"] == 54.0
    assert "stop_price" not in order_template


def test_sync_positions_from_broker_replaces_stale_internal_positions(monkeypatch):
    engine = _engine(
        monkeypatch,
        broker_positions={
            "AMD": {
                "quantity": 0.5525,
                "avg_entry": 543.01,
                "current_price": 537.5,
            },
            "NVDA": {
                "quantity": 3.5175,
                "avg_entry": 199.05,
                "current_price": 198.6,
            },
        },
    )
    engine._positions = {
        "MSFT": {"qty": 0.2602, "avg_entry": 384.34, "high": 388.0},
        "NVDA": {"qty": 0.5053, "avg_entry": 197.81, "high": 199.0},
    }
    engine._trailing_highs = {"MSFT": 388.0}

    result = asyncio.run(engine.sync_positions_from_broker("alpaca"))

    assert result["synced"] == 2
    assert result["added"] == ["AMD"]
    assert result["updated"] == ["NVDA"]
    assert result["removed"] == ["MSFT"]
    assert set(engine._positions) == {"AMD", "NVDA"}
    assert engine._positions["NVDA"]["qty"] == 3.5175
    assert "MSFT" not in engine._trailing_highs
    assert "MSFT" in engine._last_exit_ts
    saved_positions = engine._test_db.settings.updated["update"]["$set"]["value"]["positions"]
    assert set(saved_positions) == {"AMD", "NVDA"}
