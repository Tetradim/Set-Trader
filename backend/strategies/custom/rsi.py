"""
strategies/custom/rsi.py
RSI (Relative Strength Index) mean reversion strategy.

Buy when RSI enters oversold territory.
Sell when RSI enters overbought territory.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd
from pydantic import Field

from strategies.base import BaseStrategy, Signal, StrategyConfigModel, StrategyMetadata

logger = logging.getLogger(__name__)


class RSIParams(StrategyConfigModel):
    rsi_period: int = Field(14, ge=5, le=50, title="RSI Period")
    rsi_oversold: float = Field(30.0, ge=10, le=50, title="Oversold Threshold")
    rsi_overbought: float = Field(70.0, ge=50, le=90, title="Overbought Threshold")
    min_confidence: float = Field(0.70, ge=0.50, le=1.0, title="Min Confidence")
    min_bars: int = Field(30, ge=20, le=500, title="Min History Bars")


class RSIStrategy(BaseStrategy):

    metadata = StrategyMetadata(
        name="RSI",
        version="1.0.0",
        description="Buy when RSI enters oversold, sell when entering overbought.",
        author="Signal Forge Lab",
        tags=["mean-reversion", "rsi", "oversold"],
        risk_level="MEDIUM",
        requires_history_bars=30,
        supported_markets=["US", "HK", "AU", "UK", "CA", "CN_SS", "CN_SZ"],
    )

    params_model = RSIParams
    default_params = RSIParams().model_dump()

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
            from ta.momentum import RSIIndicator
            rsi = RSIIndicator(close=close, window=params["rsi_period"]).rsi()
            rsi_val = rsi.iloc[-1]
            rsi_prev = rsi.iloc[-2]
        except Exception as e:
            logger.debug(f"[{ticker_doc['symbol']}] RSI error: {e}")
            return None

        if pd.isna(rsi_val):
            return None

        logger.debug(f"[{ticker_doc['symbol']}] RSI: {rsi_val:.1f}")

        # Entering oversold (was above, now below)
        if rsi_prev >= params["rsi_oversold"] and rsi_val < params["rsi_oversold"]:
            # Calculate confidence based on how deep into oversold
            depth = params["rsi_oversold"] - rsi_val
            confidence = min(0.70 + depth / 50, 0.95)
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="BUY",
                    confidence=round(confidence, 3),
                    reason=f"RSI entering oversold ({rsi_val:.1f})",
                )

        # Entering overbought (was below, now above)
        if rsi_prev <= params["rsi_overbought"] and rsi_val > params["rsi_overbought"]:
            depth = rsi_val - params["rsi_overbought"]
            confidence = min(0.70 + depth / 50, 0.95)
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="SELL",
                    confidence=round(confidence, 3),
                    reason=f"RSI entering overbought ({rsi_val:.1f})",
                )

        return None