"""Bot control endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel

import deps
from bot_snapshot import build_bot_snapshot

router = APIRouter()


class BotControlRequest(BaseModel):
    enable_all: bool = True
    disable_all: bool = True


async def _broadcast_tickers():
    docs = await deps.db.tickers.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)
    await deps.ws_manager.broadcast({"type": "TICKERS_REORDERED", "tickers": docs})
    return docs


@router.get("/bot/snapshot")
async def get_bot_snapshot():
    snapshot = await build_bot_snapshot()
    return {
        "tickers": snapshot["tickers"],
        "prices": snapshot["prices"],
        "price_sources": snapshot["price_sources"],
        "price_errors": snapshot["price_errors"],
        "positions": snapshot["positions"],
        "profits": snapshot["profits"],
        "trades": snapshot["trades"],
        "cash_reserve": snapshot["cash_reserve"],
        "account_balance": snapshot["account_balance"],
        "allocated": snapshot["allocated"],
        "available": snapshot["available"],
        "increment_step": snapshot["increment_step"],
        "decrement_step": snapshot["decrement_step"],
        "paused": deps.engine.paused,
        "running": deps.engine.running,
        "market_open": deps.engine.is_market_open(),
        "simulate_24_7": deps.engine.simulate_24_7,
        "market_hours_only": deps.engine.market_hours_only,
        "live_during_market_hours": deps.engine.live_during_market_hours,
        "paper_after_hours": deps.engine.paper_after_hours,
        "replay": snapshot["replay"],
    }


@router.post("/bot/start")
async def start_bot(body: BotControlRequest | None = None):
    settings = body or BotControlRequest()
    tickers = None
    if settings.enable_all:
        await deps.db.tickers.update_many(
            {},
            {"$set": {"enabled": True, "auto_stopped": False, "auto_stop_reason": "", "buying_paused": False}},
        )
        tickers = await _broadcast_tickers()
    deps.engine.running = True
    deps.engine.paused = False
    await deps.engine.save_state()
    await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": False})
    deps.logger.info("Bot STARTED via API; enable_all=%s", settings.enable_all)
    return {"running": True, "paused": False, "tickers": tickers}


@router.post("/bot/pause")
async def pause_bot():
    deps.engine.paused = not deps.engine.paused
    await deps.engine.save_state()
    await deps.ws_manager.broadcast({
        "type": "BOT_STATUS",
        "running": deps.engine.running,
        "paused": deps.engine.paused,
    })
    deps.logger.info("Bot PAUSE toggled via API: paused=%s", deps.engine.paused)
    return {"running": deps.engine.running, "paused": deps.engine.paused}


@router.post("/bot/reload-state")
async def reload_bot_state():
    """Reload persisted runtime state without changing bot mode."""
    await deps.engine.load_state()
    return {
        "running": deps.engine.running,
        "paused": deps.engine.paused,
        "positions": len(getattr(deps.engine, "_positions", {}) or {}),
    }


@router.post("/tickers/{symbol}/rebracket/revert")
async def revert_ticker_bracket(symbol: str):
    """Revert a ticker's bracket to the previous one.
    
    Returns:
        dict with success status and reverted bracket info
    """
    sym = symbol.upper()
    result = await deps.engine.revert_bracket(sym)
    return result


@router.post("/bot/stop")
async def stop_bot(body: BotControlRequest | None = None):
    settings = body or BotControlRequest()
    deps.engine.running = False
    deps.engine.paused = False
    deps.engine._pending_sells.clear()
    tickers = None
    if settings.disable_all:
        await deps.db.tickers.update_many({}, {"$set": {"enabled": False}})
        tickers = await _broadcast_tickers()
    await deps.engine.save_state()
    await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": False})
    deps.logger.info("Bot STOPPED via API; disable_all=%s", settings.disable_all)
    return {"running": False, "paused": False, "tickers": tickers}
