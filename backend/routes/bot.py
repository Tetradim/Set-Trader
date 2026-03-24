"""Bot control and settings endpoints."""
from fastapi import APIRouter, HTTPException

import deps
from schemas import SettingsUpdate

router = APIRouter()


@router.post("/bot/start")
async def start_bot():
    deps.engine.running = True
    await deps.engine.save_state()
    await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": deps.engine.paused})
    deps.logger.info("Bot STARTED via API")
    return {"running": True}


@router.post("/bot/stop")
async def stop_bot():
    deps.engine.running = False
    await deps.engine.save_state()
    await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": deps.engine.paused})
    deps.logger.info("Bot STOPPED via API")
    return {"running": False}


@router.post("/settings")
async def update_settings(body: SettingsUpdate):
    if body.simulate_24_7 is not None:
        deps.engine.simulate_24_7 = body.simulate_24_7
        await deps.engine.save_state()
    if body.market_hours_only is not None:
        deps.engine.market_hours_only = body.market_hours_only
        await deps.engine.save_state()
    if body.live_during_market_hours is not None:
        deps.engine.live_during_market_hours = body.live_during_market_hours
        await deps.engine.save_state()
    if body.paper_after_hours is not None:
        deps.engine.paper_after_hours = body.paper_after_hours
        await deps.engine.save_state()
    if body.increment_step is not None:
        await deps.db.settings.update_one({"key": "increment_step"}, {"$set": {"value": body.increment_step}}, upsert=True)
    if body.decrement_step is not None:
        await deps.db.settings.update_one({"key": "decrement_step"}, {"$set": {"value": body.decrement_step}}, upsert=True)
    if body.account_balance is not None:
        if body.account_balance < 0 or body.account_balance > 100_000_000:
            raise HTTPException(400, "Account balance must be between $0 and $100,000,000.")
        await deps.db.settings.update_one({"key": "account_balance"}, {"$set": {"value": body.account_balance}}, upsert=True)
        tickers = await deps.db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
        allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)
        await deps.ws_manager.broadcast({
            "type": "ACCOUNT_UPDATE",
            "account_balance": round(body.account_balance, 2),
            "allocated": allocated,
            "available": round(body.account_balance - allocated, 2),
        })
    if body.telegram:
        doc = body.telegram.model_dump()
        await deps.db.settings.update_one({"key": "telegram"}, {"$set": {"value": doc}}, upsert=True)
        if doc.get("bot_token"):
            try:
                await deps.telegram_service.start(doc["bot_token"], doc.get("chat_ids", []))
            except Exception as e:
                deps.logger.error(f"Telegram start failed: {e}")
        else:
            await deps.telegram_service.stop()
    return {"ok": True, "telegram_running": deps.telegram_service.running}


@router.get("/settings")
async def get_settings():
    tg = await deps.db.settings.find_one({"key": "telegram"}, {"_id": 0})
    inc_doc = await deps.db.settings.find_one({"key": "increment_step"}, {"_id": 0})
    dec_doc = await deps.db.settings.find_one({"key": "decrement_step"}, {"_id": 0})
    cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    tickers = await deps.db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
    allocated = sum(t.get("base_power", 0) for t in tickers)
    account_balance = balance_doc.get("value", 0) if balance_doc else 0
    cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0
    return {
        "simulate_24_7": deps.engine.simulate_24_7,
        "market_hours_only": deps.engine.market_hours_only,
        "live_during_market_hours": deps.engine.live_during_market_hours,
        "paper_after_hours": deps.engine.paper_after_hours,
        "trading_mode": "paper" if deps.engine.simulate_24_7 else "live",
        "telegram": tg.get("value", {}) if tg else {"bot_token": "", "chat_ids": []},
        "telegram_connected": deps.telegram_service.running,
        "increment_step": inc_doc.get("value", 0.5) if inc_doc else 0.5,
        "decrement_step": dec_doc.get("value", 0.5) if dec_doc else 0.5,
        "cash_reserve": cash_reserve,
        "account_balance": round(account_balance, 2),
        "allocated": round(allocated, 2),
        "available": round(account_balance - allocated, 2),
    }


@router.post("/settings/telegram/test")
async def test_telegram():
    if not deps.telegram_service.running:
        raise HTTPException(400, "Telegram bot is not connected. Save a valid token first.")
    await deps.telegram_service._broadcast_alert("Test alert from Sentinel Pulse! Connection verified.")
    return {"ok": True, "sent_to": deps.telegram_service.chat_ids}
