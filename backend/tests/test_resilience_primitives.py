"""Regression tests for resilience primitive import and construction behavior."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from resilience_primitives import BrokerResilienceConfig, CircuitBreakerState, CircuitState


class ResiliencePrimitiveTest(unittest.TestCase):
    def test_broker_resilience_config_accepts_overrides(self):
        config = BrokerResilienceConfig(max_rps=2.5, burst=7, skip_during_opening=True)

        self.assertEqual(config.max_rps, 2.5)
        self.assertEqual(config.burst, 7)
        self.assertTrue(config.skip_during_opening)

    def test_circuit_breaker_state_has_independent_failure_windows(self):
        first = CircuitBreakerState()
        second = CircuitBreakerState()

        first.failure_timestamps.append(datetime.now(timezone.utc))

        self.assertEqual(first.state, CircuitState.CLOSED)
        self.assertEqual(len(first.failure_timestamps), 1)
        self.assertEqual(len(second.failure_timestamps), 0)


if __name__ == "__main__":
    unittest.main()
