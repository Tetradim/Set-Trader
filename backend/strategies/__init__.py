"""
Sentinel Pulse — Pluggable Strategy System
Backward-compatible drop-in replacement for strategies.py.
"""
# Re-export PRESET_STRATEGIES so existing imports keep working:
#   from strategies import PRESET_STRATEGIES
from .presets import PRESET_STRATEGIES
from .base import BaseStrategy, Signal, StrategyMetadata, StrategyConfigModel
from .loader import STRATEGY_REGISTRY, load_all_strategies, reload_strategies

__all__ = [
    "PRESET_STRATEGIES",
    "BaseStrategy", "Signal", "StrategyMetadata", "StrategyConfigModel",
    "STRATEGY_REGISTRY", "load_all_strategies", "reload_strategies",
]
