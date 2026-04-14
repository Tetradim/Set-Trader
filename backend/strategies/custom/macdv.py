"""
strategies/custom/macdv.py
MACD-V (Volume-weighted MACD) strategy based on StockCharts.com formula.

MACD-V = [(12-period EMA - 26-period EMA) / ATR(26)] * 100
Signal Line = 9-period EMA of MACD-V

Trading interpretation (from StockCharts ChartSchool):
- Risk (Oversold): MACD-V < -150
- Rebounding: -150 < MACD-V < 50, above signal line
- Rallying: 50 < MACD-V < 150, above signal line
- Risk (Overbought): MACD-V > 150, above signal line
- Retracing: MACD-V > -50, below signal line
- Reversing: -150 < MACD-V < -50, below signal line

References:
- https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/macd-v
- https://www.barchart.com/education/technical-indicators/macdv_oscillator
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from pydantic import Field

from strategies.base import BaseStrategy, Signal, StrategyConfigModel, StrategyMetadata

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parameter model
# ---------------------------------------------------------------------------

class MACDVParams(StrategyConfigModel):
    # MACD periods
    macd_fast: int = Field(12, ge=5, le=50, title="MACD Fast EMA Period")
    macd_slow: int = Field(26, ge=10, le=100, title="MACD Slow EMA Period")
    macd_signal: int = Field(9, ge=3, le=30, title="Signal Line EMA Period")
    
    # ATR period for normalization
    atr_period: int = Field(26, ge=5, le=50, title="ATR Period for Normalization")
    
    # Thresholds (from StockCharts)
    oversold_threshold: float = Field(-150.0, ge=-300, le=0, title="Oversold Threshold")
    rebounding_threshold: float = Field(50.0, ge=-100, le=100, title="Rebounding Threshold")
    rallying_threshold: float = Field(150.0, ge=50, le=300, title="Rallying Threshold")
    overbought_threshold: float = Field(150.0, ge=50, le=500, title="Overbought Threshold")
    
    # Signal confirmation
    min_confidence: float = Field(0.65, ge=0.50, le=1.0, title="Min Confidence to Trade")
    min_bars: int = Field(60, ge=30, le=500, title="Min History Bars Required")
    
    # Enable/disable signal modes
    enable_reversals: bool = Field(True, title="Enable Reversal Signals")
    enable_retraces: bool = Field(True, title="Enable Retracement Signals")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def calc_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range."""
    high = df.get("high", df.get("Close"))
    low = df.get("low", df.get("Close"))
    close = df.get("close", df.get("Close"))
    
    if high is None or low is None:
        # Fallback: use close as proxy
        high = close
        low = close
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    
    return atr


def calc_macdv(
    df: pd.DataFrame,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
    atr_period: int = 26,
) -> pd.DataFrame:
    """
    Calculate MACD-V oscillator.
    
    Returns DataFrame with:
    - macd: MACD line (fast EMA - slow EMA)
    - macdv: MACD-V normalized by ATR
    - signal: Signal line (EMA of MACD-V)
    - histogram: MACD-V - Signal
    """
    close = df.get("close", df.get("Close"))
    
    if close is None:
        return pd.DataFrame()
    
    # Calculate EMAs
    ema_fast = calc_ema(close, fast_period)
    ema_slow = calc_ema(close, slow_period)
    
    # MACD line
    macd = ema_fast - ema_slow
    
    # Calculate ATR
    atr = calc_atr(df, atr_period)
    
    # Avoid division by zero
    atr = atr.replace(0, np.nan)
    
    # MACD-V = [(MACD / ATR) * 100]
    macdv = (macd / atr) * 100
    
    # Signal line
    signal = calc_ema(macdv, signal_period)
    
    # Histogram
    histogram = macdv - signal
    
    return pd.DataFrame({
        "macd": macd,
        "macdv": macdv,
        "signal": signal,
        "histogram": histogram,
    })


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class MACDVStrategy(BaseStrategy):

    metadata = StrategyMetadata(
        name="MACD-V (Volume-Weighted MACD)",
        version="1.0.0",
        description=(
            "MACD-V normalizes MACD by ATR to create universal momentum readings "
            "that work consistently across all price levels. Based on StockCharts.com formula. "
            "Uses overbought/oversold thresholds and signal line crossovers for entry/exit."
        ),
        author="Signal Forge Lab",
        tags=["momentum", "macd", "atr-normalized", "mean-reversion"],
        risk_level="MEDIUM",
        requires_history_bars=60,
        supported_markets=["US", "HK", "AU", "UK", "CA", "CN_SS", "CN_SZ"],
    )

    params_model = MACDVParams
    default_params = MACDVParams().model_dump()

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
                f"[{ticker_doc['symbol']}] MACD-V: insufficient history "
                f"({0 if df is None else len(df)} bars, need {params['min_bars']})"
            )
            return None

        # Calculate MACD-V
        macd_data = calc_macdv(
            df,
            fast_period=params["macd_fast"],
            slow_period=params["macd_slow"],
            signal_period=params["macd_signal"],
            atr_period=params["atr_period"],
        )
        
        if macd_data.empty:
            return None
        
        # Get current and previous values
        macdv = macd_data["macdv"].iloc[-1]
        prev_macdv = macd_data["macdv"].iloc[-2]
        signal = macd_data["signal"].iloc[-1]
        prev_signal = macd_data["signal"].iloc[-2]
        histogram = macd_data["histogram"].iloc[-1]
        
        # Check for valid values
        if pd.isna(macdv) or pd.isna(signal):
            logger.debug(f"[{ticker_doc['symbol']}] MACD-V: NaN values detected")
            return None
        
        # Determine market state (from StockCharts)
        above_signal = macdv > signal
        action = None
        confidence = 0.0
        reason = ""
        
        # === SELL / REVERSAL / RETRACE CONDITIONS ===
        if above_signal:
            # Above signal line - bullish territory
            if macdv < params["oversold_threshold"]:
                # Oversold (rare in bullish territory)
                action = "BUY"
                confidence = 0.75
                reason = f"MACD-V oversold ({macdv:.1f}), bullish divergence possible"
                
            elif macdv < params["rebounding_threshold"]:
                # Rebounding: -150 < MACD-V < 50
                if prev_macdv < signal and macdv > signal:
                    # Signal line crossover
                    action = "BUY"
                    confidence = params["min_confidence"] * 1.2
                    reason = f"MACD-V rebounding ({macdv:.1f}), signal line crossover"
                else:
                    action = "HOLD"
                    confidence = 0.5
                    reason = f"MACD-V rebounding ({macdv:.1f}), waiting for confirmation"
                    
            elif macdv < params["rallying_threshold"]:
                # Rallying: 50 < MACD-V < 150
                action = "HOLD"
                confidence = 0.6
                reason = f"MACD-V rallying ({macdv:.1f}), strong momentum"
                
            else:
                # Overbought: MACD-V > 150
                if params.get("enable_reversals", True):
                    action = "SELL"
                    confidence = 0.80
                    reason = f"MACD-V overbought ({macdv:.1f}), reversal likely"
                else:
                    action = "HOLD"
                    confidence = 0.5
                    reason = f"MACD-V overbought ({macdv:.1f}), but reversals disabled"
        else:
            # Below signal line - bearish territory
            if macdv > -50:
                # Retracing: MACD-V > -50
                if params.get("enable_retraces", True):
                    action = "SELL"
                    confidence = params["min_confidence"] * 1.1
                    reason = f"MACD-V retracing ({macdv:.1f}), taking profits"
                else:
                    action = "HOLD"
                    confidence = 0.5
                    reason = f"MACD-V retracing ({macdv:.1f}), but retraces disabled"
                    
            elif macdv > -params["overbought_threshold"]:
                # Reversing: -150 < MACD-V < -50
                if params.get("enable_reversals", True):
                    action = "SELL"
                    confidence = 0.75
                    reason = f"MACD-V reversing ({macdv:.1f}), bearish momentum"
                else:
                    action = "HOLD"
                    confidence = 0.5
                    reason = f"MACD-V reversing ({macdv:.1f}), waiting"
                    
            else:
                # Strong reversal: MACD-V < -150
                if params.get("enable_reversals", True):
                    action = "BUY"
                    confidence = 0.70
                    reason = f"MACD-V deeply oversold ({macdv:.1f}), potential reversal"
                else:
                    action = "HOLD"
                    confidence = 0.4
                    reason = f"MACD-V extreme oversold ({macdv:.1f})"
        
        # Clamp confidence
        confidence = min(1.0, confidence)
        
        # Metadata for debugging/trading
        metadata = {
            "macdv": round(macdv, 2),
            "signal": round(signal, 2),
            "histogram": round(histogram, 2),
            "crossover": "bullish" if (prev_macdv < prev_signal and macdv > signal) else "bearish" if (prev_macdv > prev_signal and macdv < signal) else "none",
            "market_state": self._get_market_state(macdv, above_signal, params),
        }
        
        logger.info(
            f"[{ticker_doc['symbol']}] MACD-V: {action} | "
            f"MACD-V={macdv:.1f} signal={signal:.1f} | "
            f"conf={confidence:.2f} | {reason}"
        )
        
        return Signal(
            action=action or "HOLD",
            confidence=confidence,
            reason=reason,
            metadata=metadata,
        )

    def _get_market_state(self, macdv: float, above_signal: bool, params: Dict) -> str:
        """Determine market state based on StockCharts interpretation."""
        if above_signal:
            if macdv < params["oversold_threshold"]:
                return "oversold"
            elif macdv < params["rebounding_threshold"]:
                return "rebounding"
            elif macdv < params["rallying_threshold"]:
                return "rallying"
            else:
                return "overbought"
        else:
            if macdv > -50:
                return "retracing"
            elif macdv > -params["overbought_threshold"]:
                return "reversing"
            else:
                return "strong_reversal"