"""Unit tests for advanced risk-management calculations."""
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from advanced_risk import (
    AdvancedRiskLimits,
    AdvancedRiskManager,
    CircuitBreakerAdjustmentInput,
    LiquiditySizingInput,
    PortfolioPosition,
    TradeRiskInput,
    VarCvarInput,
)
from resilience_primitives import BrokerResilienceConfig


class AdvancedRiskManagerTest(unittest.TestCase):
    def setUp(self):
        self.manager = AdvancedRiskManager()

    def test_trade_risk_score_increases_for_large_volatile_illiquid_trade(self):
        conservative = TradeRiskInput(
            symbol="SPY",
            side="buy",
            order_value=1_000,
            account_equity=100_000,
            price=500,
            volatility_pct=0.01,
            average_daily_volume=75_000_000,
            broker_risk_level="low",
            existing_symbol_exposure=2_500,
            daily_drawdown_pct=0.0,
            strategy_confidence=0.9,
        )
        aggressive = TradeRiskInput(
            symbol="TSLA",
            side="buy",
            order_value=35_000,
            account_equity=100_000,
            price=200,
            volatility_pct=0.09,
            average_daily_volume=30_000,
            broker_risk_level="high",
            existing_symbol_exposure=25_000,
            daily_drawdown_pct=0.045,
            strategy_confidence=0.35,
        )

        low_risk = self.manager.score_trade(conservative)
        high_risk = self.manager.score_trade(aggressive)

        self.assertEqual(low_risk.risk_level, "low")
        self.assertGreater(high_risk.score, low_risk.score)
        self.assertEqual(high_risk.risk_level, "high")
        self.assertIn("concentration", high_risk.drivers)
        self.assertIn("volatility", high_risk.drivers)

    def test_dynamic_circuit_breaker_tightens_during_market_stress(self):
        base = BrokerResilienceConfig(
            max_rps=20.0,
            burst=30,
            failure_threshold=5,
            recovery_timeout_seconds=30,
            half_open_max_calls=2,
        )
        adjustment = CircuitBreakerAdjustmentInput(
            broker_id="alpaca",
            volatility_pct=0.10,
            liquidity_score=0.2,
            market_stress_score=0.8,
            broker_risk_level="high",
        )

        result = self.manager.recommend_circuit_breaker(base, adjustment)

        self.assertLess(result.config.max_rps, base.max_rps)
        self.assertLess(result.config.burst, base.burst)
        self.assertLessEqual(result.config.failure_threshold, base.failure_threshold)
        self.assertGreater(result.config.recovery_timeout_seconds, base.recovery_timeout_seconds)
        self.assertGreater(result.stress_score, 0.7)
        self.assertIn("market volatility", result.reasons)

    def test_liquidity_sizing_caps_requested_order_by_predicted_volume(self):
        sizing = LiquiditySizingInput(
            symbol="THIN",
            requested_order_value=25_000,
            price=50,
            account_equity=100_000,
            average_daily_volume=10_000,
            recent_volume=2_000,
            max_participation_rate=0.02,
            volatility_pct=0.03,
            risk_score=76,
        )

        result = self.manager.recommend_position_size(sizing)

        self.assertLess(result.recommended_order_value, sizing.requested_order_value)
        self.assertLessEqual(result.recommended_shares, 200)
        self.assertEqual(result.constraint, "liquidity")
        self.assertIn("predicted volume", result.reason)

    def test_var_cvar_limits_block_tail_loss_breach(self):
        request = VarCvarInput(
            positions=[
                PortfolioPosition(symbol="SPY", quantity=100, price=500),
                PortfolioPosition(symbol="QQQ", quantity=80, price=400),
            ],
            historical_returns={
                "SPY": [-0.010, -0.015, -0.020, -0.090, 0.006, 0.004],
                "QQQ": [-0.012, -0.018, -0.025, -0.110, 0.005, 0.003],
            },
            confidence_level=0.95,
            limits=AdvancedRiskLimits(max_var_pct=0.03, max_cvar_pct=0.04),
        )

        result = self.manager.evaluate_var_cvar(request)

        self.assertFalse(result.is_allowed)
        self.assertGreater(result.var_pct, 0.03)
        self.assertGreaterEqual(result.cvar_value, result.var_value)
        self.assertIn("CVaR", result.message)


if __name__ == "__main__":
    unittest.main()
