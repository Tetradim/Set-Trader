"""
backend/strategies/loader.py
Dynamic strategy loader with hot-reload, error isolation, and async safety.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import pkgutil
import threading
from pathlib import Path
from typing import Dict, Optional

import watchdog.events
import watchdog.observers

from .base import BaseStrategy

logger = logging.getLogger(__name__)

# Singleton registry — populated by load_all_strategies()
STRATEGY_REGISTRY: Dict[str, BaseStrategy] = {}

CUSTOM_DIR   = Path(__file__).parent / "custom"
PRESETS_DIR  = Path(__file__).parent / "presets"

_observer: Optional[watchdog.observers.Observer] = None


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

async def load_all_strategies() -> Dict[str, BaseStrategy]:
    """Discover and register all strategies from presets/ and custom/."""
    global STRATEGY_REGISTRY
    STRATEGY_REGISTRY.clear()

    await _load_from_dir(PRESETS_DIR,  namespace="presets")
    await _load_from_dir(CUSTOM_DIR,   namespace="custom")

    logger.info(
        f"Strategy registry: {len(STRATEGY_REGISTRY)} loaded "
        f"({list(STRATEGY_REGISTRY.keys())})"
    )
    return STRATEGY_REGISTRY


async def reload_strategies() -> Dict[str, BaseStrategy]:
    """Hot-reload all strategies. Safe to call from any context."""
    logger.info("Reloading strategy registry …")
    result = await load_all_strategies()
    # Broadcast via ws_manager if available
    try:
        import deps
        if deps.ws_manager:
            await deps.ws_manager.broadcast({
                "type": "STRATEGIES_RELOADED",
                "strategies": list(result.keys()),
            })
    except Exception:
        pass
    return result


async def _load_from_dir(directory: Path, namespace: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    
    # Debug: log file count
    py_files = list(directory.glob("*.py"))
    logger.debug(f"[{namespace}] scanning: {directory}, found {len(py_files)} .py files")
    logger.debug(f"[{namespace}] files: {[f.name for f in py_files]}")
    
    for finder, mod_name, is_pkg in pkgutil.iter_modules([str(directory)]):
        if mod_name.startswith("_") or is_pkg:
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"strategies.{namespace}.{mod_name}",
                directory / f"{mod_name}.py",
            )
            module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(module)  # type: ignore[union-attr]

            for attr_name in dir(module):
                obj = getattr(module, attr_name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseStrategy)
                    and obj is not BaseStrategy
                ):
                    instance: BaseStrategy = obj()
                    await instance.on_load()
                    key = instance.metadata.name
                    STRATEGY_REGISTRY[key] = instance
                    logger.info(
                        f"  [+] {key} v{instance.metadata.version} "
                        f"({namespace}) — signal={instance.metadata.is_signal_strategy}"
                    )
        except Exception as exc:
            logger.error(f"Failed to load strategy '{mod_name}': {exc}", exc_info=True)


# ---------------------------------------------------------------------------
# Watchdog hot-reload (non-blocking, thread-safe async dispatch)
# ---------------------------------------------------------------------------

class _ReloadHandler(watchdog.events.FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def on_modified(self, event: watchdog.events.FileSystemEvent) -> None:
        if not event.is_directory and str(event.src_path).endswith(".py"):
            logger.info(f"Strategy file changed: {event.src_path} — scheduling reload")
            asyncio.run_coroutine_threadsafe(reload_strategies(), self._loop)

    on_created = on_modified   # also reload on new files


def start_strategy_watcher() -> None:
    """Start background file watcher for custom strategy hot-reload."""
    global _observer
    if _observer is not None:
        return  # already running

    try:
        loop = asyncio.get_event_loop()
        CUSTOM_DIR.mkdir(parents=True, exist_ok=True)

        _observer = watchdog.observers.Observer()
        _observer.schedule(_ReloadHandler(loop), str(CUSTOM_DIR), recursive=False)
        _observer.daemon = True
        _observer.start()
        logger.info(f"Strategy hot-reload watcher started on {CUSTOM_DIR}")
    except Exception as exc:
        logger.warning(f"Could not start strategy watcher: {exc}")
