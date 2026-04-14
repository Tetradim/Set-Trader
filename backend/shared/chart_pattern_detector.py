"""
Chart pattern detector using pandas + scipy + TA-Lib.

Detects multi-candle patterns like double_top, double_bottom, head_shoulders, etc.
Uses TA-Lib for single-candle patterns when available, falls back to custom detection.
Designed for Pulse to send observations back to Edge via WebSocket.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# Check for TA-Lib availability
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    logger.info("TA-Lib not available, using custom pattern detection")


# Pattern detection parameters
_LOOKBACK = 60  # bars to look back
_VOLUME_CONFIRMATION = 1.5  # volume must be this many times avg for pattern


def detect_candlestick_patterns_ta(df: pd.DataFrame) -> Dict[str, Any]:
    """Detect single-candle patterns using TA-Lib.
    
    Returns dict of pattern -> confidence (0-100, |value| >= 80 is strong)
    """
    if not TALIB_AVAILABLE or df is None or len(df) < 3:
        return {}
    
    try:
        # Get all pattern recognition functions
        pattern_funcs = talib.get_function_groups().get('Pattern Recognition', [])
        
        patterns = {}
        for func_name in pattern_funcs:
            func = getattr(talib, func_name, None)
            if func is None:
                continue
            
            try:
                result = func(
                    df['Open'].values,
                    df['High'].values,
                    df['Low'].values,
                    df['Close'].values
                )
                # TA-Lib returns: 0 = no pattern, +100/-100 = strong bullish/bearish
                if result[-1] != 0:  # Most recent candle has a pattern
                    patterns[func_name.lower()] = {
                        "value": float(result[-1]),
                        "confidence": min(1.0, abs(result[-1]) / 100),
                        "direction": "bullish" if result[-1] > 0 else "bearish",
                    }
            except Exception:
                continue
        
        return patterns
    except Exception as e:
        logger.debug(f"TA-Lib pattern detection error: {e}")
        return {}


def find_local_extrema(series: pd.Series, order: int = 5) -> Tuple[list, list]:
    """Find local minima and maxima using rolling window."""
    roll_min = series.rolling(order, center=True).min()
    roll_max = series.rolling(order, center=True).max()
    
    min_indices = series[series == roll_min].index.tolist()
    max_indices = series[series == roll_max].index.tolist()
    
    return min_indices, max_indices


def find_peaks_scipy(series: pd.Series, distance: int = 10, prominence: float = None) -> Tuple[list, list]:
    """Find peaks using scipy.signal.find_peaks."""
    try:
        from scipy.signal import find_peaks
        
        kwargs = {"distance": distance}
        if prominence is not None:
            kwargs["prominence"] = prominence
            
        values = series.values
        peaks, _ = find_peaks(values, **kwargs)
        troughs, _ = find_peaks(-values, **kwargs)
        
        return troughs.tolist(), peaks.tolist()
    except ImportError:
        return find_local_extrema(series, order=distance)


def detect_double_bottom(df: pd.DataFrame, tolerance: float = 0.02) -> Optional[Dict[str, Any]]:
    """Detect double bottom pattern (W-shape).
    
    Args:
        df: DataFrame with 'close', 'low', 'volume' columns
        tolerance: Price tolerance for bottoms (2% default)
    
    Returns:
        Dict with pattern info or None
    """
    if len(df) < _LOOKBACK:
        return None
    
    recent = df.tail(_LOOKBACK)
    closes = recent["close"]
    lows = recent.get("low", closes)
    volumes = recent.get("volume", pd.Series([1]*len(recent)))
    
    # Find local minima
    try:
        from scipy.signal import find_peaks
        troughs_idx, _ = find_peaks(-lows.values, distance=10, prominence=lows.std()*0.5)
    except ImportError:
        roll_min = lows.rolling(10, center=True).min()
        troughs_idx = lows[lows == roll_min].index.tolist()
        troughs_idx = [i for i in troughs_idx if isinstance(i, int)]
    
    if len(troughs_idx) < 2:
        return None
    
    # Find two comparable bottoms
    for i in range(len(troughs_idx) - 1):
        for j in range(i + 1, len(troughs_idx)):
            idx1, idx2 = troughs_idx[i], troughs_idx[j]
            price1, price2 = lows.iloc[idx1], lows.iloc[idx2]
            
            # Check if bottoms are within tolerance
            if abs(price1 - price2) / price1 < tolerance:
                # Check for W-shape (second bottom shouldn't be much deeper)
                if price2 >= price1 * 0.98:
                    # Check volume confirmation on bounce
                    vol_avg = volumes.mean()
                    bounce_volume = volumes.iloc[idx2:min(idx2+5, len(volumes))].mean()
                    
                    return {
                        "pattern": "double_bottom",
                        "confidence": min(0.95, 0.70 + (bounce_volume / vol_avg) * 0.25),
                        "levels": {
                            "bottom1": float(price1),
                            "bottom2": float(price2),
                            "middle_peak": float(closes.iloc[idx1:idx2].max()),
                        },
                    }
    
    return None


def detect_double_top(df: pd.DataFrame, tolerance: float = 0.02) -> Optional[Dict[str, Any]]:
    """Detect double top pattern (M-shape)."""
    if len(df) < _LOOKBACK:
        return None
    
    recent = df.tail(_LOOKBACK)
    closes = recent["close"]
    highs = recent.get("high", closes)
    volumes = recent.get("volume", pd.Series([1]*len(recent)))
    
    try:
        from scipy.signal import find_peaks
        peaks_idx, _ = find_peaks(highs.values, distance=10, prominence=highs.std()*0.5)
    except ImportError:
        roll_max = highs.rolling(10, center=True).max()
        peaks_idx = highs[highs == roll_max].index.tolist()
        peaks_idx = [i for i in peaks_idx if isinstance(i, int)]
    
    if len(peaks_idx) < 2:
        return None
    
    for i in range(len(peaks_idx) - 1):
        for j in range(i + 1, len(peaks_idx)):
            idx1, idx2 = peaks_idx[i], peaks_idx[j]
            price1, price2 = highs.iloc[idx1], highs.iloc[idx2]
            
            if abs(price1 - price2) / price1 < tolerance:
                if price1 <= price2 * 1.02:
                    vol_avg = volumes.mean()
                    drop_volume = volumes.iloc[idx2:min(idx2+5, len(volumes))].mean()
                    
                    return {
                        "pattern": "double_top",
                        "confidence": min(0.95, 0.70 + (drop_volume / vol_avg) * 0.25),
                        "levels": {
                            "top1": float(price1),
                            "top2": float(price2),
                            "middle_trough": float(closes.iloc[idx1:idx2].min()),
                        },
                    }
    
    return None


def detect_head_shoulders(df: pd.DataFrame, tolerance: float = 0.03) -> Optional[Dict[str, Any]]:
    """Detect head and shoulders pattern."""
    if len(df) < _LOOKBACK:
        return None
    
    recent = df.tail(_LOOKBACK)
    closes = recent["close"]
    highs = recent.get("high", closes)
    
    try:
        from scipy.signal import find_peaks
        peaks_idx, _ = find_peaks(highs.values, distance=8, prominence=highs.std()*0.3)
    except ImportError:
        roll_max = highs.rolling(8, center=True).max()
        peaks_idx = highs[highs == roll_max].index.tolist()
        peaks_idx = [i for i in peaks_idx if isinstance(i, int)]
    
    if len(peaks_idx) < 3:
        return None
    
    # Look for H&S pattern in last 3 peaks
    for i in range(len(peaks_idx) - 2):
        idx_l, idx_h, idx_r = peaks_idx[i], peaks_idx[i+1], peaks_idx[i+2]
        
        left_shoulder = highs.iloc[idx_l]
        head = highs.iloc[idx_h]
        right_shoulder = highs.iloc[idx_r]
        
        # Head should be higher than shoulders
        if head > left_shoulder and head > right_shoulder:
            # Shoulders should be roughly equal
            if abs(left_shoulder - right_shoulder) / left_shoulder < tolerance:
                return {
                    "pattern": "head_shoulders",
                    "confidence": min(0.90, 0.65 + abs(head - left_shoulder) / head * 0.25),
                    "levels": {
                        "left_shoulder": float(left_shoulder),
                        "head": float(head),
                        "right_shoulder": float(right_shoulder),
                    },
                }
    
    return None


def detect_inverse_head_shoulders(df: pd.DataFrame, tolerance: float = 0.03) -> Optional[Dict[str, Any]]:
    """Detect inverse head and shoulders (bullish)."""
    if len(df) < _LOOKBACK:
        return None
    
    recent = df.tail(_LOOKBACK)
    lows = recent.get("low", recent["close"])
    
    try:
        from scipy.signal import find_peaks
        troughs_idx, _ = find_peaks(-lows.values, distance=8, prominence=lows.std()*0.3)
    except ImportError:
        roll_min = lows.rolling(8, center=True).min()
        troughs_idx = lows[lows == roll_min].index.tolist()
        troughs_idx = [i for i in troughs_idx if isinstance(i, int)]
    
    if len(troughs_idx) < 3:
        return None
    
    for i in range(len(troughs_idx) - 2):
        idx_l, idx_h, idx_r = troughs_idx[i], troughs_idx[i+1], troughs_idx[i+2]
        
        left_shoulder = lows.iloc[idx_l]
        head = lows.iloc[idx_h]
        right_shoulder = lows.iloc[idx_r]
        
        if head < left_shoulder and head < right_shoulder:
            if abs(left_shoulder - right_shoulder) / left_shoulder < tolerance:
                return {
                    "pattern": "head_shoulders_inverse",
                    "confidence": min(0.90, 0.65 + abs(left_shoulder - head) / left_shoulder * 0.25),
                    "levels": {
                        "left_shoulder": float(left_shoulder),
                        "head": float(head),
                        "right_shoulder": float(right_shoulder),
                    },
                }
    
    return None


def detect_triangle(df: pd.DataFrame, lookback: int = 30) -> Optional[Dict[str, Any]]:
    """Detect ascending or descending triangle."""
    if len(df) < lookback:
        return None
    
    recent = df.tail(lookback)
    highs = recent.get("high", recent["close"])
    lows = recent.get("low", recent["close"])
    
    # Linear regression for trend
    x = np.arange(len(highs))
    
    high_slope = np.polyfit(x, highs.values, 1)[0]
    low_slope = np.polyfit(x, lows.values, 1)[0]
    
    # Ascending triangle: flat resistance, rising support
    if abs(high_slope) < 0.1 and low_slope > 0.1:
        return {"pattern": "ascending_triangle", "confidence": 0.75}
    
    # Descending triangle: flat support, falling resistance
    if abs(low_slope) < 0.1 and high_slope < -0.1:
        return {"pattern": "descending_triangle", "confidence": 0.75}
    
    return None


def detect_wedge(df: pd.DataFrame, lookback: int = 30) -> Optional[Dict[str, Any]]:
    """Detect rising or falling wedge."""
    if len(df) < lookback:
        return None
    
    recent = df.tail(lookback)
    highs = recent.get("high", recent["close"])
    lows = recent.get("low", recent["close"])
    
    x = np.arange(len(highs))
    
    high_slope = np.polyfit(x, highs.values, 1)[0]
    low_slope = np.polyfit(x, lows.values, 1)[0]
    
    # Rising wedge (bearish): both slopes positive but high slope < low slope
    if high_slope > 0 and low_slope > 0 and high_slope < low_slope:
        return {"pattern": "rising_wedge", "confidence": 0.70}
    
    # Falling wedge (bullish): both slopes negative but high slope > low slope
    if high_slope < 0 and low_slope < 0 and high_slope > low_slope:
        return {"pattern": "falling_wedge", "confidence": 0.70}
    
    return None


def detect_flag(df: pd.DataFrame, lookback: int = 20) -> Optional[Dict[str, Any]]:
    """Detect flag pattern (continuation)."""
    if len(df) < lookback:
        return None
    
    recent = df.tail(lookback)
    closes = recent["close"]
    
    # Strong move followed by consolidation
    early_move = closes.iloc[:5].diff().abs().mean()
    late_consolidation = closes.iloc[-5:].diff().abs().mean()
    
    if early_move > late_consolidation * 2:
        # Check direction
        if closes.iloc[4] > closes.iloc[0]:
            return {"pattern": "flag", "confidence": 0.65, "direction": "bullish"}
        else:
            return {"pattern": "flag", "confidence": 0.65, "direction": "bearish"}
    
    return None


# Pattern detector class for Pulse integration
class ChartPatternDetector:
    """Detects chart patterns in OHLCV data."""
    
    def __init__(self, lookback: int = 60):
        self.lookback = lookback
    
    def detect_all(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Run all pattern detectors and return findings."""
        patterns = []
        
        # First: Check TA-Lib single-candle patterns
        if TALIB_AVAILABLE:
            ta_patterns = detect_candlestick_patterns_ta(df)
            for name, info in ta_patterns.items():
                if info.get("confidence", 0) >= 0.5:
                    patterns.append({
                        "pattern": name,
                        "confidence": info["confidence"],
                        "direction": info["direction"],
                        "source": "talib",
                    })
        
        # Custom multi-candle patterns
        # Double bottom (bullish)
        result = detect_double_bottom(df)
        if result:
            result["direction"] = "bullish"
            result["source"] = "custom"
            patterns.append(result)
        
        # Double top (bearish)
        result = detect_double_top(df)
        if result:
            result["direction"] = "bearish"
            result["source"] = "custom"
            patterns.append(result)
        
        # Head and shoulders (bearish)
        result = detect_head_shoulders(df)
        if result:
            result["direction"] = "bearish"
            result["source"] = "custom"
            patterns.append(result)
        
        # Inverse H&S (bullish)
        result = detect_inverse_head_shoulders(df)
        if result:
            result["direction"] = "bullish"
            result["source"] = "custom"
            patterns.append(result)
        
        # Triangles
        result = detect_triangle(df)
        if result:
            result["source"] = "custom"
            patterns.append(result)
        
        # Wedges
        result = detect_wedge(df)
        if result:
            result["source"] = "custom"
            patterns.append(result)
        
        # Flags
        result = detect_flag(df)
        if result:
            result["source"] = "custom"
            patterns.append(result)
        
        # Sort by confidence
        patterns.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        return patterns
    
    def get_best_pattern(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Get highest confidence pattern."""
        patterns = self.detect_all(df)
        return patterns[0] if patterns else None


# Example usage for Pulse integration
if __name__ == "__main__":
    import sys
    
    # Demo with sample data
    np.random.seed(42)
    n = 100
    
    # Generate double bottom pattern
    prices = 100 + np.cumsum(np.random.randn(n) * 0.5)
    # Inject W shape
    prices[40:45] = [98, 95, 97, 95, 98]
    prices[55:60] = [98, 94, 97, 95, 99]
    
    df = pd.DataFrame({
        "open": prices + np.random.randn(n) * 0.2,
        "high": prices + np.abs(np.random.randn(n)),
        "low": prices - np.abs(np.random.randn(n)),
        "close": prices,
        "volume": np.random.randint(1000000, 5000000, n),
    })
    
    detector = ChartPatternDetector()
    patterns = detector.detect_all(df)
    
    print("Detected patterns:")
    for p in patterns:
        print(f"  {p['pattern']}: {p['confidence']:.2%}")