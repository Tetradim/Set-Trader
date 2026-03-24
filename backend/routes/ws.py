"""WebSocket endpoint — initial state + real-time message handling."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

import deps
from schemas import TickerConfig
from strategies import PRESET_STRATEGIES

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await deps.ws_manager.connect(websocket)
    try:
        tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
        prices = {}
        for t in tickers:
            prices[t["symbol"]] = await deps.price_service.get_price(t["symbol"])

        profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
        profits = {p["symbol"]: p.get("total_pnl", 0) for p in profits_list}

        cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
        cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0

        inc_doc = await deps.db.settings.find_one({"key": "increment_step"}, {"_id": 0})
        dec_doc = await deps.db.settings.find_one({"key": "decrement_step"}, {"_id": 0})
        balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
        account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
        allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)

        await websocket.send_json({
            "type": "INITIAL_STATE",
            "tickers": tickers,
            "prices": prices,
            "profits": profits,
            "cash_reserve": cash_reserve,
            "account_balance": account_balance,
            "allocated": allocated,
            "available": round(account_balance - allocated, 2),
            "increment_step": inc_doc.get("value", 0.5) if inc_doc else 0.5,
            "decrement_step": dec_doc.get("value", 0.5) if dec_doc else 0.5,
            "paused": deps.engine.paused,
            "running": deps.engine.running,
            "market_open": deps.engine.is_market_open(),
            "simulate_24_7": deps.engine.simulate_24_7,
            "market_hours_only": deps.engine.market_hours_only,
        })

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "ADD_TICKER":
                sym = msg.get("symbol", "").upper().strip()
                if sym:
                    t = TickerConfig(symbol=sym, base_power=msg.get("base_power", 100.0))
                    doc = t.model_dump()
                    try:
                        await deps.db.tickers.insert_one(doc)
                        doc.pop("_id", None)
                        await deps.ws_manager.broadcast({"type": "TICKER_ADDED", "ticker": doc})
                    except Exception:
                        pass

            elif action == "DELETE_TICKER":
                sym = msg.get("symbol", "").upper()
                await deps.db.tickers.delete_one({"symbol": sym})
                deps.engine._positions.pop(sym, None)
                await deps.ws_manager.broadcast({"type": "TICKER_DELETED", "symbol": sym})

            elif action == "UPDATE_TICKER":
                sym = msg.get("symbol", "").upper()
                updates = {k: v for k, v in msg.items() if k not in ("action", "symbol")}
                NUMERIC_BOUNDS = {
                    "base_power": (1, 10_000_000), "buy_offset": (-99999, 99999),
                    "sell_offset": (-99999, 99999), "stop_offset": (-99999, 99999),
                    "trailing_percent": (0.01, 50), "avg_days": (1, 365),
                    "max_daily_loss": (0, 999999), "max_consecutive_losses": (0, 100),
                    "rebracket_threshold": (0.01, 99999), "rebracket_spread": (0.01, 99999),
                    "rebracket_cooldown": (0, 3600), "rebracket_lookback": (2, 100),
                    "rebracket_buffer": (0, 99999),
                }
                valid = True
                for field, (lo, hi) in NUMERIC_BOUNDS.items():
                    if field in updates:
                        try:
                            val = float(updates[field])
                            updates[field] = max(lo, min(hi, val))
                        except (ValueError, TypeError):
                            valid = False
                            break
                if updates and valid:
                    await deps.db.tickers.update_one({"symbol": sym}, {"$set": updates})
                    doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if doc:
                        await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})

            elif action == "START_BOT":
                deps.engine.running = True
                deps.engine.paused = False
                await deps.engine.save_state()
                await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": False})

            elif action == "STOP_BOT":
                deps.engine.running = False
                deps.engine.paused = False
                await deps.engine.save_state()
                await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": False, "paused": False})

            elif action == "APPLY_STRATEGY":
                sym = msg.get("symbol", "").upper()
                preset = msg.get("preset", "")
                current_doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
                if not current_doc:
                    continue

                if current_doc.get("strategy") == preset:
                    backup = current_doc.get("custom_backup", {})
                    if backup:
                        backup["strategy"] = "custom"
                        backup.pop("custom_backup", None)
                        await deps.db.tickers.update_one({"symbol": sym}, {"$set": backup, "$unset": {"custom_backup": ""}})
                    else:
                        await deps.db.tickers.update_one({"symbol": sym}, {"$set": {"strategy": "custom"}})
                    doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if doc:
                        await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})
                    continue

                strategy = PRESET_STRATEGIES.get(preset)
                if strategy:
                    backup_fields = {
                        "avg_days": current_doc.get("avg_days"), "buy_offset": current_doc.get("buy_offset"),
                        "buy_percent": current_doc.get("buy_percent"), "buy_order_type": current_doc.get("buy_order_type", "limit"),
                        "sell_offset": current_doc.get("sell_offset"), "sell_percent": current_doc.get("sell_percent"),
                        "sell_order_type": current_doc.get("sell_order_type", "limit"),
                        "stop_offset": current_doc.get("stop_offset"), "stop_percent": current_doc.get("stop_percent"),
                        "stop_order_type": current_doc.get("stop_order_type", "limit"),
                        "trailing_enabled": current_doc.get("trailing_enabled"), "trailing_percent": current_doc.get("trailing_percent"),
                        "trailing_percent_mode": current_doc.get("trailing_percent_mode", True),
                        "trailing_order_type": current_doc.get("trailing_order_type", "limit"),
                    }
                    updates = strategy.model_dump()
                    updates.pop("name")
                    updates["strategy"] = preset
                    updates["custom_backup"] = backup_fields
                    await deps.db.tickers.update_one({"symbol": sym}, {"$set": updates})
                    doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if doc:
                        await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})

            elif action == "TAKE_PROFIT":
                sym = msg.get("symbol", "").upper()
                profit_doc = await deps.db.profits.find_one({"symbol": sym}, {"_id": 0})
                if profit_doc and profit_doc.get("total_pnl", 0) > 0:
                    amount = profit_doc["total_pnl"]
                    await deps.db.cash_ledger.insert_one({
                        "symbol": sym, "amount": amount,
                        "timestamp": datetime.now(timezone.utc).isoformat(), "type": "TAKE_PROFIT",
                    })
                    await deps.db.settings.update_one({"key": "cash_reserve"}, {"$inc": {"value": amount}}, upsert=True)
                    await deps.db.profits.update_one(
                        {"symbol": sym}, {"$set": {"total_pnl": 0, "updated_at": datetime.now(timezone.utc).isoformat()}}
                    )
                    ticker_doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if ticker_doc and ticker_doc.get("compound_profits", True):
                        new_bp = max(1.0, round(ticker_doc.get("base_power", 100) - amount, 2))
                        await deps.db.tickers.update_one({"symbol": sym}, {"$set": {"base_power": new_bp}})
                        updated_ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
                        if updated_ticker:
                            await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": updated_ticker})
                    profits_cursor = deps.db.profits.find({}, {"_id": 0})
                    profits_list = await profits_cursor.to_list(100)
                    profits = {p["symbol"]: p.get("total_pnl", 0) for p in profits_list}
                    cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
                    cash_total = round(cash_doc.get("value", 0), 2) if cash_doc else 0
                    await deps.ws_manager.broadcast({"type": "PROFITS_UPDATE", "profits": profits, "cash_reserve": cash_total})

    except WebSocketDisconnect:
        deps.ws_manager.disconnect(websocket)
    except Exception as e:
        deps.logger.error(f"WebSocket error: {e}")
        deps.ws_manager.disconnect(websocket)
