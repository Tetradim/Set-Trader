import asyncio
import sys
from copy import deepcopy
from datetime import datetime, timezone
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


class _WsManager:
    def __init__(self):
        self.messages = []

    async def broadcast(self, message):
        self.messages.append(message)


class _Telegram:
    running = False

    def __init__(self):
        self.alerts = []
        self.trades = []

    async def send_trade_alert(self, trade):
        self.trades.append(trade)

    async def _broadcast_alert(self, message):
        self.alerts.append(message)


class _PriceTape:
    def __init__(self, prices_by_symbol, avg_by_symbol=None):
        self.prices_by_symbol = {k: list(v) for k, v in prices_by_symbol.items()}
        self.avg_by_symbol = dict(avg_by_symbol or {})
        self.last_price = {}

    async def get_price(self, symbol):
        tape = self.prices_by_symbol.setdefault(symbol, [self.avg_by_symbol.get(symbol, 100.0)])
        if len(tape) > 1:
            price = tape.pop(0)
        else:
            price = tape[0]
        self.last_price[symbol] = float(price)
        return float(price)

    async def get_avg_price(self, symbol, _days):
        return float(self.avg_by_symbol.get(symbol, self.last_price.get(symbol, 100.0)))

    async def get_enriched_market_data(self, ticker_doc):
        return {"current_price": self.last_price.get(ticker_doc["symbol"], 100.0)}


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    async def to_list(self, length):
        if length is None:
            return list(self.docs)
        return list(self.docs)[:length]


def _matches(doc, query):
    for key, expected in (query or {}).items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$lt" in expected and not (actual < expected["$lt"]):
                return False
            if "$gte" in expected and not (actual >= expected["$gte"]):
                return False
            continue
        if actual != expected:
            return False
    return True


class _Collection:
    def __init__(self, docs=None, key_field=None):
        self.docs = [deepcopy(doc) for doc in (docs or [])]
        self.key_field = key_field

    async def insert_one(self, doc):
        self.docs.append(deepcopy(doc))
        return SimpleNamespace(inserted_id=doc.get("id"))

    def find(self, query=None, projection=None):
        docs = [deepcopy(doc) for doc in self.docs if _matches(doc, query or {})]
        if projection and projection.get("_id") == 0:
            for doc in docs:
                doc.pop("_id", None)
        return _Cursor(docs)

    async def find_one(self, query, projection=None, sort=None):
        docs = [doc for doc in self.docs if _matches(doc, query or {})]
        if sort:
            field, direction = sort[0]
            docs = sorted(docs, key=lambda item: item.get(field, ""), reverse=direction < 0)
        if not docs:
            return None
        result = deepcopy(docs[0])
        if projection and projection.get("_id") == 0:
            result.pop("_id", None)
        return result

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if _matches(doc, query or {}):
                self._apply_update(doc, update)
                return SimpleNamespace(matched_count=1, modified_count=1)
        if upsert:
            doc = deepcopy(query or {})
            self._apply_update(doc, update)
            self.docs.append(doc)
            return SimpleNamespace(matched_count=0, modified_count=1, upserted_id=True)
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def update_many(self, query, update):
        count = 0
        for doc in self.docs:
            if _matches(doc, query or {}):
                self._apply_update(doc, update)
                count += 1
        return SimpleNamespace(matched_count=count, modified_count=count)

    def aggregate(self, _pipeline):
        losses = [doc for doc in self.docs if doc.get("pnl", 0) < 0]
        total = sum(doc.get("pnl", 0) for doc in losses)
        return _Cursor([{"_id": None, "total_loss": total}] if losses else [])

    def _apply_update(self, doc, update):
        for key, value in update.get("$set", {}).items():
            doc[key] = deepcopy(value)
        for key, value in update.get("$inc", {}).items():
            doc[key] = doc.get(key, 0) + value
        for key in update.get("$unset", {}):
            doc.pop(key, None)


class _Db:
    def __init__(self, tickers):
        self.tickers = _Collection(tickers, key_field="symbol")
        self.trades = _Collection()
        self.profits = _Collection(key_field="symbol")
        self.settings = _Collection(key_field="key")


class _BrokerMgr:
    def __init__(self, results):
        self.results = results
        self.calls = []

    async def place_orders_for_ticker(self, broker_ids, allocations, order_template):
        self.calls.append({
            "broker_ids": list(broker_ids),
            "allocations": dict(allocations),
            "order_template": deepcopy(order_template),
        })
        return deepcopy(self.results)


@pytest.fixture
def engine_env(monkeypatch):
    tickers = [
        {
            "symbol": "TIGHT",
            "enabled": True,
            "strategy": "custom",
            "base_power": 1_000.0,
            "avg_days": 1,
            "buy_percent": False,
            "buy_offset": 99.95,
            "buy_order_type": "limit",
            "sell_percent": False,
            "sell_offset": 100.05,
            "sell_order_type": "limit",
            "stop_percent": False,
            "stop_offset": 99.70,
            "stop_order_type": "limit",
            "trailing_enabled": False,
            "broker_ids": [],
            "broker_allocations": {},
            "compound_profits": False,
            "reentry_cooldown_seconds": 0,
        },
        {
            "symbol": "PART",
            "enabled": True,
            "strategy": "custom",
            "base_power": 900.0,
            "avg_days": 1,
            "partial_fills_enabled": True,
            "buy_legs": [
                {"offset": 99.95, "is_percent": False, "alloc_pct": 40},
                {"offset": 99.90, "is_percent": False, "alloc_pct": 30},
                {"offset": 99.85, "is_percent": False, "alloc_pct": 30},
            ],
            "sell_legs": [
                {"offset": 100.05, "is_percent": False, "alloc_pct": 50},
                {"offset": 100.10, "is_percent": False, "alloc_pct": 100},
            ],
            "stop_percent": False,
            "stop_offset": 99.50,
            "stop_order_type": "limit",
            "trailing_enabled": True,
            "trailing_percent": 1.0,
            "trailing_percent_mode": True,
            "trailing_order_type": "limit",
            "broker_ids": [],
            "broker_allocations": {},
            "compound_profits": False,
            "reentry_cooldown_seconds": 0,
        },
        {
            "symbol": "REB",
            "enabled": True,
            "strategy": "custom",
            "base_power": 100.0,
            "avg_days": 1,
            "buy_percent": False,
            "buy_offset": 99.0,
            "sell_percent": False,
            "sell_offset": 101.0,
            "auto_rebracket": True,
            "rebracket_threshold": 0.20,
            "rebracket_min_drift": 0.05,
            "rebracket_spread": 0.80,
            "rebracket_lookback": 3,
            "rebracket_buffer": 0.10,
            "rebracket_cooldown": 0,
            "broker_ids": [],
            "broker_allocations": {},
            "reentry_cooldown_seconds": 0,
        },
    ]
    db = _Db(tickers)
    price_service = _PriceTape(
        {
            "TIGHT": [99.94, 100.06],
            "PART": [99.94, 99.89, 99.84, 100.06, 100.11],
            "REB": [102.0, 102.5, 103.0],
            "ORD": [100.0],
        },
        {"TIGHT": 100.0, "PART": 100.0, "REB": 100.0, "ORD": 100.0},
    )
    monkeypatch.setattr(deps, "tracer", _Tracer())
    monkeypatch.setattr(deps, "logger", _Logger())
    monkeypatch.setattr(deps, "db", db)
    monkeypatch.setattr(deps, "price_service", price_service)
    monkeypatch.setattr(deps, "ws_manager", _WsManager())
    monkeypatch.setattr(deps, "telegram_service", _Telegram())
    monkeypatch.setattr(deps, "broker_mgr", SimpleNamespace())

    engine = TradingEngine()
    engine.simulate_24_7 = True
    engine.TRADE_COOLDOWN_SECS = 0
    engine.REENTRY_COOLDOWN_SECS = 0
    engine._is_ticker_market_open = lambda _ticker_doc: True
    engine._is_opening_window = lambda *_args, **_kwargs: False
    engine._is_past_opening_window = lambda *_args, **_kwargs: False
    monkeypatch.setattr(deps, "engine", engine)
    return SimpleNamespace(engine=engine, db=db, price_service=price_service)


def _ticker(env, symbol):
    return next(doc for doc in env.db.tickers.docs if doc["symbol"] == symbol)


def test_tight_gap_stress_cycles_bracket_and_partial_fill_features(engine_env):
    env = engine_env

    async def run():
        for _ in range(2):
            await env.engine.evaluate_ticker(_ticker(env, "TIGHT"))
        for _ in range(5):
            await env.engine.evaluate_ticker(_ticker(env, "PART"))

    asyncio.run(run())

    tight_trades = [trade for trade in env.db.trades.docs if trade["symbol"] == "TIGHT"]
    part_trades = [trade for trade in env.db.trades.docs if trade["symbol"] == "PART"]

    assert [trade["side"] for trade in tight_trades] == ["BUY", "SELL"]
    assert tight_trades[0]["order_type"] == "LIMIT"
    assert tight_trades[1]["pnl"] > 0
    assert [trade["side"] for trade in part_trades] == ["BUY", "BUY", "BUY", "SELL", "SELL"]
    assert env.engine._positions["PART"]["qty"] == 0
    assert "PART" not in env.engine._trailing_highs


def test_gap_widening_stress_runs_repeated_cycles_without_state_leaks(engine_env):
    env = engine_env
    ticker = {
        "symbol": "GAP",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 1,
        "buy_percent": False,
        "buy_offset": 99.98,
        "buy_order_type": "limit",
        "sell_percent": False,
        "sell_offset": 100.02,
        "sell_order_type": "limit",
        "stop_percent": False,
        "stop_offset": 98.0,
        "stop_order_type": "limit",
        "trailing_enabled": True,
        "trailing_percent": 5.0,
        "trailing_percent_mode": True,
        "trailing_order_type": "limit",
        "auto_rebracket": True,
        "rebracket_threshold": 2.0,
        "broker_ids": [],
        "broker_allocations": {},
        "compound_profits": False,
        "reentry_cooldown_seconds": 0,
    }
    env.db.tickers.docs.append(deepcopy(ticker))

    async def run_phase(gap):
        ticker["buy_offset"] = round(100.0 - gap, 2)
        ticker["sell_offset"] = round(100.0 + gap, 2)
        env.price_service.prices_by_symbol["GAP"] = []
        for _ in range(8):
            env.price_service.prices_by_symbol["GAP"].extend(
                [round(100.0 - gap - 0.01, 2), round(100.0 + gap + 0.01, 2)]
            )

        before = len([trade for trade in env.db.trades.docs if trade["symbol"] == "GAP"])
        for _ in range(16):
            await env.engine.evaluate_ticker(ticker)
        after = len([trade for trade in env.db.trades.docs if trade["symbol"] == "GAP"])
        return after - before

    async def run():
        return [await run_phase(gap) for gap in (0.02, 0.05, 0.10, 0.25, 0.50)]

    phase_trade_counts = asyncio.run(run())
    gap_trades = [trade for trade in env.db.trades.docs if trade["symbol"] == "GAP"]

    assert phase_trade_counts == [16, 16, 16, 16, 16]
    assert [trade["side"] for trade in gap_trades[0:4]] == ["BUY", "SELL", "BUY", "SELL"]
    assert gap_trades[-1]["side"] == "SELL"
    assert env.engine._positions["GAP"]["qty"] == 0
    assert "GAP" not in env.engine._pending_sells
    assert "GAP" not in env.engine._trailing_highs


def test_live_buy_with_empty_broker_results_does_not_create_internal_position(engine_env):
    env = engine_env
    ticker = {
        "symbol": "LIVEBUY",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 1,
        "buy_percent": False,
        "buy_offset": 100.0,
        "buy_order_type": "limit",
        "sell_percent": False,
        "sell_offset": 110.0,
        "stop_percent": False,
        "stop_offset": 90.0,
        "trailing_enabled": False,
        "broker_ids": ["b1"],
        "broker_allocations": {"b1": 1_000.0},
        "compound_profits": False,
    }
    env.db.tickers.docs.append(deepcopy(ticker))
    env.price_service.prices_by_symbol["LIVEBUY"] = [99.0]
    deps.broker_mgr = _BrokerMgr([])
    env.engine.simulate_24_7 = False
    env.engine.live_during_market_hours = True

    asyncio.run(env.engine.evaluate_ticker(ticker))

    assert [trade for trade in env.db.trades.docs if trade["symbol"] == "LIVEBUY"] == []
    assert env.engine._positions.get("LIVEBUY", {}).get("qty", 0) == 0


def test_live_buy_with_submitted_broker_result_does_not_create_internal_position(engine_env):
    env = engine_env
    ticker = {
        "symbol": "LIVESUB",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 1,
        "buy_percent": False,
        "buy_offset": 100.0,
        "buy_order_type": "limit",
        "sell_percent": False,
        "sell_offset": 110.0,
        "stop_percent": False,
        "stop_offset": 90.0,
        "trailing_enabled": False,
        "broker_ids": ["b1"],
        "broker_allocations": {"b1": 1_000.0},
        "compound_profits": False,
    }
    env.db.tickers.docs.append(deepcopy(ticker))
    env.price_service.prices_by_symbol["LIVESUB"] = [99.0]
    deps.broker_mgr = _BrokerMgr([{"broker_id": "b1", "status": "submitted", "order_id": "abc-123"}])
    env.engine.simulate_24_7 = False
    env.engine.live_during_market_hours = True

    asyncio.run(env.engine.evaluate_ticker(ticker))

    assert [trade for trade in env.db.trades.docs if trade["symbol"] == "LIVESUB"] == []
    assert env.engine._positions.get("LIVESUB", {}).get("qty", 0) == 0


@pytest.mark.parametrize(
    ("symbol", "price", "ticker_updates", "trailing_high"),
    [
        ("LIVESELL", 111.0, {"sell_offset": 110.0, "stop_offset": 90.0, "trailing_enabled": False}, None),
        ("LIVESTOP", 89.0, {"sell_offset": 120.0, "stop_offset": 90.0, "trailing_enabled": False}, None),
        (
            "LIVETRAIL",
            108.0,
            {"sell_offset": 120.0, "stop_offset": 90.0, "trailing_enabled": True, "trailing_percent": 1.0},
            110.0,
        ),
    ],
)
def test_live_exit_with_all_broker_errors_keeps_position_open(engine_env, symbol, price, ticker_updates, trailing_high):
    env = engine_env
    ticker = {
        "symbol": symbol,
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 1,
        "buy_percent": False,
        "buy_offset": 90.0,
        "sell_percent": False,
        "sell_order_type": "limit",
        "stop_percent": False,
        "stop_order_type": "limit",
        "trailing_percent_mode": True,
        "trailing_order_type": "limit",
        "broker_ids": ["b1"],
        "broker_allocations": {"b1": 1_000.0},
        "compound_profits": False,
        **ticker_updates,
    }
    env.db.tickers.docs.append(deepcopy(ticker))
    env.engine._positions[symbol] = {"qty": 10.0, "avg_entry": 100.0, "high": 100.0}
    if trailing_high is not None:
        env.engine._trailing_highs[symbol] = trailing_high
    env.price_service.prices_by_symbol[symbol] = [price]
    deps.broker_mgr = _BrokerMgr([{"broker_id": "b1", "status": "error", "error": "broker down"}])
    env.engine.simulate_24_7 = False
    env.engine.live_during_market_hours = True

    asyncio.run(env.engine.evaluate_ticker(ticker))

    assert [trade for trade in env.db.trades.docs if trade["symbol"] == symbol] == []
    assert env.engine._positions[symbol]["qty"] == 10.0


def test_market_sell_order_type_waits_for_sell_target(engine_env):
    env = engine_env
    ticker = {
        "symbol": "ORD",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 1,
        "buy_percent": False,
        "buy_offset": 90.0,
        "sell_percent": False,
        "sell_offset": 110.0,
        "sell_order_type": "market",
        "stop_percent": False,
        "stop_offset": 90.0,
        "stop_order_type": "limit",
        "trailing_enabled": False,
        "broker_ids": [],
        "broker_allocations": {},
        "compound_profits": False,
    }
    env.db.tickers.docs.append(deepcopy(ticker))
    env.engine._positions["ORD"] = {"qty": 10.0, "avg_entry": 100.0, "high": 100.0}

    asyncio.run(env.engine.evaluate_ticker(ticker))

    assert [trade["side"] for trade in env.db.trades.docs if trade["symbol"] == "ORD"] == []
    assert env.engine._positions["ORD"]["qty"] == 10.0


def test_market_stop_order_type_waits_for_stop_threshold(engine_env):
    env = engine_env
    ticker = {
        "symbol": "ORD",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 1,
        "buy_percent": False,
        "buy_offset": 90.0,
        "sell_percent": False,
        "sell_offset": 120.0,
        "sell_order_type": "limit",
        "stop_percent": False,
        "stop_offset": 95.0,
        "stop_order_type": "market",
        "trailing_enabled": False,
        "broker_ids": [],
        "broker_allocations": {},
        "compound_profits": False,
    }
    env.db.tickers.docs.append(deepcopy(ticker))
    env.engine._positions["ORD"] = {"qty": 10.0, "avg_entry": 100.0, "high": 100.0}

    asyncio.run(env.engine.evaluate_ticker(ticker))

    assert [trade["side"] for trade in env.db.trades.docs if trade["symbol"] == "ORD"] == []
    assert env.engine._positions["ORD"]["qty"] == 10.0


def test_market_trailing_order_type_waits_for_trailing_threshold(engine_env):
    env = engine_env
    ticker = {
        "symbol": "ORD",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 1,
        "buy_percent": False,
        "buy_offset": 90.0,
        "sell_percent": False,
        "sell_offset": 120.0,
        "sell_order_type": "limit",
        "stop_percent": False,
        "stop_offset": 90.0,
        "stop_order_type": "limit",
        "trailing_enabled": True,
        "trailing_percent": 1.0,
        "trailing_percent_mode": True,
        "trailing_order_type": "market",
        "broker_ids": [],
        "broker_allocations": {},
        "compound_profits": False,
    }
    env.db.tickers.docs.append(deepcopy(ticker))
    env.engine._positions["ORD"] = {"qty": 10.0, "avg_entry": 100.0, "high": 100.0}
    env.engine._trailing_highs["ORD"] = 110.0
    env.price_service.prices_by_symbol["ORD"] = [109.5]

    asyncio.run(env.engine.evaluate_ticker(ticker))

    assert [trade["side"] for trade in env.db.trades.docs if trade["symbol"] == "ORD"] == []
    assert env.engine._positions["ORD"]["qty"] == 10.0
    assert env.engine._trailing_highs["ORD"] == 110.0


def test_halved_opening_stop_uses_tightened_threshold(engine_env):
    env = engine_env
    ticker = {
        "symbol": "ORD",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 1,
        "buy_percent": False,
        "buy_offset": 90.0,
        "sell_percent": False,
        "sell_offset": 120.0,
        "sell_order_type": "limit",
        "stop_percent": False,
        "stop_offset": 94.0,
        "stop_order_type": "limit",
        "halve_stop_at_open": True,
        "trailing_enabled": False,
        "broker_ids": [],
        "broker_allocations": {},
        "compound_profits": False,
    }
    env.db.tickers.docs.append(deepcopy(ticker))
    env.engine._positions["ORD"] = {"qty": 10.0, "avg_entry": 100.0, "high": 100.0}
    env.engine._is_opening_window = lambda *_args, **_kwargs: True
    env.price_service.prices_by_symbol["ORD"] = [96.5]

    asyncio.run(env.engine.evaluate_ticker(ticker))

    ord_trades = [trade for trade in env.db.trades.docs if trade["symbol"] == "ORD"]
    assert [trade["side"] for trade in ord_trades] == ["STOP"]
    assert ord_trades[0]["target_price"] == 94.0
    assert env.engine._positions["ORD"]["qty"] == 0


def test_wait_day_after_buy_still_allows_stop_loss_exit(engine_env):
    env = engine_env
    ticker = {
        "symbol": "WAITSTOP",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 1,
        "buy_percent": False,
        "buy_offset": 90.0,
        "sell_percent": False,
        "sell_offset": 120.0,
        "stop_percent": False,
        "stop_offset": 95.0,
        "stop_order_type": "limit",
        "wait_day_after_buy": True,
        "trailing_enabled": False,
        "broker_ids": [],
        "broker_allocations": {},
        "compound_profits": False,
    }
    env.db.tickers.docs.append(deepcopy(ticker))
    env.engine._positions["WAITSTOP"] = {"qty": 10.0, "avg_entry": 100.0, "high": 100.0}
    env.price_service.prices_by_symbol["WAITSTOP"] = [94.0]
    env.db.trades.docs.append({
        "symbol": "WAITSTOP",
        "side": "BUY",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    asyncio.run(env.engine.evaluate_ticker(ticker))

    trades = [trade for trade in env.db.trades.docs if trade["symbol"] == "WAITSTOP" and trade["side"] == "STOP"]
    assert len(trades) == 1
    assert env.engine._positions["WAITSTOP"]["qty"] == 0


def test_partial_fill_trailing_lock_at_open_keeps_remaining_position(engine_env):
    env = engine_env
    ticker = {
        "symbol": "PARTLOCK",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 1,
        "partial_fills_enabled": True,
        "buy_legs": [],
        "sell_legs": [],
        "stop_percent": False,
        "stop_offset": 90.0,
        "trailing_enabled": True,
        "trailing_percent": 1.0,
        "trailing_percent_mode": True,
        "trailing_order_type": "limit",
        "lock_trailing_at_open": True,
        "broker_ids": [],
        "broker_allocations": {},
        "compound_profits": False,
    }
    env.db.tickers.docs.append(deepcopy(ticker))
    env.engine._positions["PARTLOCK"] = {
        "qty": 10.0,
        "avg_entry": 100.0,
        "buy_legs_filled": [0],
        "sell_legs_filled": [],
    }
    env.engine._trailing_highs["PARTLOCK"] = 110.0
    env.engine._is_opening_window = lambda *_args, **_kwargs: True
    env.price_service.prices_by_symbol["PARTLOCK"] = [108.0]

    asyncio.run(env.engine.evaluate_ticker(ticker))

    assert [trade for trade in env.db.trades.docs if trade["symbol"] == "PARTLOCK"] == []
    assert env.engine._positions["PARTLOCK"]["qty"] == 10.0
    assert env.engine._trailing_highs["PARTLOCK"] == 110.0


def test_auto_rebracket_does_not_recenter_immediately_after_buy(engine_env):
    env = engine_env
    ticker = _ticker(env, "REB")
    ticker["buy_offset"] = 103.0
    ticker["sell_offset"] = 104.0
    env.price_service.prices_by_symbol["REB"] = [102.0]

    asyncio.run(env.engine.evaluate_ticker(ticker))

    updated = _ticker(env, "REB")
    assert env.engine._positions["REB"]["qty"] > 0
    assert "prev_bracket" not in updated
    assert updated["buy_offset"] == 103.0
    assert updated["sell_offset"] == 104.0


def test_auto_rebracket_converts_percent_config_to_absolute_bracket(engine_env):
    env = engine_env
    ticker = {
        "symbol": "PCTREB",
        "enabled": True,
        "strategy": "custom",
        "base_power": 100.0,
        "avg_days": 30,
        "buy_percent": True,
        "buy_offset": -3.0,
        "sell_percent": True,
        "sell_offset": 3.0,
        "auto_rebracket": True,
        "rebracket_threshold": 2.0,
        "rebracket_min_drift": 0.50,
        "rebracket_spread": 0.80,
        "rebracket_buffer": 0.10,
        "rebracket_lookback": 3,
        "rebracket_cooldown": 0,
        "broker_ids": [],
        "broker_allocations": {},
    }
    env.db.tickers.docs.append(deepcopy(ticker))

    asyncio.run(env.engine._auto_rebracket("PCTREB", ticker, 120.0, 97.0, 103.0))

    updated = _ticker(env, "PCTREB")
    assert updated["buy_percent"] is False
    assert updated["sell_percent"] is False
    assert updated["buy_offset"] == 119.9
    assert updated["sell_offset"] == 120.7
    assert updated["prev_bracket"]["buy_offset"] == -3.0
    assert updated["prev_bracket"]["sell_offset"] == 3.0
    assert updated["prev_bracket"]["buy_percent"] is True
    assert updated["prev_bracket"]["sell_percent"] is True
    state_doc = next(doc for doc in env.db.settings.docs if doc["key"] == "engine_state")
    assert "PCTREB" in state_doc["value"]["last_rebracket_ts"]


def test_opening_bell_post_window_sets_real_absolute_bracket(engine_env):
    env = engine_env
    ticker = {
        "symbol": "OPENRB",
        "enabled": True,
        "strategy": "custom",
        "base_power": 1_000.0,
        "avg_days": 30,
        "buy_percent": False,
        "buy_offset": 90.0,
        "sell_percent": False,
        "sell_offset": 110.0,
        "sell_order_type": "limit",
        "stop_percent": False,
        "stop_offset": 80.0,
        "trailing_enabled": False,
        "opening_bell_enabled": True,
        "rebracket_spread": 0.80,
        "rebracket_buffer": 0.10,
        "broker_ids": [],
        "broker_allocations": {},
        "compound_profits": False,
    }
    env.db.tickers.docs.append(deepcopy(ticker))
    env.engine._positions["OPENRB"] = {"qty": 10.0, "avg_entry": 100.0, "high": 100.0}
    env.engine._opening_bell_highs["OPENRB"] = 105.0
    env.engine._is_opening_window = lambda *_args, **_kwargs: False
    env.engine._is_past_opening_window = lambda *_args, **_kwargs: True
    env.price_service.prices_by_symbol["OPENRB"] = [104.0]

    asyncio.run(env.engine.evaluate_ticker(ticker))

    updated = _ticker(env, "OPENRB")
    assert updated["buy_percent"] is False
    assert updated["sell_percent"] is False
    assert updated["buy_offset"] == 104.9
    assert updated["sell_offset"] == 105.7
    assert updated["prev_bracket"]["buy_offset"] == 90.0
    assert updated["prev_bracket"]["sell_offset"] == 110.0


def test_manual_pending_sell_and_rebracket_revert_paths(engine_env):
    env = engine_env
    env.engine._positions["TIGHT"] = {"qty": 10.0, "avg_entry": 100.0, "high": 100.0}
    env.engine._prices["TIGHT"] = 100.0

    async def run():
        pending = await env.engine.manual_sell("TIGHT", "limit", 101.0)
        env.engine._prices["TIGHT"] = 101.25
        await env.engine.check_pending_sells()
        await env.engine._auto_rebracket("REB", _ticker(env, "REB"), 102.0, 99.0, 101.0)
        reverted = await env.engine.revert_bracket("REB")
        return pending, reverted

    pending, reverted = asyncio.run(run())

    tight_trades = [trade for trade in env.db.trades.docs if trade["symbol"] == "TIGHT"]
    reb = _ticker(env, "REB")

    assert pending["status"] == "pending"
    assert [trade["side"] for trade in tight_trades] == ["SELL"]
    assert "TIGHT" not in env.engine._pending_sells
    assert reverted["success"] is True
    assert reb["buy_offset"] == 99.0
    assert reb["sell_offset"] == 101.0
    assert "prev_bracket" not in reb
