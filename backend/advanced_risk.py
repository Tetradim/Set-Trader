"""Advanced risk-management calculations for Sentinel Pulse.

The functions here are deterministic and dependency-light so every risk
decision can be inspected, tested, and explained before a trade is allowed.
"""
from dataclasses import asdict, dataclass, field
from math import ceil
from typing import Dict, List, Optional

from risk_controls import OrderRestriction, RiskCheckResult
from resilience_primitives import BrokerResilienceConfig


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _broker_risk_weight(level: str) -> float:
    weights = {
        "low": 0.15,
        "medium": 0.55,
        "high": 1.0,
    }
    return weights.get((level or "medium").lower(), 0.55)


@dataclass(frozen=True)
class AdvancedRiskLimits:
    """Portfolio tail-risk limits expressed as percentages of portfolio value."""

    max_trade_risk_score: float = 85.0
    max_var_pct: float = 0.05
    max_cvar_pct: float = 0.08


@dataclass(frozen=True)
class TradeRiskInput:
    """Inputs used to score the risk of a proposed trade."""

    symbol: str
    side: str
    order_value: float
    account_equity: float
    price: float = 0.0
    quantity: float = 0.0
    volatility_pct: float = 0.0
    average_daily_volume: float = 0.0
    broker_risk_level: str = "medium"
    existing_symbol_exposure: float = 0.0
    portfolio_notional: float = 0.0
    daily_drawdown_pct: float = 0.0
    strategy_confidence: float = 1.0


@dataclass(frozen=True)
class TradeRiskScore:
    """Explainable per-trade risk score."""

    symbol: str
    score: float
    risk_level: str
    drivers: List[str]
    model_version: str = "sentinel-risk-logistic-v1"
    features: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CircuitBreakerAdjustmentInput:
    """Market-context inputs for adaptive circuit-breaker recommendations."""

    broker_id: str
    volatility_pct: float
    liquidity_score: float = 1.0
    market_stress_score: float = 0.0
    broker_risk_level: str = "medium"


@dataclass(frozen=True)
class CircuitBreakerRecommendation:
    """Recommended broker resilience configuration for current market stress."""

    broker_id: str
    stress_score: float
    config: BrokerResilienceConfig
    reasons: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "broker_id": self.broker_id,
            "stress_score": self.stress_score,
            "config": asdict(self.config),
            "reasons": self.reasons,
        }


@dataclass(frozen=True)
class LiquiditySizingInput:
    """Inputs for liquidity-aware position sizing."""

    symbol: str
    requested_order_value: float
    price: float
    account_equity: float
    average_daily_volume: float
    recent_volume: float = 0.0
    max_participation_rate: float = 0.01
    volatility_pct: float = 0.0
    risk_score: float = 0.0
    recent_volume_weight: float = 0.65


@dataclass(frozen=True)
class LiquiditySizingResult:
    """Position-size recommendation constrained by predicted liquidity."""

    symbol: str
    requested_order_value: float
    recommended_order_value: float
    recommended_shares: float
    predicted_volume: float
    max_liquidity_notional: float
    constraint: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioPosition:
    """Current portfolio holding used in portfolio tail-risk simulation."""

    symbol: str
    quantity: float
    price: float


@dataclass(frozen=True)
class VarCvarInput:
    """Historical-simulation VaR/CVaR request."""

    positions: List[PortfolioPosition]
    historical_returns: Dict[str, List[float]]
    confidence_level: float = 0.95
    limits: AdvancedRiskLimits = field(default_factory=AdvancedRiskLimits)


@dataclass(frozen=True)
class VarCvarResult:
    """Portfolio VaR/CVaR result."""

    is_allowed: bool
    portfolio_value: float
    var_value: float
    cvar_value: float
    var_pct: float
    cvar_pct: float
    confidence_level: float
    message: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AdvancedRiskAssessment:
    """Combined advanced pre-trade result."""

    is_allowed: bool
    restriction: OrderRestriction
    message: str
    trade_score: TradeRiskScore
    liquidity: Optional[LiquiditySizingResult] = None
    var_cvar: Optional[VarCvarResult] = None

    def to_risk_check_result(self) -> RiskCheckResult:
        rejected_fields = {
            "risk_score": self.trade_score.score,
            "risk_level": self.trade_score.risk_level,
        }
        if self.liquidity:
            rejected_fields["recommended_order_value"] = self.liquidity.recommended_order_value
        if self.var_cvar:
            rejected_fields["var_pct"] = self.var_cvar.var_pct
            rejected_fields["cvar_pct"] = self.var_cvar.cvar_pct

        return RiskCheckResult(
            is_allowed=self.is_allowed,
            restriction=self.restriction,
            message=self.message,
            rejected_fields=rejected_fields,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "is_allowed": self.is_allowed,
            "restriction": self.restriction.value,
            "message": self.message,
            "trade_score": self.trade_score.to_dict(),
            "liquidity": self.liquidity.to_dict() if self.liquidity else None,
            "var_cvar": self.var_cvar.to_dict() if self.var_cvar else None,
        }


class AdvancedRiskManager:
    """Explainable advanced risk engine for pre-trade decisions."""

    def score_trade(self, trade: TradeRiskInput) -> TradeRiskScore:
        order_ratio = _safe_ratio(trade.order_value, trade.account_equity)
        quantity = trade.quantity
        if quantity <= 0 and trade.price > 0:
            quantity = trade.order_value / trade.price

        concentration_ratio = _safe_ratio(
            trade.existing_symbol_exposure + trade.order_value,
            trade.account_equity,
        )
        participation_ratio = _safe_ratio(quantity, trade.average_daily_volume)

        features = {
            "order_size": _clamp(order_ratio / 0.25),
            "concentration": _clamp(concentration_ratio / 0.30),
            "volatility": _clamp(trade.volatility_pct / 0.08),
            "liquidity": _clamp(participation_ratio / 0.01),
            "drawdown": _clamp(trade.daily_drawdown_pct / 0.05),
            "broker": _broker_risk_weight(trade.broker_risk_level),
            "confidence": _clamp(1.0 - trade.strategy_confidence),
        }
        weights = {
            "order_size": 0.22,
            "concentration": 0.20,
            "volatility": 0.20,
            "liquidity": 0.15,
            "drawdown": 0.13,
            "broker": 0.07,
            "confidence": 0.03,
        }
        raw_score = sum(features[name] * weights[name] for name in weights) * 100
        score = round(_clamp(raw_score, 0.0, 100.0), 2)

        if score < 35:
            level = "low"
        elif score < 70:
            level = "medium"
        else:
            level = "high"

        drivers = [
            name
            for name, value in sorted(features.items(), key=lambda item: item[1], reverse=True)
            if value >= 0.50
        ][:4]

        return TradeRiskScore(
            symbol=trade.symbol.upper(),
            score=score,
            risk_level=level,
            drivers=drivers,
            features={name: round(value, 4) for name, value in features.items()},
        )

    def recommend_circuit_breaker(
        self,
        base_config: BrokerResilienceConfig,
        context: CircuitBreakerAdjustmentInput,
    ) -> CircuitBreakerRecommendation:
        volatility = _clamp(context.volatility_pct / 0.08)
        liquidity_stress = _clamp(1.0 - context.liquidity_score)
        market_stress = _clamp(context.market_stress_score)
        broker_stress = 0.10 if context.broker_risk_level.lower() == "high" else 0.0
        stress = _clamp(
            (volatility * 0.50)
            + (market_stress * 0.25)
            + (liquidity_stress * 0.15)
            + broker_stress
        )

        rate_multiplier = max(0.20, 1.0 - (0.65 * stress))
        burst_multiplier = max(0.25, 1.0 - (0.55 * stress))
        threshold_multiplier = max(0.35, 1.0 - (0.45 * stress))

        adjusted = BrokerResilienceConfig(
            max_rps=round(max(0.1, base_config.max_rps * rate_multiplier), 2),
            burst=max(1, int(round(base_config.burst * burst_multiplier))),
            cooldown_ms=base_config.cooldown_ms,
            failure_threshold=max(1, int(round(base_config.failure_threshold * threshold_multiplier))),
            failure_window_seconds=base_config.failure_window_seconds,
            recovery_timeout_seconds=max(
                base_config.recovery_timeout_seconds,
                int(round(base_config.recovery_timeout_seconds * (1.0 + 2.0 * stress))),
            ),
            half_open_max_calls=base_config.half_open_max_calls,
            skip_during_opening=base_config.skip_during_opening or stress >= 0.75,
        )

        reasons = []
        if volatility >= 0.50:
            reasons.append("market volatility")
        if market_stress >= 0.50:
            reasons.append("market stress")
        if liquidity_stress >= 0.50:
            reasons.append("thin liquidity")
        if broker_stress:
            reasons.append("high broker restriction risk")

        return CircuitBreakerRecommendation(
            broker_id=context.broker_id,
            stress_score=round(stress, 4),
            config=adjusted,
            reasons=reasons or ["normal market conditions"],
        )

    def recommend_position_size(self, sizing: LiquiditySizingInput) -> LiquiditySizingResult:
        recent_weight = _clamp(sizing.recent_volume_weight)
        baseline_weight = 1.0 - recent_weight
        predicted_volume = (
            sizing.average_daily_volume * baseline_weight
            + sizing.recent_volume * recent_weight
        )
        if predicted_volume <= 0:
            predicted_volume = sizing.average_daily_volume

        max_liquidity_notional = max(
            0.0,
            predicted_volume * _clamp(sizing.max_participation_rate, 0.0, 1.0) * sizing.price,
        )

        risk_haircut = 1.0
        if sizing.risk_score >= 70:
            risk_haircut = 0.50
        elif sizing.risk_score >= 35:
            risk_haircut = 0.75

        volatility_haircut = max(0.30, 1.0 - (sizing.volatility_pct * 3.0))
        account_cap = max(0.0, sizing.account_equity)
        capped_notional = min(sizing.requested_order_value, max_liquidity_notional, account_cap)
        recommended = round(max(0.0, capped_notional * risk_haircut * volatility_haircut), 2)
        shares = round(_safe_ratio(recommended, sizing.price), 6)

        if max_liquidity_notional < sizing.requested_order_value:
            constraint = "liquidity"
        elif account_cap < sizing.requested_order_value:
            constraint = "account_equity"
        elif risk_haircut < 1.0:
            constraint = "risk_score"
        elif volatility_haircut < 1.0:
            constraint = "volatility"
        else:
            constraint = "requested"

        return LiquiditySizingResult(
            symbol=sizing.symbol.upper(),
            requested_order_value=sizing.requested_order_value,
            recommended_order_value=recommended,
            recommended_shares=shares,
            predicted_volume=round(predicted_volume, 6),
            max_liquidity_notional=round(max_liquidity_notional, 2),
            constraint=constraint,
            reason=(
                f"Recommended size uses predicted volume of {predicted_volume:,.0f} shares, "
                f"{sizing.max_participation_rate:.2%} participation, risk haircut {risk_haircut:.0%}, "
                f"and volatility haircut {volatility_haircut:.0%}."
            ),
        )

    def evaluate_var_cvar(self, request: VarCvarInput) -> VarCvarResult:
        portfolio_value = sum(abs(position.quantity * position.price) for position in request.positions)
        if portfolio_value <= 0:
            return VarCvarResult(
                is_allowed=True,
                portfolio_value=0.0,
                var_value=0.0,
                cvar_value=0.0,
                var_pct=0.0,
                cvar_pct=0.0,
                confidence_level=request.confidence_level,
                message="No portfolio exposure to evaluate.",
            )

        usable_lengths = [
            len(request.historical_returns.get(position.symbol.upper(), []))
            for position in request.positions
        ]
        sample_count = min(usable_lengths) if usable_lengths else 0
        if sample_count <= 0:
            return VarCvarResult(
                is_allowed=True,
                portfolio_value=round(portfolio_value, 2),
                var_value=0.0,
                cvar_value=0.0,
                var_pct=0.0,
                cvar_pct=0.0,
                confidence_level=request.confidence_level,
                message="Insufficient return history for VaR/CVaR.",
            )

        pnl_samples = []
        for index in range(sample_count):
            pnl = 0.0
            for position in request.positions:
                returns = request.historical_returns.get(position.symbol.upper(), [])
                pnl += position.quantity * position.price * returns[index]
            pnl_samples.append(pnl)

        pnl_samples.sort()
        tail_count = max(1, ceil(sample_count * (1.0 - _clamp(request.confidence_level))))
        tail_losses = [abs(value) for value in pnl_samples[:tail_count] if value < 0]
        if not tail_losses:
            tail_losses = [0.0]

        var_value = tail_losses[-1]
        cvar_value = sum(tail_losses) / len(tail_losses)
        var_pct = _safe_ratio(var_value, portfolio_value)
        cvar_pct = _safe_ratio(cvar_value, portfolio_value)

        breaches = []
        if var_pct > request.limits.max_var_pct:
            breaches.append(f"VaR {var_pct:.2%} > {request.limits.max_var_pct:.2%}")
        if cvar_pct > request.limits.max_cvar_pct:
            breaches.append(f"CVaR {cvar_pct:.2%} > {request.limits.max_cvar_pct:.2%}")

        is_allowed = not breaches
        message = "Tail-risk limits pass." if is_allowed else "Tail-risk breach: " + "; ".join(breaches)

        return VarCvarResult(
            is_allowed=is_allowed,
            portfolio_value=round(portfolio_value, 2),
            var_value=round(var_value, 2),
            cvar_value=round(cvar_value, 2),
            var_pct=round(var_pct, 6),
            cvar_pct=round(cvar_pct, 6),
            confidence_level=request.confidence_level,
            message=message,
        )

    def assess_trade(
        self,
        trade: TradeRiskInput,
        limits: Optional[AdvancedRiskLimits] = None,
        liquidity: Optional[LiquiditySizingInput] = None,
        var_cvar: Optional[VarCvarInput] = None,
    ) -> AdvancedRiskAssessment:
        limits = limits or AdvancedRiskLimits()
        trade_score = self.score_trade(trade)
        liquidity_result = self.recommend_position_size(liquidity) if liquidity else None
        var_cvar_result = self.evaluate_var_cvar(var_cvar) if var_cvar else None

        messages = []
        allowed = True
        restriction = OrderRestriction.NONE

        if trade_score.score > limits.max_trade_risk_score:
            allowed = False
            restriction = OrderRestriction.NO_NEW_ENTRIES
            messages.append(f"Trade risk score {trade_score.score:.2f} exceeds {limits.max_trade_risk_score:.2f}.")

        if var_cvar_result and not var_cvar_result.is_allowed:
            allowed = False
            restriction = OrderRestriction.HARD_BLOCK
            messages.append(var_cvar_result.message)

        if liquidity_result and liquidity_result.recommended_order_value <= 0:
            allowed = False
            restriction = OrderRestriction.NO_NEW_ENTRIES
            messages.append("Predicted liquidity does not support a new entry.")

        if not messages:
            messages.append("Advanced risk checks pass.")

        return AdvancedRiskAssessment(
            is_allowed=allowed,
            restriction=restriction,
            message=" ".join(messages),
            trade_score=trade_score,
            liquidity=liquidity_result,
            var_cvar=var_cvar_result,
        )


advanced_risk_manager = AdvancedRiskManager()


__all__ = [
    "AdvancedRiskAssessment",
    "AdvancedRiskLimits",
    "AdvancedRiskManager",
    "CircuitBreakerAdjustmentInput",
    "CircuitBreakerRecommendation",
    "LiquiditySizingInput",
    "LiquiditySizingResult",
    "PortfolioPosition",
    "TradeRiskInput",
    "TradeRiskScore",
    "VarCvarInput",
    "VarCvarResult",
    "advanced_risk_manager",
]
