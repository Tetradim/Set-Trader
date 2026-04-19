"""
strategies/custom/multi_indicator.py
Example signal-based strategy showing how to combine multiple indicators.

This strategy demonstrates combining RSI and MACD for entry signals.
Use this as a reference for building your own custom strategies.

To create your own strategy:
  1. Copy this file to strategies/custom/my_strategy.py
  2. Subclass BaseStrategy, define metadata and generate_signals()
  3. The engine hot-reloads the file automatically (or call POST /api/strategies/reload)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from pydantic import Field

from strategies.base import BaseStrategy, Signal, StrategyConfigModel, StrategyMetadata

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter model — each field becomes a form input in ConfigModal
# ---------------------------------------------------------------------------

class MultiIndicatorParams(StrategyConfigModel):
    rsi_period: int      = Field(14,  ge=5,  le=50,  title="RSI Period")
    macd_fast: int       = Field(12,  ge=5,  le=50,  title="MACD Fast Period")
    macd_slow: int       = Field(26,  ge=10, le=100, title="MACD Slow Period")
    macd_signal: int     = Field(9,   ge=3,  le=30,  title="MACD Signal Period")
    rsi_oversold: float  = Field(35.0, ge=10, le=50, title="RSI Oversold Threshold")
    rsi_overbought: float = Field(65.0, ge=50, le=90, title="RSI Overbought Threshold")
    min_confidence: float    = Field(0.70, ge=0.50, le=1.0, title="Min Confidence to Trade")
    min_bars: int            = Field(50, ge=20, le=500, title="Min History Bars Required")


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class MultiIndicatorStrategy(BaseStrategy):

    metadata = StrategyMetadata(
        name="Example: RSI + MACD",
        version="1.0.0",
        description=(
            "Example strategy showing how to combine RSI and MACD. "
            "Use as a template to build your own multi-indicator strategies."
        ),
        author="Signal Forge Lab",
        tags=["momentum", "mean-reversion", "example"],
        risk_level="MEDIUM",
        requires_history_bars=50,
        supported_markets=["US", "HK", "AU", "UK", "CA", "CN_SS", "CN_SZ"],
    )

    params_model   = MultiIndicatorParams
    default_params = MultiIndicatorParams().model_dump()

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
            logger.debug(
                f"[{ticker_doc['symbol']}] MultiIndicator: insufficient history "
                f"({0 if df is None else len(df)} bars, need {params['min_bars']})"
            )
            return None  # fall through to bracket logic

        close = df["close"]

        # --- RSI ---
        try:
            from ta.momentum import RSIIndicator
            rsi_val = RSIIndicator(close=close, window=params["rsi_period"]).rsi().iloc[-1]
        except Exception:
            return None

        # --- MACD ---
        try:
            from ta.trend import MACD
            macd_obj  = MACD(
                close=close,
                window_fast=params["macd_fast"],
                window_slow=params["macd_slow"],
                window_sign=params["macd_signal"],
            )
            macd_diff_now  = macd_obj.macd_diff().iloc[-1]   # positive = bull crossover
            macd_diff_prev = macd_obj.macd_diff().iloc[-2]
        except Exception:
            return None

        logger.debug(
            f"[{ticker_doc['symbol']}] RSI={rsi_val:.1f} MACD_diff={macd_diff_now:.4f}"
        )

        # --- BUY signal: RSI oversold + MACD crossing up ---
        if (
            rsi_val < params["rsi_oversold"]
            and macd_diff_now > 0
            and macd_diff_prev <= 0        # fresh crossover
        ):
            confidence = min(
                0.50 + (params["rsi_oversold"] - rsi_val) / 100,
                0.98,
            )
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="BUY",
                    confidence=round(confidence, 3),
                    reason=f"RSI {rsi_val:.1f} oversold + bullish MACD crossover",
                )

        # --- SELL signal: RSI overbought + MACD crossing down ---
        if (
            rsi_val > params["rsi_overbought"]
            and macd_diff_now < 0
            and macd_diff_prev >= 0        # fresh crossover
        ):
            confidence = min(
                0.50 + (rsi_val - params["rsi_overbought"]) / 100,
                0.95,
            )
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="SELL",
                    confidence=round(confidence, 3),
                    reason=f"RSI {rsi_val:.1f} overbought + bearish MACD crossover",
                )

        return None   # no signal — engine will apply bracket rules
