"""Regression tests for Edge execution-intent v3 supervisory directives."""
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from trading import edge_handoff_contract_patch as supervision  # noqa: E402


class _Action:
    def __init__(self, value):
        self.value = value


class _Body:
    def __init__(self, *, action, intent, price=110.0):
        self.symbol = "AAPL"
        self.action = _Action(action)
        self.idempotency_key = f"edge:AAPL:{action}:market_open:123:supervision"
        self.reason = "Edge supervisory thesis"
        self.metadata = {
            "price": price,
            "execution_intent": {
                "contract_version": "edge.execution_intent.v3",
                "intent_id": self.idempotency_key,
                "expires_at": time.time() + 60,
                **intent,
            },
        }


class _TickerCollection:
    def __init__(self, ticker):
        self.ticker = dict(ticker)
        self.updates = []

    async def find_one(self, query, projection=None):
        return dict(self.ticker) if query.get("symbol") == self.ticker.get("symbol") else None

    async def update_one(self, query, update):
        self.updates.append((query, update))
        self.ticker.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1)


class _Engine:
    def __init__(self, qty=10.0):
        self._positions = {"AAPL": {"qty": qty, "avg_entry": 100.0, "high": 115.0}}
        self.calls = []

    async def execute_reduce_position(self, symbol, quantity, price, reason):
        self.calls.append((symbol, quantity, price, reason))
        remaining = round(self._positions[symbol]["qty"] - quantity, 8)
        self._positions[symbol]["qty"] = remaining
        return {"quantity": quantity, "remaining_quantity": remaining, "price": price}


class _EdgeModule:
    def __init__(self, *, ticker=None, qty=10.0):
        ticker = ticker or {
            "symbol": "AAPL",
            "stop_offset": -6.0,
            "stop_percent": True,
        }
        self.engine = _Engine(qty=qty)
        self.deps = SimpleNamespace(
            engine=self.engine,
            db=SimpleNamespace(tickers=_TickerCollection(ticker)),
        )

    def _current_position(self, symbol):
        return self.engine._positions.get(symbol, {})

    async def _handoff_price(self, symbol, body):
        return float(body.metadata["price"])

    @staticmethod
    def _handoff_response(body, *, accepted, status, reason, message=""):
        return {
            "accepted": accepted,
            "sent": accepted,
            "status": status,
            "reason": reason,
            "message": message,
            "symbol": body.symbol,
            "action": body.action.value,
        }


class EdgeSupervisionIntentV3Tests(unittest.IsolatedAsyncioTestCase):
    async def test_absolute_stop_is_persisted_as_price_not_offset(self):
        edge = _EdgeModule()
        body = _Body(
            action="tighten_stop",
            intent={
                "directive": "set_stop",
                "stop_policy": {"type": "absolute", "stop_price": 97.5, "tighten_only": True},
            },
        )

        response = await supervision._apply_execution_intent(edge, body)

        self.assertTrue(response["accepted"])
        self.assertEqual("set_stop", response["directive"])
        self.assertEqual(97.5, edge.deps.db.tickers.ticker["stop_offset"])
        self.assertFalse(edge.deps.db.tickers.ticker["stop_percent"])

    async def test_stop_widening_is_rejected_by_default(self):
        edge = _EdgeModule()
        body = _Body(
            action="tighten_stop",
            intent={
                "directive": "set_stop",
                "stop_policy": {"type": "absolute", "stop_price": 90.0, "tighten_only": True},
            },
        )

        response = await supervision._apply_execution_intent(edge, body)

        self.assertFalse(response["accepted"])
        self.assertEqual("stop_widening_blocked", response["reason"])
        self.assertEqual([], edge.deps.db.tickers.updates)

    async def test_stop_above_market_is_rejected_instead_of_triggering_accidental_exit(self):
        edge = _EdgeModule()
        body = _Body(
            action="tighten_stop",
            price=105.0,
            intent={
                "directive": "set_stop",
                "stop_policy": {"type": "absolute", "stop_price": 106.0},
            },
        )

        response = await supervision._apply_execution_intent(edge, body)

        self.assertFalse(response["accepted"])
        self.assertEqual("stop_not_below_market", response["reason"])

    async def test_reduce_percent_executes_partial_market_sell_with_position_guard(self):
        edge = _EdgeModule(qty=10.0)
        body = _Body(
            action="sell",
            intent={
                "directive": "reduce_position",
                "quantity_policy": {"type": "reduce_percent", "reduce_percent": 40.0},
                "position_guard": {"expected_quantity": 10.0, "max_quantity_drift_percent": 1.0},
            },
        )

        response = await supervision._apply_execution_intent(edge, body)

        self.assertTrue(response["accepted"])
        self.assertEqual("reduce_position", response["directive"])
        self.assertEqual(4.0, response["executed_quantity"])
        self.assertEqual(6.0, response["remaining_quantity"])
        self.assertEqual(("AAPL", 4.0, 110.0, "Edge supervisory thesis"), edge.engine.calls[0])

    async def test_position_guard_blocks_stale_edge_quantity(self):
        edge = _EdgeModule(qty=7.0)
        body = _Body(
            action="sell",
            intent={
                "directive": "reduce_position",
                "quantity_policy": {"type": "reduce_percent", "reduce_percent": 50.0},
                "position_guard": {"expected_quantity": 10.0, "max_quantity_drift_percent": 2.0},
            },
        )

        response = await supervision._apply_execution_intent(edge, body)

        self.assertFalse(response["accepted"])
        self.assertEqual("position_guard_mismatch", response["reason"])
        self.assertEqual([], edge.engine.calls)

    async def test_partial_shared_sell_restores_unsold_position(self):
        engine = SimpleNamespace(
            _positions={"AAPL": {"qty": 10.0, "avg_entry": 100.0, "high": 115.0}},
        )

        async def destructive_sell(self, sym, price, qty, entry, order_type, reason):
            self._positions[sym] = {"qty": 0, "avg_entry": 0, "high": 0}
            return {"quantity": qty, "price": price}

        with patch.object(supervision, "_original_shared_sell", destructive_sell):
            result = await supervision._shared_sell_with_remaining_position(
                engine,
                "AAPL",
                110.0,
                4.0,
                100.0,
                "MARKET",
                "test reduction",
            )

        self.assertEqual(6.0, engine._positions["AAPL"]["qty"])
        self.assertEqual(100.0, engine._positions["AAPL"]["avg_entry"])
        self.assertEqual(6.0, result["remaining_quantity"])


if __name__ == "__main__":
    unittest.main()
