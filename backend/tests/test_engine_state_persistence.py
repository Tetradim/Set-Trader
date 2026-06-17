import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import deps  # noqa: E402
from trading_engine import TradingEngine  # noqa: E402
from routes import bot as bot_routes  # noqa: E402


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass


class _Settings:
    def __init__(self):
        self.doc = None

    async def update_one(self, query, update, upsert=False):
        self.doc = {"key": query["key"], **update["$set"]}

    async def find_one(self, query, projection=None):
        if self.doc and self.doc["key"] == query["key"]:
            return self.doc
        return None


class _Db:
    def __init__(self):
        self.settings = _Settings()


def test_engine_state_persists_runtime_positions(monkeypatch):
    db = _Db()
    monkeypatch.setattr(deps, "db", db)
    monkeypatch.setattr(deps, "logger", _Logger())

    exit_ts = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    engine = TradingEngine()
    engine.running = True
    engine.paused = False
    engine.simulate_24_7 = True
    engine._positions = {
        "AAPL": {"qty": 3.4349, "avg_entry": 291.13, "high": 291.13},
        "NASA": {"qty": 33.6098, "avg_entry": 31.93, "buy_legs_filled": [0, 1, 2]},
    }
    engine._trailing_highs = {"AAPL": 292.0}
    engine._pending_sells = {"AAPL": {"limit_price": 300.0, "qty": 3.4349, "entry": 291.13}}
    engine._last_exit_ts = {"SPY": exit_ts}

    asyncio.run(engine.save_state())

    assert db.settings.doc["updated_at"]

    restored = TradingEngine()
    asyncio.run(restored.load_state())

    assert restored.running is True
    assert restored.paused is False
    assert restored.simulate_24_7 is True
    assert restored._positions == engine._positions
    assert restored._trailing_highs == engine._trailing_highs
    assert restored._pending_sells == engine._pending_sells
    assert restored._last_exit_ts["SPY"] == exit_ts


def test_bot_reload_state_endpoint_loads_saved_runtime_state(monkeypatch):
    class _Engine:
        def __init__(self):
            self.running = True
            self.paused = True
            self._positions = {"AAPL": {"qty": 1, "avg_entry": 100}}
            self.loaded = False

        async def load_state(self):
            self.loaded = True

    engine = _Engine()
    monkeypatch.setattr(bot_routes.deps, "engine", engine)

    response = asyncio.run(bot_routes.reload_bot_state())

    assert engine.loaded is True
    assert response == {"running": True, "paused": True, "positions": 1}
