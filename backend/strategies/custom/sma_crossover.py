"""
strategies/custom/sma_crossover.py
SMA (Simple Moving Average) Crossover strategy.

Buy when fast SMA crosses above slow SMA (golden cross).
Sell when fast SMA crosses below slow SMA (death cross).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd
from pydantic import Field

from strategies.base import BaseStrategy, Signal, StrategyConfigModel, StrategyMetadata

logger = logging.getLogger(__name__)


class SMACrossoverParams(StrategyConfigModel):
    fast_period: int = Field(10, ge=3, le=50, title="Fast SMA Period")
    slow_period: int = Field(50, ge=10, le=200, title="Slow SMA Period")
    min_confidence: float = Field(0.70, ge=0.50, le=1.0, title="Min Confidence")
    min_bars: int = Field(60, ge=30, le=500, title="Min History Bars")


class SMACrossoverStrategy(BaseStrategy):

    metadata = StrategyMetadata(
        name="SMA Crossover",
        version="1.0.0",
        description="Buy when fast SMA crosses above slow SMA, sell on death cross.",
        author="Signal Forge Lab",
        tags=["trend", "sma", "crossover"],
        risk_level="MEDIUM",
        requires_history_bars=60,
        supported_markets=["US", "HK", "AU", "UK", "CA", "CN_SS", "CN_SZ"],
    )

    params_model = SMACrossoverParams
    default_params = SMACrossoverParams().model_dump()

    async def generate_signals(
        self,
        ticker_doc: dict,
        current_price: float,
        market_data: Dict[str, Any],
        market_status: Dict[str, Any],
        broker_allocations: Dict[str, float],
        params: Dict[str, Any],
    ) -> Optional[Signal]:

        df = market_data.get("history")
        if df is None or len(df) < params["min_bars"]:
            return None

        close = df["close"]

        try:
            fast_sma = close.rolling(params["fast_period"]).mean()
            slow_sma = close.rolling(params["slow_period"]).mean()
            
            fast_now = fast_sma.iloc[-1]
            fast_prev = fast_sma.iloc[-2]
            slow_now = slow_sma.iloc[-1]
            slow_prev = slow_sma.iloc[-2]
            
        except Exception as e:
            logger.debug(f"[{ticker_doc['symbol']}] SMA error: {e}")
            return None

        if pd.isna(fast_now) or pd.isna(slow_now):
            return None

        logger.debug(
            f"[{ticker_doc['symbol']}] SMA: Fast={fast_now:.2f} Slow={slow_now:.2f}"
        )

        # Golden cross: fast SMA crosses above slow SMA
        if fast_now > slow_now and fast_prev <= slow_prev:
            # Calculate strength based on how far fast is above slow
            strength = (fast_now - slow_now) / slow_now
            confidence = min(0.75 + strength * 10, 0.95)
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="BUY",
                    confidence=round(confidence, 3),
                    reason=f"Golden cross: SMA{params['fast_period']} crossed above SMA{params['slow_period']}",
                )

        # Death cross: fast SMA crosses below slow SMA
        if fast_now < slow_now and fast_prev >= slow_prev:
            strength = (slow_now - fast_now) / slow_now
            confidence = min(0.75 + strength * 10, 0.95)
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="SELL",
                    confidence=round(confidence, 3),
                    reason=f"Death cross: SMA{params['fast_period']} crossed below SMA{params['slow_period']}",
                )

        return None