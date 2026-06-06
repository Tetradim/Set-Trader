import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from schemas import TickerUpdate


class TickerUpdateSchemaTest(unittest.TestCase):
    def test_ticker_update_accepts_broker_and_strategy_fields(self):
        update = TickerUpdate(
            broker_id="alpaca",
            broker_ids=["alpaca", "ibkr"],
            broker_allocations={"alpaca": 100.0},
            strategy="RSI",
            strategy_config={"rsi_period": 14},
        )

        dumped = update.model_dump(exclude_none=True)
        self.assertEqual("alpaca", dumped["broker_id"])
        self.assertEqual(["alpaca", "ibkr"], dumped["broker_ids"])
        self.assertEqual({"alpaca": 100.0}, dumped["broker_allocations"])
        self.assertEqual("RSI", dumped["strategy"])
        self.assertEqual({"rsi_period": 14}, dumped["strategy_config"])


if __name__ == "__main__":
    unittest.main()
