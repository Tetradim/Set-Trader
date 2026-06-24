import asyncio
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import deps  # noqa: E402
from trading.broker_execution import BrokerExecutionMixin, LiveOrderExecutionError  # noqa: E402


class _BrokerManager:
    def __init__(self):
        self.calls = []

    async def place_orders_for_ticker(self, **kwargs):
        self.calls.append(kwargs)
        return [{"broker_id": "alpaca", "status": "filled"}]


class _Engine(BrokerExecutionMixin):
    def __init__(self):
        self.pre_trade_checks = []

    def is_paper_trading(self):
        return False

    async def pre_trade_check(self, symbol, side, quantity, price):
        self.pre_trade_checks.append((symbol, side, quantity, price))
        return False, "GLOBAL KILL SWITCH ACTIVE: panic stop"


def test_broker_execution_blocks_before_broker_manager_when_pretrade_rejects(monkeypatch):
    broker_mgr = _BrokerManager()
    monkeypatch.setattr(deps, "broker_mgr", broker_mgr)
    engine = _Engine()

    with pytest.raises(LiveOrderExecutionError, match="GLOBAL KILL SWITCH ACTIVE"):
        asyncio.run(
            engine._place_live_order_or_raise(
                sym="SPY",
                broker_ids=["alpaca"],
                broker_allocs={"alpaca": 100.0},
                action_label="BRACKET_BUY",
                order_template={
                    "symbol": "SPY",
                    "side": "BUY",
                    "order_type": "MARKET",
                    "price": 50.0,
                },
            )
        )

    assert broker_mgr.calls == []
    assert engine.pre_trade_checks == [("SPY", "BUY", 2.0, 50.0)]
