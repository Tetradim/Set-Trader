"""
Observation system for Pulse → Edge pattern signals.

Pulse can send chart pattern observations (e.g., double_bottom, head_shoulders)
via WebSocket or REST. Edge's SignalEngine can query these as an optional 6th
scoring layer.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Known chart patterns
CHART_PATTERNS = {
    # Bullish patterns
    "double_bottom": {"direction": "bullish", "weight": 0.15},
    "head_shoulders_inverse": {"direction": "bullish", "weight": 0.15},
    "ascending_triangle": {"direction": "bullish", "weight": 0.12},
    "bullish_divergence": {"direction": "bullish", "weight": 0.18},
    "falling_wedge": {"direction": "bullish", "weight": 0.12},
    "cup_and_handle": {"direction": "bullish", "weight": 0.14},
    "morning_star": {"direction": "bullish", "weight": 0.16},
    "bullish_engulfing": {"direction": "bullish", "weight": 0.15},
    "piercing_line": {"direction": "bullish", "weight": 0.14},
    
    # Bearish patterns
    "double_top": {"direction": "bearish", "weight": 0.15},
    "head_shoulders": {"direction": "bearish", "weight": 0.15},
    "descending_triangle": {"direction": "bearish", "weight": 0.12},
    "bearish_divergence": {"direction": "bearish", "weight": 0.18},
    "rising_wedge": {"direction": "bearish", "weight": 0.12},
    "cup_and_handle_inverse": {"direction": "bearish", "weight": 0.14},
    "evening_star": {"direction": "bearish", "weight": 0.16},
    "bearish_engulfing": {"direction": "bearish", "weight": 0.15},
    "dark_cloud_cover": {"direction": "bearish", "weight": 0.14},
    
    # Neutral/continuation patterns
    "flag": {"direction": "neutral", "weight": 0.08},
    "pennant": {"direction": "neutral", "weight": 0.08},
    "wedge": {"direction": "neutral", "weight": 0.10},
}


class ObservationService:
    """Service for managing pattern observations."""
    
    def __init__(self, db=None):
        self.db = db
    
    def set_db(self, db):
        self.db = db
    
    async def add_observation(
        self,
        ticker: str,
        pattern: str,
        confidence: float,
        broker_data: Optional[Dict[str, Any]] = None,
        source: str = "pulse",
    ) -> Dict[str, Any]:
        """Add a new observation to the database."""
        if not self.db:
            return {"error": "Database not initialized"}
        
        # Validate pattern
        pattern_info = CHART_PATTERNS.get(pattern, {"direction": "neutral", "weight": 0.10})
        
        obs_doc = {
            "ticker": ticker.upper(),
            "pattern": pattern,
            "direction": pattern_info.get("direction", "neutral"),
            "weight": pattern_info.get("weight", 0.10),
            "confidence": min(max(confidence, 0.0), 1.0),
            "broker_data": broker_data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
        }
        
        await self.db.observations.insert_one(obs_doc)
        logger.info(f"Observation added: {ticker} {pattern} ({confidence:.2f})")
        
        return obs_doc
    
    async def get_latest_observation(self, ticker: str, max_age_seconds: int = 3600) -> Optional[Dict[str, Any]]:
        """Get the latest observation for a ticker within max age."""
        if not self.db:
            return None
        
        cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
        
        obs = await self.db.observations.find_one(
            {
                "ticker": ticker.upper(),
                "timestamp_unix": {"$gte": cutoff},
            },
            sort=[("timestamp_unix", -1)],
        )
        
        # Add timestamp_unix for filtering
        if obs and "timestamp" in obs:
            try:
                dt = datetime.fromisoformat(obs["timestamp"].replace("Z", "+00:00"))
                obs["timestamp_unix"] = dt.timestamp()
            except Exception:
                pass
        
        return obs
    
    async def get_observations_for_scoring(
        self,
        ticker: str,
        max_age_seconds: int = 3600,
        min_confidence: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Get observations suitable for scoring (used by SignalEngine)."""
        if not self.db:
            return []
        
        import time
        cutoff = time.time() - max_age_seconds
        
        cursor = self.db.observations.find({
            "ticker": ticker.upper(),
            "confidence": {"$gte": min_confidence},
            "timestamp_unix": {"$gte": cutoff},
        }).sort("timestamp_unix", -1).limit(10)
        
        observations = await cursor.to_list(10)
        
        # Add timestamp_unix if not present
        for obs in observations:
            if "timestamp" in obs and "timestamp_unix" not in obs:
                try:
                    dt = datetime.fromisoformat(obs["timestamp"].replace("Z", "+00:00"))
                    obs["timestamp_unix"] = dt.timestamp()
                except Exception:
                    pass
        
        return observations
    
    async def get_pattern_direction(self, ticker: str) -> str:
        """Get aggregate pattern direction for a ticker (bullish/bearish/neutral)."""
        obs = await self.get_latest_observation(ticker)
        if obs:
            return obs.get("direction", "neutral")
        return "neutral"
    
    async def get_pattern_confidence(self, ticker: str) -> float:
        """Get confidence score from latest observation."""
        obs = await self.get_latest_observation(ticker)
        if obs:
            return obs.get("confidence", 0.0)
        return 0.0


# Singleton instance
observation_service = ObservationService()