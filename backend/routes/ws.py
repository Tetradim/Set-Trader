"""WebSocket endpoint — initial state + real-time message handling."""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

import deps
from auth import TokenData, get_auth_disabled_user, is_auth_disabled, verify_token
from bot_snapshot import build_bot_snapshot
from default_tickers import ensure_default_tickers
from routes.runtime_state import reset_trailing_state_if_needed
from schemas import TickerConfig
from strategies import PRESET_STRATEGIES

logger = logging.getLogger(__name__)
router = APIRouter()


def extract_websocket_token(websocket: WebSocket, token: Optional[str]) -> str:
    """Read the WebSocket auth token from query params or a Bearer header."""
    if token:
        return token.strip()
    authorization = websocket.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


async def authenticate_websocket(websocket: WebSocket, token: Optional[str]) -> Optional[TokenData]:
    """Validate a WebSocket before accepting it."""
    if is_auth_disabled():
        return get_auth_disabled_user()

    provided = extract_websocket_token(websocket, token)
    if not provided:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return None
    try:
        return verify_token(provided)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return None


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, token: Optional[str] = None):
    token_data = await authenticate_websocket(websocket, token)
    if not token_data:
        return

    logger.info("WebSocket authenticated for user=%s roles=%s", token_data.username, token_data.roles)
    await deps.ws_manager.connect(websocket)
    try:
        tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
        
        # Startup owns the normal seed path; this is a safety net for direct WS use.
        if await ensure_default_tickers(deps.db, logger):
            tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
        snapshot = await build_bot_snapshot()

        await websocket.send_json({
            "type": "INITIAL_STATE",
            "tickers": snapshot["tickers"],
            "prices": snapshot["prices"],
            "price_sources": snapshot["price_sources"],
            "price_errors": snapshot["price_errors"],
            "profits": snapshot["profits"],
            "positions": snapshot["positions"],
            "trades": snapshot["trades"],
            "cash_reserve": snapshot["cash_reserve"],
            "account_balance": snapshot["account_balance"],
            "allocated": snapshot["allocated"],
            "available": snapshot["available"],
            "increment_step": snapshot["increment_step"],
            "decrement_step": snapshot["decrement_step"],
            "paused": snapshot["paused"],
            "running": snapshot["running"],
            "market_open": snapshot["market_open"],
            "simulate_24_7": snapshot["simulate_24_7"],
            "market_hours_only": snapshot["market_hours_only"],
            "live_during_market_hours": snapshot["live_during_market_hours"],
            "paper_after_hours": snapshot["paper_after_hours"],
            "replay": snapshot["replay"],
        })

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")

            if action == "ADD_TICKER":
                sym = msg.get("symbol", "").upper().strip()
                if sym:
                    from markets import detect_market_from_symbol
                    market = msg.get("market") or detect_market_from_symbol(sym)
                    existing = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if existing:
                        await deps.ws_manager.broadcast({
                            "type": "TICKER_ERROR",
                            "error": f"{sym} already exists",
                            "symbol": sym,
                        })
                        continue
                    t = TickerConfig(symbol=sym, base_power=msg.get("base_power", 100.0), market=market)
                    doc = t.model_dump()
                    try:
                        await deps.db.tickers.insert_one(doc)
                        doc.pop("_id", None)
                        await deps.ws_manager.broadcast({"type": "TICKER_ADDED", "ticker": doc})
                    except Exception as e:
                        logger.exception("Failed to add ticker over WebSocket: %s", sym)
                        await deps.ws_manager.broadcast({
                            "type": "TICKER_ERROR",
                            "error": f"Failed to add {sym}: {e}",
                            "symbol": sym,
                        })

            elif action == "DELETE_TICKER":
                sym = msg.get("symbol", "").upper()
                await deps.db.tickers.delete_one({"symbol": sym})
                deps.engine._positions.pop(sym, None)
                await deps.ws_manager.broadcast({"type": "TICKER_DELETED", "symbol": sym})

            elif action == "UPDATE_TICKER":
                sym = msg.get("symbol", "").upper()
                updates = {k: v for k, v in msg.items() if k not in ("action", "symbol")}
                logger.info(f"[UPDATE_TICKER] symbol={sym} keys={list(updates.keys())}")
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
                    result = await deps.db.tickers.update_one({"symbol": sym}, {"$set": updates})
                    await reset_trailing_state_if_needed(updates, [sym])
                    logger.info(f"[UPDATE_TICKER] result={result.modified_count} modified")
                    doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
                    if doc:
                        logger.info(f"[UPDATE_TICKER] doc allocations={doc.get('broker_allocations')}")
                        await deps.ws_manager.broadcast({"type": "TICKER_UPDATED", "ticker": doc})

            elif action == "START_BOT":
                await deps.db.tickers.update_many(
                    {},
                    {"$set": {"enabled": True, "auto_stopped": False, "auto_stop_reason": "", "buying_paused": False}},
                )
                tickers = await deps.db.tickers.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)
                deps.engine.running = True
                deps.engine.paused = False
                await deps.engine.save_state()
                await deps.ws_manager.broadcast({"type": "TICKERS_REORDERED", "tickers": tickers})
                await deps.ws_manager.broadcast({"type": "BOT_STATUS", "running": True, "paused": False})

            elif action == "STOP_BOT":
                deps.engine.running = False
                deps.engine.paused = False
                deps.engine._pending_sells.clear()
                await deps.db.tickers.update_many({}, {"$set": {"enabled": False}})
                tickers = await deps.db.tickers.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)
                await deps.engine.save_state()
                await deps.ws_manager.broadcast({"type": "TICKERS_REORDERED", "tickers": tickers})
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
                        await reset_trailing_state_if_needed(backup, [sym])
                    else:
                        updates = {"strategy": "custom"}
                        await deps.db.tickers.update_one({"symbol": sym}, {"$set": updates})
                        await reset_trailing_state_if_needed(updates, [sym])
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
                    await reset_trailing_state_if_needed(updates, [sym])
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

            elif action == "OBSERVATION":
                # Handle pattern observations from Pulse (e.g., chart patterns, signals)
                # Format: {"type": "observation", "ticker": "...", "pattern": "double_bottom", "confidence": 0.85, "broker_data": {...}}
                obs = msg.get("observation", {})
                ticker = obs.get("ticker", "").upper()
                pattern = obs.get("pattern", "")
                confidence = obs.get("confidence", 0.0)
                broker_data = obs.get("broker_data", {})
                
                if ticker and pattern:
                    # Store observation in database for scoring
                    await deps.db.observations.insert_one({
                        "ticker": ticker,
                        "pattern": pattern,
                        "confidence": confidence,
                        "broker_data": broker_data,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source": "pulse",
                    })
                    # Broadcast to all connected clients
                    await deps.ws_manager.broadcast({
                        "type": "OBSERVATION",
                        "observation": obs,
                        "stored": True,
                    })
                    logger.info(f"Observation stored: {ticker} {pattern} ({confidence:.2f})")
                else:
                    await deps.ws_manager.broadcast({
                        "type": "OBSERVATION_ERROR",
                        "error": "Missing ticker or pattern",
                    })

    except WebSocketDisconnect:
        deps.ws_manager.disconnect(websocket)
    except Exception as e:
        deps.logger.error(f"WebSocket error: {e}")
        deps.ws_manager.disconnect(websocket)
