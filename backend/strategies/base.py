"""
backend/strategies/base.py
Core abstractions for the pluggable strategy system.
Pydantic v2 config models enable automatic JSON-schema UI form generation.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

@dataclass
class StrategyMetadata:
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = "Community"
    tags: List[str] = field(default_factory=list)
    risk_level: str = "MEDIUM"          # LOW | MEDIUM | HIGH
    requires_history_bars: int = 100
    supported_markets: List[str] = field(
        default_factory=lambda: ["US", "HK", "AU", "UK", "CA", "CN_SS", "CN_SZ"]
    )
    is_signal_strategy: bool = True     # False = preset config template only


# ---------------------------------------------------------------------------
# Parameter model — subclass to define strategy-specific params
# ---------------------------------------------------------------------------

class StrategyConfigModel(BaseModel):
    """
    Base Pydantic model for strategy parameters.
    Subclass and add typed fields; model_json_schema() drives UI form generation.
    """
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    action: str                        # BUY | SELL | HOLD | STOP_LOSS | TRAILING_STOP | TAKE_PROFIT
    confidence: float = 0.0            # 0.0 – 1.0
    reason: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseStrategy(ABC):
    """
    All signal-based strategies must subclass this.

    Class-level attributes to define on subclasses:
        metadata       — StrategyMetadata
        params_model   — StrategyConfigModel subclass (drives UI form)
        default_params — dict of default param values (from params_model().model_dump())
    """

    metadata: StrategyMetadata
    params_model: Type[StrategyConfigModel] = StrategyConfigModel
    default_params: Dict[str, Any] = {}

    # --- Lifecycle hooks ---------------------------------------------------

    async def on_load(self) -> None:
        """Called once when the strategy is registered. Override for setup."""

    async def validate_ticker(self, ticker_doc: dict) -> bool:
        """Return False to skip this strategy for a given ticker."""
        return True

    # --- Core method -------------------------------------------------------

    @abstractmethod
    async def generate_signals(
        self,
        ticker_doc: dict,
        current_price: float,
        market_data: Dict[str, Any],
        market_status: Dict[str, Any],
        broker_allocations: Dict[str, float],
        params: Dict[str, Any],
    ) -> Optional[Signal]:
        """
        Generate a trading signal (or None to fall through to bracket logic).

        Args:
            ticker_doc:         Full ticker MongoDB document.
            current_price:      Latest price in native market currency.
            market_data:        {"history": pd.DataFrame|None, "fx_rate": float}.
            market_status:      markets.MarketConfig.to_dict() for this ticker.
            broker_allocations: {broker_id: float} allocation map.
            params:             Merged default_params + per-ticker strategy_config.
        """

    # --- Helpers -----------------------------------------------------------

    def get_params(self, ticker_doc: dict) -> Dict[str, Any]:
        """Merge class defaults with per-ticker strategy_config overrides."""
        return {**self.default_params, **ticker_doc.get("strategy_config", {})}

    def get_config_schema(self) -> dict:
        """Returns Pydantic v2 JSON Schema for UI dynamic form generation."""
        return self.params_model.model_json_schema()

    def to_registry_dict(self) -> dict:
        """Serialisable summary for the /api/strategies/registry endpoint."""
        m = self.metadata
        return {
            "name": m.name,
            "version": m.version,
            "description": m.description,
            "author": m.author,
            "tags": m.tags,
            "risk_level": m.risk_level,
            "requires_history_bars": m.requires_history_bars,
            "supported_markets": m.supported_markets,
            "is_signal_strategy": m.is_signal_strategy,
            "default_params": self.default_params,
            "config_schema": self.get_config_schema(),
        }
