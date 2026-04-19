"""Strategy registry API — list, schema, reload."""
from fastapi import APIRouter, HTTPException

import deps
from strategies.loader import STRATEGY_REGISTRY, reload_strategies
from strategies.presets import PRESET_STRATEGIES

router = APIRouter(tags=["Strategies"])


@router.get("/strategies/registry")
async def list_strategy_registry():
    """List all registered signal-based strategies with metadata and JSON schema."""
    return {
        "strategies": {
            name: s.to_registry_dict()
            for name, s in STRATEGY_REGISTRY.items()
            if s.metadata.is_signal_strategy
        },
        "count": sum(1 for s in STRATEGY_REGISTRY.values() if s.metadata.is_signal_strategy),
    }


@router.get("/strategies/registry/{name}")
async def get_strategy_detail(name: str):
    """Get full metadata + JSON schema for a specific strategy."""
    strategy = STRATEGY_REGISTRY.get(name)
    if not strategy:
        raise HTTPException(404, f"Strategy '{name}' not found in registry")
    return strategy.to_registry_dict()


@router.post("/strategies/reload")
async def trigger_reload():
    """Hot-reload all strategies from disk. Safe to call at any time."""
    result = await reload_strategies()
    return {
        "ok": True,
        "loaded": list(result.keys()),
        "count": len(result),
    }


@router.get("/strategies/presets")
async def list_presets():
    """List all bracket-based preset strategies (backward-compat endpoint)."""
    return {k: v.model_dump() for k, v in PRESET_STRATEGIES.items()}
