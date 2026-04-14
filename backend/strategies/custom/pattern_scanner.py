"""
strategies/custom/pattern_scanner.py
Pattern Scanner Strategy - Detects chart patterns and optionally sends to Edge.

Enable via settings:
- pattern_detection_enabled: Enable/disable pattern scanning
- pattern_min_confidence: Minimum confidence threshold (default 0.65)
- pattern_send_to_edge: Send observations to Edge via WebSocket
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import pandas as pd
from pydantic import Field

from strategies.base import BaseStrategy, Signal, StrategyConfigModel, StrategyMetadata
from shared.chart_pattern_detector import ChartPatternDetector

logger = logging.getLogger(__name__)


class PatternScannerParams(StrategyConfigModel):
    min_confidence: float = Field(0.65, ge=0.3, le=0.95, title="Min Confidence")
    lookback_bars: int = Field(60, ge=20, le=200, title="Lookback Bars")
    scan_interval: int = Field(1, ge=1, le=60, title="Scan Every N Ticks")
    send_to_edge: bool = Field(True, title="Send Observations to Edge")
    patterns: str = Field("all", title="Patterns (comma-separated or 'all')")


class PatternScannerStrategy(BaseStrategy):

    metadata = StrategyMetadata(
        name="Pattern Scanner",
        version="1.0.0",
        description="Scans for chart patterns, optionally sends to Edge as 6th scoring layer.",
        author="Signal Forge Lab",
        tags=["pattern", "chart", "scanner", "double_top", "double_bottom"],
        risk_level="LOW",
        requires_history_bars=60,
        supported_markets=["US", "HK", "AU", "UK", "CA", "CN_SS", "CN_SZ"],
    )

    params_model = PatternScannerParams
    default_params = PatternScannerParams().model_dump()

    def __init__(self):
        super().__init__()
        self._scan_counter = 0
        self._last_patterns: Dict[str, Dict] = {}
        self._detector = ChartPatternDetector(lookback=self.params["lookback_bars"])

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
        if df is None or len(df) < params["lookback_bars"]:
            return None

        # Check if pattern detection is enabled in settings
        from deps import db
        settings = await db.settings.find_one({"key": "pattern_detection_enabled"})
        if settings and not settings.get("value", True):
            return None

        # Scan interval check
        self._scan_counter += 1
        if self._scan_counter % params["scan_interval"] != 0:
            return None

        # Get min_confidence from settings if available
        min_conf = params["min_confidence"]
        settings_conf = await db.settings.find_one({"key": "pattern_min_confidence"})
        if settings_conf:
            min_conf = settings_conf.get("value", min_conf)

        # Check if we should send to Edge
        send_to_edge = params["send_to_edge"]
        edge_settings = await db.settings.find_one({"key": "pattern_send_to_edge"})
        if edge_settings is not None:
            send_to_edge = edge_settings.get("value", send_to_edge)

        # Run pattern detection
        patterns = self._detector.detect_all(df)
        
        if not patterns:
            return None

        # Get best pattern above threshold
        best_pattern = None
        for p in patterns:
            if p.get("confidence", 0) >= min_conf:
                best_pattern = p
                break

        if not best_pattern:
            return None

        symbol = ticker_doc.get("symbol", "")
        
        # Cache the pattern
        self._last_patterns[symbol] = best_pattern

        # Optionally send to Edge via WebSocket
        if send_to_edge:
            from deps import ws_manager
            from datetime import datetime, timezone
            
            observation = {
                "ticker": symbol,
                "pattern": best_pattern.get("pattern"),
                "confidence": best_pattern.get("confidence", 0.0),
                "direction": best_pattern.get("direction", "neutral"),
                "broker_data": {
                    "price": current_price,
                    "levels": best_pattern.get("levels", {}),
                },
            }
            
            # Store in database for scoring
            await db.observations.insert_one({
                "ticker": symbol,
                "pattern": best_pattern.get("pattern"),
                "confidence": best_pattern.get("confidence", 0.0),
                "direction": best_pattern.get("direction", "neutral"),
                "weight": best_pattern.get("weight", 0.10),
                "broker_data": observation.get("broker_data", {}),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "pattern_scanner",
            })
            
            # Broadcast to WebSocket clients
            await ws_manager.broadcast({
                "type": "OBSERVATION",
                "observation": observation,
                "stored": True,
            })
            
            logger.info(f"[Pattern] {symbol}: {best_pattern['pattern']} ({best_pattern['confidence']:.0%}) → Edge")

        # Return signal based on pattern direction
        direction = best_pattern.get("direction", "neutral")
        confidence = best_pattern.get("confidence", 0.0)

        if direction == "bullish":
            return Signal(
                action="BUY",
                confidence=round(confidence, 3),
                reason=f"Pattern: {best_pattern['pattern']} (bullish)",
            )
        elif direction == "bearish":
            return Signal(
                action="SELL",
                confidence=round(confidence, 3),
                reason=f"Pattern: {best_pattern['pattern']} (bearish)",
            )

        # Neutral pattern - just notify, no trade
        logger.debug(f"[Pattern] {symbol}: {best_pattern['pattern']} (neutral, no trade)")
        return None

    def get_last_pattern(self, symbol: str) -> Optional[Dict]:
        """Get the last detected pattern for a symbol."""
        return self._last_patterns.get(symbol)