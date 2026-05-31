import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


class StartupRegressionTests(unittest.TestCase):
    def test_engine_state_market_hours_has_eastern_timezone(self):
        from trading.engine_state import EngineStateMixin

        class Engine(EngineStateMixin):
            pass

        self.assertIsInstance(Engine()._is_actual_market_hours(), bool)

    def test_pattern_scanner_instantiates_with_default_params(self):
        from strategies.custom.pattern_scanner import PatternScannerStrategy

        strategy = PatternScannerStrategy()

        self.assertEqual(strategy.default_params["lookback_bars"], 60)
        self.assertIsNotNone(strategy._detector)


if __name__ == "__main__":
    unittest.main()
