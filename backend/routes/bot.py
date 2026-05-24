"""Bot control endpoints."""
from fastapi import APIRouter

import deps

router = APIRouter()


@router.post("/bot/start")
async def start_bot():
    deps.engine.running = True
    await deps.engine.save_state()
    await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": deps.engine.paused})
    deps.logger.info("Bot STARTED via API")
    return {"running": True}


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
async def stop_bot():
    deps.engine.running = False
    await deps.engine.save_state()
    await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": deps.engine.paused})
    deps.logger.info("Bot STOPPED via API")
    return {"running": False}
