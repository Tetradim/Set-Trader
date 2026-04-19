"""
Observation models with Pydantic validation and scoring.

Observations flow from Pulse to Edge via WebSocket or MongoDB.
This module provides schema-validated observation models with:
- Pydantic validation (strict schema)
- Confidence scoring
- Timeframe desync handling
"""
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


class ObservationSource(str, Enum):
    PULSE = "pulse"
    EDGE = "edge"
    EXTERNAL = "external"
    PATTERN_SCANNER = "pattern_scanner"


class ObservationType(str, Enum):
    PATTERN = "pattern"
    EXECUTION = "execution"
    RISK = "risk"
    HEALTH = "health"
    SIGNAL = "signal"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --- Base Observation Model ---
class BaseObservation(BaseModel):
    """Base observation with schema validation.
    
    Strict validation (extra fields forbidden) ensures clean data flow.
    """
    model_config = ConfigDict(
        extra="forbid",  # Reject unknown fields
        str_strip_whitespace=True,
    )
    
    # Required fields
    symbol: str = Field(description="Ticker symbol")
    observation_type: ObservationType = Field(description="Type of observation")
    source: ObservationSource = Field(description="Source system")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Confidence scoring
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence 0-1")
    confidence_level: ConfidenceLevel = Field(description="Qualitative confidence")
    
    # Optional metadata
    broker_data: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        return v.upper().strip()
    
    @field_validator("confidence_level")
    @classmethod
    def derive_confidence_level(cls, v: str, info) -> ConfidenceLevel:
        if hasattr(info.data, "confidence"):
            conf = info.data.get("confidence", 0)
            if conf >= 0.8:
                return ConfidenceLevel.HIGH
            elif conf >= 0.5:
                return ConfidenceLevel.MEDIUM
            return ConfidenceLevel.LOW
        return ConfidenceLevel.MEDIUM


class PatternObservation(BaseObservation):
    """Chart pattern observation (from Pulse pattern scanner)."""
    observation_type: ObservationType = Field(default=ObservationType.PATTERN)
    
    # Pattern-specific fields
    pattern_name: str = Field(description="Pattern name (double_bottom, etc.)")
    pattern_direction: str = Field(description="bullish, bearish, neutral")
    pattern_weight: float = Field(ge=0.0, le=1.0, default=0.10)
    
    # TA-Lib indicator if applicable
    talib_indicator: Optional[str] = Field(default=None)


class ExecutionObservation(BaseObservation):
    """Execution observation (order fill, cancel, reject)."""
    observation_type: ObservationType = Field(default=ObservationType.EXECUTION)
    
    order_id: str
    execution_side: str  # BUY, SELL
    execution_price: float
    execution_quantity: float
    execution_result: str  # filled, partial, cancelled, rejected
    reason: str = ""


class RiskObservation(BaseObservation):
    """Risk observation (drawdown, volatility spike, etc.)."""
    observation_type: ObservationType = Field(default=ObservationType.RISK)
    
    risk_type: str  # drawdown, volatility, concentration
    risk_value: float
    threshold: float


class HealthObservation(BaseObservation):
    """Health check observation (broker disconnect, etc.)."""
    observation_type: ObservationType = Field(default=ObservationType.HEALTH)
    
    component: str  # broker, database, network
    health_status: str  # healthy, degraded, failed


# --- Observation Scorer ---
class ObservationScorer:
    """Score and weight observations for signal adjustment."""
    
    # Source weights (trust levels)
    SOURCE_WEIGHTS = {
        ObservationSource.PULSE: 1.0,
        ObservationSource.EDGE: 1.0,
        ObservationSource.PATTERN_SCANNER: 1.0,
        ObservationSource.EXTERNAL: 0.5,  # Lower trust
    }
    
    # Confidence multipliers
    HIGH_CONFIDENCE_MULT = 1.25
    TIMEFRAME_MATCH_BONUS = 0.2
    MAX_ADJUSTMENT = 1.5  # Max signal adjustment points
    
    def __init__(
        self,
        max_observations_per_symbol: int = 50,
        observation_max_age_seconds: int = 300,
    ):
        self.max_observations_per_symbol = max_observations_per_symbol
        self.observation_max_age_seconds = observation_max_age_seconds
        self._observations: Dict[str, List[BaseObservation]] = {}
    
    def add_observation(self, obs: BaseObservation) -> None:
        """Add observation for a symbol."""
        symbol = obs.symbol
        if symbol not in self._observations:
            self._observations[symbol] = []
        
        self._observations[symbol].append(obs)
        
        # Trim to max
        if len(self._observations[symbol]) > self.max_observations_per_symbol:
            self._observations[symbol] = self._observations[symbol][-self.max_observations_per_symbol:]
    
    def get_latest(self, symbol: str) -> Optional[BaseObservation]:
        """Get most recent observation for symbol."""
        obs_list = self._observations.get(symbol, [])
        return obs_list[-1] if obs_list else None
    
    def get_observations(self, symbol: str) -> List[BaseObservation]:
        """Get all observations for symbol."""
        return self._observations.get(symbol, [])
    
    def clear_old(self, max_age_seconds: int = None) -> int:
        """Clear observations older than max_age_seconds."""
        max_age = max_age_seconds or self.observation_max_age_seconds
        cutoff = datetime.now(timezone.utc).timestamp() - max_age
        
        removed = 0
        for symbol in list(self._observations.keys()):
            obs_list = self._observations[symbol]
            new_list = []
            
            for obs in obs_list:
                try:
                    obs_time = datetime.fromisoformat(obs.timestamp.replace("Z", "+00:00")).timestamp()
                    if obs_time >= cutoff:
                        new_list.append(obs)
                    else:
                        removed += 1
                except Exception:
                    new_list.append(obs)
            
            self._observations[symbol] = new_list
        
        return removed
    
    def calculate_impact(self, obs: BaseObservation) -> float:
        """Calculate observation impact (-1.0 to +1.0)."""
        if not obs:
            return 0.0
        
        # Source weight
        source_weight = self.SOURCE_WEIGHTS.get(obs.source, 0.5)
        
        # Confidence multiplier
        conf_mult = 1.0
        if obs.confidence >= 0.8:
            conf_mult = self.HIGH_CONFIDENCE_MULT
        elif obs.confidence < 0.5:
            conf_mult = 0.75
        
        # Base impact from confidence
        base_impact = obs.confidence * source_weight * conf_mult
        
        # Direction adjustment
        if isinstance(obs, PatternObservation):
            if obs.pattern_direction == "bullish":
                return base_impact
            elif obs.pattern_direction == "bearish":
                return -base_impact
        
        return 0.0
    
    def get_observation_impact(
        self,
        symbol: str,
        current_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get impact calculation for a symbol."""
        obs = self.get_latest(symbol)
        if not obs:
            return {"has_observation": False, "impact": 0.0}
        
        now = current_time or datetime.now(timezone.utc)
        
        try:
            obs_time = datetime.fromisoformat(obs.timestamp.replace("Z", "+00:00"))
            age_seconds = (now - obs_time).total_seconds()
        except Exception:
            age_seconds = 0
        
        impact = self.calculate_impact(obs)
        
        return {
            "has_observation": True,
            "observation": obs.model_dump(),
            "impact": impact,
            "age_seconds": age_seconds,
            "confidence": obs.confidence,
            "source": obs.source.value,
            "pattern": obs.pattern_name if isinstance(obs, PatternObservation) else None,
        }
    
    def apply_adjustment(
        self,
        signal_strength: float,
        symbol: str,
    ) -> float:
        """Apply observation adjustment to signal strength."""
        impact_info = self.get_observation_impact(symbol)
        
        if not impact_info.get("has_observation"):
            return signal_strength
        
        impact = impact_info.get("impact", 0.0)
        
        # Scale impact to signal adjustment
        adjustment = impact * self.MAX_ADJUSTMENT
        
        return signal_strength + adjustment


class ObservationDesyncMonitor:
    """Monitor desync between observation time and current time."""
    
    def __init__(
        self,
        max_timeframe_diff_seconds: int = 60,
        observation_max_age_seconds: int = 300,
    ):
        self.max_timeframe_diff_seconds = max_timeframe_diff_seconds
        self.observation_max_age_seconds = observation_max_age_seconds
        self._last_check: Dict[str, datetime] = {}
    
    def check_desync(
        self,
        obs: Optional[BaseObservation],
        current_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Check for timeframe desync."""
        now = current_time or datetime.now(timezone.utc)
        
        if not obs:
            return {
                "desynced": False,
                "severity": "none",
                "age_seconds": 0,
            }
        
        try:
            obs_time = datetime.fromisoformat(obs.timestamp.replace("Z", "+00:00"))
            age_seconds = (now - obs_time).total_seconds()
        except Exception:
            age_seconds = 0
        
        # Determine severity
        severity = "none"
        desynced = False
        
        if age_seconds > self.observation_max_age_seconds:
            severity = "expired"
            desynced = True
        elif age_seconds > self.max_timeframe_diff_seconds * 2:
            severity = "high"
            desynced = True
        elif age_seconds > self.max_timeframe_diff_seconds:
            severity = "warning"
            desynced = True
        
        return {
            "desynced": desynced,
            "severity": severity,
            "age_seconds": age_seconds,
            "max_allowed": self.max_timeframe_diff_seconds,
            "expired": age_seconds > self.observation_max_age_seconds,
        }
    
    def log_warning(self, symbol: str, severity: str, age_seconds: float) -> None:
        """Log desync warning."""
        if severity == "high":
            logger.warning(
                f"OBSERVATION desync: {symbol} age={age_seconds:.0f}s severity={severity}"
            )
        elif severity == "warning":
            logger.info(
                f"OBSERVATION desync: {symbol} age={age_seconds:.0f}s severity={severity}"
            )


# --- Singleton instances ---
observation_scorer = ObservationScorer()
desync_monitor = ObservationDesyncMonitor()


# --- Helper functions ---
def create_pattern_observation(
    symbol: str,
    pattern_name: str,
    confidence: float,
    direction: str,
    pattern_weight: float = 0.10,
    source: ObservationSource = ObservationSource.PATTERN_SCANNER,
    broker_data: Optional[Dict] = None,
) -> PatternObservation:
    """Create a validated pattern observation."""
    # Derive confidence level
    if confidence >= 0.8:
        conf_level = ConfidenceLevel.HIGH
    elif confidence >= 0.5:
        conf_level = ConfidenceLevel.MEDIUM
    else:
        conf_level = ConfidenceLevel.LOW
    
    return PatternObservation(
        symbol=symbol,
        observation_type=ObservationType.PATTERN,
        source=source,
        confidence=confidence,
        confidence_level=conf_level,
        pattern_name=pattern_name,
        pattern_direction=direction,
        pattern_weight=pattern_weight,
        broker_data=broker_data or {},
    )


def validate_observation(data: Dict[str, Any]) -> Optional[BaseObservation]:
    """Validate incoming observation data with Pydantic.
    
    Returns None if validation fails.
    """
    try:
        obs_type = data.get("observation_type", "")
        
        if obs_type == "pattern":
            return PatternObservation(**data)
        elif obs_type == "execution":
            return ExecutionObservation(**data)
        elif obs_type == "risk":
            return RiskObservation(**data)
        elif obs_type == "health":
            return HealthObservation(**data)
        else:
            # Unknown type, try base
            return BaseObservation(**data)
    except Exception as e:
        logger.warning(f"Observation validation failed: {e}")
        return None