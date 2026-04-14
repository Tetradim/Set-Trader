"""
strategies/custom/macd.py
MACD (Moving Average Convergence Divergence) strategy.

Buy when MACD line crosses above signal line (bullish).
Sell when MACD line crosses below signal line (bearish).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd
from pydantic import Field

from strategies.base import BaseStrategy, Signal, StrategyConfigModel, StrategyMetadata

logger = logging.getLogger(__name__)


class MACDParams(StrategyConfigModel):
    macd_fast: int = Field(12, ge=5, le=50, title="Fast EMA Period")
    macd_slow: int = Field(26, ge=10, le=100, title="Slow EMA Period")
    macd_signal: int = Field(9, ge=3, le=30, title="Signal Line Period")
    min_confidence: float = Field(0.70, ge=0.50, le=1.0, title="Min Confidence")
    min_bars: int = Field(40, ge=20, le=500, title="Min History Bars")


class MACDStrategy(BaseStrategy):

    metadata = StrategyMetadata(
        name="MACD",
        version="1.0.0",
        description="Buy on bullish MACD crossover, sell on bearish crossover.",
        author="Signal Forge Lab",
        tags=["momentum", "trend", "macd"],
        risk_level="MEDIUM",
        requires_history_bars=40,
        supported_markets=["US", "HK", "AU", "UK", "CA", "CN_SS", "CN_SZ"],
    )

    params_model = MACDParams
    default_params = MACDParams().model_dump()

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
            from ta.trend import MACD
            macd = MACD(
                close=close,
                window_fast=params["macd_fast"],
                window_slow=params["macd_slow"],
                window_sign=params["macd_signal"],
            )
            
            macd_line = macd.macd().iloc[-1]
            signal_line = macd.macd_signal().iloc[-1]
            macd_hist = macd.macd_diff().iloc[-1]
            
            macd_line_prev = macd.macd().iloc[-2]
            signal_line_prev = macd.macd_signal().iloc[-2]
            
        except Exception as e:
            logger.debug(f"[{ticker_doc['symbol']}] MACD error: {e}")
            return None

        if pd.isna(macd_line) or pd.isna(signal_line):
            return None

        logger.debug(
            f"[{ticker_doc['symbol']}] MACD: {macd_line:.4f} Signal: {signal_line:.4f}"
        )

        # Bullish crossover: MACD crosses above signal line
        if macd_line > signal_line and macd_line_prev <= signal_line_prev:
            confidence = min(0.75 + min(macd_hist / 10, 0.2), 0.95)
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="BUY",
                    confidence=round(confidence, 3),
                    reason=f"MACD bullish crossover (MACD={macd_line:.2f}, signal={signal_line:.2f})",
                )

        # Bearish crossover: MACD crosses below signal line
        if macd_line < signal_line and macd_line_prev >= signal_line_prev:
            confidence = min(0.75 + min(abs(macd_hist) / 10, 0.2), 0.95)
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="SELL",
                    confidence=round(confidence, 3),
                    reason=f"MACD bearish crossover (MACD={macd_line:.2f}, signal={signal_line:.2f})",
                )

        return None