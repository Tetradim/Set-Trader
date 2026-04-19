"""
strategies/custom/bollinger.py
Bollinger Bands mean reversion strategy.

Buy when price touches lower band (oversold).
Sell when price touches upper band (overbought).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd
from pydantic import Field

from strategies.base import BaseStrategy, Signal, StrategyConfigModel, StrategyMetadata

logger = logging.getLogger(__name__)


class BollingerParams(StrategyConfigModel):
    bb_period: int = Field(20, ge=5, le=50, title="BB Period")
    bb_std: float = Field(2.0, ge=1.0, le=4.0, title="Standard Deviations")
    min_confidence: float = Field(0.70, ge=0.50, le=1.0, title="Min Confidence")
    min_bars: int = Field(30, ge=20, le=500, title="Min History Bars")


class BollingerStrategy(BaseStrategy):

    metadata = StrategyMetadata(
        name="Bollinger Bands",
        version="1.0.0",
        description="Buy at lower band, sell at upper band. Mean reversion.",
        author="Signal Forge Lab",
        tags=["volatility", "mean-reversion", "bollinger"],
        risk_level="MEDIUM",
        requires_history_bars=30,
        supported_markets=["US", "HK", "AU", "UK", "CA", "CN_SS", "CN_SZ"],
    )

    params_model = BollingerParams
    default_params = BollingerParams().model_dump()

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
        high = df.get("high", close)
        low = df.get("low", close)

        try:
            from ta.volatility import BollingerBands
            bb = BollingerBands(
                close=close,
                window=params["bb_period"],
                window_dev=params["bb_std"],
            )
            
            lower = bb.bollinger_lband().iloc[-1]
            middle = bb.bollinger_mavg().iloc[-1]
            upper = bb.bollinger_hband().iloc[-1]
            
            lower_prev = bb.bollinger_lband().iloc[-2]
            upper_prev = bb.bollinger_hband().iloc[-2]
            
        except Exception as e:
            logger.debug(f"[{ticker_doc['symbol']}] Bollinger error: {e}")
            return None

        if pd.isna(lower) or pd.isna(upper):
            return None

        logger.debug(
            f"[{ticker_doc['symbol']}] BB: Lower={lower:.2f} Mid={middle:.2f} Upper={upper:.2f}"
        )

        # Price touches or crosses below lower band - BUY
        if current_price <= lower or (low.iloc[-1] if hasattr(low, 'iloc') else low) <= lower:
            # Calculate how far below the band
            band_distance = (lower - current_price) / lower
            confidence = min(0.70 + band_distance * 5, 0.95)
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="BUY",
                    confidence=round(confidence, 3),
                    reason=f"Price at lower Bollinger band ({current_price:.2f} <= {lower:.2f})",
                )

        # Price touches or crosses above upper band - SELL
        if current_price >= upper or (high.iloc[-1] if hasattr(high, 'iloc') else high) >= upper:
            band_distance = (current_price - upper) / upper
            confidence = min(0.70 + band_distance * 5, 0.95)
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="SELL",
                    confidence=round(confidence, 3),
                    reason=f"Price at upper Bollinger band ({current_price:.2f} >= {upper:.2f})",
                )

        return None