"""
strategies/custom/multi_indicator.py
Example signal-based strategy using RSI + MACD + Volume confirmation.
Drop-in ready — uses `ta` (pure Python TA, no C build required).

To add your own strategy:
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
    volume_multiplier: float = Field(1.5, ge=1.0, le=5.0, title="Volume Surge Multiplier")
    min_confidence: float    = Field(0.70, ge=0.50, le=1.0, title="Min Confidence to Trade")
    min_bars: int            = Field(50, ge=20, le=500, title="Min History Bars Required")


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class MultiIndicatorStrategy(BaseStrategy):

    metadata = StrategyMetadata(
        name="Multi-Indicator (RSI + MACD + Volume)",
        version="1.0.0",
        description=(
            "RSI oversold/overbought signals confirmed by MACD crossover and "
            "volume surge. Works across all supported markets."
        ),
        author="Signal Forge Lab",
        tags=["momentum", "mean-reversion", "volume", "multi-timeframe"],
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

        close  = df["close"]
        volume = df.get("volume")

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

        # --- Volume surge ---
        volume_ratio = 1.0
        if volume is not None and len(volume) >= 20:
            vol_sma = volume.rolling(20).mean().iloc[-1]
            if vol_sma and vol_sma > 0:
                volume_ratio = float(volume.iloc[-1]) / float(vol_sma)

        logger.debug(
            f"[{ticker_doc['symbol']}] RSI={rsi_val:.1f} "
            f"MACD_diff={macd_diff_now:.4f} vol_ratio={volume_ratio:.2f}"
        )

        # --- BUY signal: RSI oversold + MACD crossing up + volume surge ---
        if (
            rsi_val < params["rsi_oversold"]
            and macd_diff_now > 0
            and macd_diff_prev <= 0        # fresh crossover
            and volume_ratio >= params["volume_multiplier"]
        ):
            confidence = min(
                0.50
                + (params["rsi_oversold"] - rsi_val) / 100
                + min(volume_ratio - 1.0, 0.3),
                0.98,
            )
            if confidence >= params["min_confidence"]:
                return Signal(
                    action="BUY",
                    confidence=round(confidence, 3),
                    reason=(
                        f"RSI {rsi_val:.1f} oversold + bullish MACD crossover "
                        f"+ volume {volume_ratio:.1f}x surge"
                    ),
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
