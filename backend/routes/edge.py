"""REST endpoints for Edge/Pulse integration.

Edge calls these endpoints to:
- POST /api/edge/handoff - Structured broker-control handoffs
- POST /api/edge/tickers/{symbol}/decision - Legacy buy/sell/stop decisions
- POST /api/edge/tickers/{symbol}/trailing - Enable trailing stop
- POST /api/edge/signals/{symbol} - Receive signal context from Edge
- GET /api/edge/positions/{symbol} - Get position
- GET /api/edge/tickers - Get all tickers
- GET /api/edge/account/status - Get account and open positions
"""
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse

import deps
from bot_snapshot import build_bot_snapshot
from markets import detect_market_from_symbol
from risk_controls import risk_controls as _fallback_risk_controls
from routes.runtime_state import reset_trailing_state_if_needed
from schemas import TickerConfig
from shared import (
    edge_client,
    build_pulse_status,
    build_position_update,
    build_account_update,
)

from routes.edge_contracts import (
    DecisionRequest,
    PulseHandoffAction,
    PulseHandoffRequest,
    SignalEvalRequest,
    SignalEvalResponse,
    SignalRequest,
    SignalResponse,
    TrailingRequest,
    _check_rate_limit,
    _current_position,
    validate_api_key,
)
from routes.bot import BotControlRequest, reload_bot_state as _reload_bot_state, start_bot as _start_bot, stop_bot as _stop_bot

router = APIRouter(prefix="/edge")
_LEGACY_LIVE_EXECUTION_DECISIONS = {"buy", "sell", "stop"}

# In-memory signal cache (reset on restart)
# Key = symbol, Value = latest signal dict
_signal_cache: dict = {}


async def _broadcast_edge_created_ticker(doc: dict) -> None:
    try:
        await deps.ws_manager.broadcast({"type": "TICKER_ADDED", "ticker": doc})
        balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
        account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
        tickers = await deps.db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
        allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)
        await deps.ws_manager.broadcast(
            {
                "type": "ACCOUNT_UPDATE",
                "account_balance": account_balance,
                "allocated": allocated,
                "available": round(account_balance - allocated, 2),
            }
        )
    except Exception as exc:
        deps.logger.warning("Edge-created ticker broadcast failed for %s: %s", doc.get("symbol"), exc)


async def _create_ticker_from_edge_buy(symbol: str) -> dict:
    max_order = await deps.db.tickers.find_one(
        {},
        sort=[("sort_order", -1)],
        projection={"sort_order": 1},
    )
    next_order = (max_order.get("sort_order", 0) + 1) if max_order else 0
    ticker = TickerConfig(
        symbol=symbol,
        base_power=100.0,
        sort_order=next_order,
        market=detect_market_from_symbol(symbol),
        compound_profits=False,
    )
    doc = ticker.model_dump()
    await deps.db.tickers.insert_one(doc)
    doc.pop("_id", None)
    await _broadcast_edge_created_ticker(doc)
    return doc


def _handoff_response(
    body: PulseHandoffRequest,
    *,
    accepted: bool,
    status: str,
    reason: str,
    message: str = "",
) -> dict:
    response = {
        "accepted": accepted,
        "sent": accepted,
        "status": status,
        "reason": reason,
        "symbol": body.symbol,
        "action": body.action.value,
        "handoff_id": body.idempotency_key,
    }
    if message:
        response["message"] = message
    return response


def _pulse_trading_mode() -> str:
    mode_getter = getattr(deps.engine, "get_trading_mode", None)
    if callable(mode_getter):
        return str(mode_getter()).strip().lower()

    if bool(getattr(deps.engine, "simulate_24_7", False)) or not bool(getattr(deps.engine, "live_during_market_hours", False)):
        return "paper"
    return "live"


def _handoff_mode_mismatch(body: PulseHandoffRequest) -> dict | None:
    pulse_mode = _pulse_trading_mode()
    handoff_mode = body.mode.value
    if handoff_mode == pulse_mode:
        return None

    return _handoff_response(
        body,
        accepted=False,
        status="rejected",
        reason="mode_mismatch",
        message=f"Handoff requested {handoff_mode} mode but Pulse is currently {pulse_mode}.",
    )


def _legacy_live_decision_rejection(symbol: str, decision: str) -> dict | None:
    if decision not in _LEGACY_LIVE_EXECUTION_DECISIONS or _pulse_trading_mode() != "live":
        return None

    return {
        "status": "error",
        "symbol": symbol,
        "decision": decision,
        "reason": "legacy_live_handoff_blocked",
        "message": "Live Pulse execution requires the structured /api/edge/handoff contract.",
    }


def _finite_positive_price(value) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if math.isfinite(price) and price > 0 else None


def _risk_controls():
    controls = getattr(getattr(deps, "engine", None), "risk_controls", None)
    return controls or _fallback_risk_controls


def _pending_sells() -> dict:
    pending = getattr(deps.engine, "_pending_sells", {}) or {}
    return pending if hasattr(pending, "items") else {}


def _position_qty(position: dict) -> float:
    try:
        return float(position.get("qty", position.get("quantity", 0)) or 0)
    except (TypeError, ValueError):
        return 0.0


def _position_entry(position: dict) -> float:
    try:
        return float(position.get("avg_entry", position.get("entry_price", 0)) or 0)
    except (TypeError, ValueError):
        return 0.0


async def _position_rows() -> list[dict]:
    rows = []
    prices = getattr(deps.engine, "_prices", {}) or {}
    for sym, pos in getattr(deps.engine, "_positions", {}).items():
        qty = _position_qty(pos)
        if qty <= 0:
            continue
        avg_entry = _position_entry(pos)
        current_price = _finite_positive_price(prices.get(sym)) or _finite_positive_price(pos.get("current_price"))
        if current_price is None:
            current_price = _finite_positive_price(await deps.price_service.get_price(sym)) or avg_entry
        market_value = round(qty * current_price, 2)
        rows.append(
            {
                "symbol": sym,
                "quantity": qty,
                "avg_entry": avg_entry,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": round((current_price - avg_entry) * qty, 2),
            }
        )
    return rows


def _order_query(status_value: str | None = None, symbol: str | None = None) -> dict:
    query = {}
    if status_value:
        query["status"] = status_value
    if symbol:
        query["symbol"] = symbol.upper()
    return query


def _as_plain_payload(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_as_plain_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _as_plain_payload(item) for key, item in value.items()}
    return value


async def _handoff_price(symbol: str, body: PulseHandoffRequest) -> float:
    metadata = body.metadata if isinstance(body.metadata, dict) else {}
    metadata_price_seen = False
    for key in ("price", "current_price", "last_price"):
        value = metadata.get(key)
        if value is not None:
            metadata_price_seen = True
            price = _finite_positive_price(value)
            if price is not None:
                return price
    if metadata_price_seen:
        return 0.0
    return _finite_positive_price(await deps.price_service.get_price(symbol)) or 0.0


async def _set_trailing(symbol: str, trailing_percent: float, *, opening_bell: bool = False) -> None:
    updates = {
        "trailing_enabled": True,
        "trailing_percent": trailing_percent,
    }
    if opening_bell:
        updates.update(
            {
                "opening_bell_enabled": True,
                "opening_bell_trail_value": trailing_percent,
                "opening_bell_trail_is_percent": True,
            }
        )
    await deps.db.tickers.update_one({"symbol": symbol}, {"$set": updates})
    await reset_trailing_state_if_needed(updates, [symbol])


async def _set_global_trailing(trailing_percent: float, *, opening_bell: bool = False) -> None:
    updates = {
        "trailing_enabled": True,
        "trailing_percent": trailing_percent,
    }
    if opening_bell:
        updates.update(
            {
                "opening_bell_enabled": True,
                "opening_bell_trail_value": trailing_percent,
                "opening_bell_trail_is_percent": True,
            }
        )
    await deps.db.tickers.update_many({}, {"$set": updates})
    await reset_trailing_state_if_needed(updates)


async def _set_stop_buying(symbol: str, reason: str) -> None:
    position = _current_position(symbol)
    position_qty = position.get("qty", 0) if position else 0
    updates = {
        "buying_paused": True,
        "auto_stop_reason": reason or "edge_stop_buying",
    }
    if position_qty > 0:
        updates["enabled"] = True
    else:
        updates["enabled"] = False
    await deps.db.tickers.update_one(
        {"symbol": symbol},
        {"$set": updates},
    )


async def _set_dca_plan(symbol: str, body: PulseHandoffRequest) -> None:
    plan = body.dca.model_dump(exclude_none=True) if body.dca else {}
    steps = int(plan.get("steps", 1))
    allocation_pct = float(plan.get("allocation_pct", 100.0 / max(steps, 1)))
    buy_legs = [
        {"alloc_pct": allocation_pct, "offset": 0.0, "is_percent": True}
        for _ in range(max(steps, 1))
    ]
    await deps.db.tickers.update_one(
        {"symbol": symbol},
        {"$set": {"partial_fills_enabled": True, "buy_legs": buy_legs, "dca_plan": plan}},
    )


async def _process_global_handoff(body: PulseHandoffRequest) -> dict:
    action = body.action

    try:
        if action in {
            PulseHandoffAction.TRAILING_STOP,
            PulseHandoffAction.TIGHTEN_TRAILING_STOP,
        }:
            await _set_global_trailing(float(body.trailing_percent))

        elif action == PulseHandoffAction.OPENING_TRAILING_STOP:
            await _set_global_trailing(float(body.trailing_percent), opening_bell=True)

        elif action in {PulseHandoffAction.STOP_BUYING, PulseHandoffAction.STOP_ALL}:
            await deps.db.tickers.update_many(
                {"enabled": True},
                {"$set": {"enabled": False, "auto_stop_reason": body.reason or "edge_global_stop"}},
            )
            if action == PulseHandoffAction.STOP_ALL:
                deps.engine.paused = True

        elif action == PulseHandoffAction.EMERGENCY_EXIT:
            open_positions = [
                (symbol, position)
                for symbol, position in list(getattr(deps.engine, "_positions", {}).items())
                if float(position.get("qty", 0) or 0) > 0
            ]
            for symbol, _position in open_positions:
                await deps.engine.execute_sell(symbol, None)
            await deps.db.tickers.update_many(
                {"enabled": True},
                {"$set": {"enabled": False, "auto_stop_reason": body.reason or "edge_emergency_exit"}},
            )
            deps.engine.paused = True

        else:
            return _handoff_response(
                body,
                accepted=False,
                status="rejected",
                reason="global_action_not_supported",
                message=f"{action.value} is not supported for GLOBAL handoffs",
            )

    except Exception as exc:
        return _handoff_response(
            body,
            accepted=False,
            status="failed",
            reason=exc.__class__.__name__,
            message=str(exc),
        )

    return _handoff_response(
        body,
        accepted=True,
        status="accepted",
        reason="pulse_accepted",
        message=f"{action.value} accepted for GLOBAL",
    )


# --- Endpoints ---


@router.get("/status", dependencies=[Depends(validate_api_key)])
async def get_edge_status():
    """Return Edge communication health for setup and beta diagnostics."""
    expected = await deps.db.settings.find_one({"key": "edge_api_key"}, {"_id": 0})
    expected_key = expected.get("value", "") if expected else ""
    return {
        "api_key_configured": bool(expected_key),
        "signals_cached": len(_signal_cache),
        "max_retry_attempts": edge_client.max_retry_attempts,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mongo": edge_client.status_snapshot(),
    }


@router.post("/bot/start", dependencies=[Depends(validate_api_key)])
async def edge_start_bot(body: BotControlRequest | None = None):
    """Start Pulse through the Edge service-to-service API key boundary."""
    return await _start_bot(body)


@router.post("/bot/stop", dependencies=[Depends(validate_api_key)])
async def edge_stop_bot(body: BotControlRequest | None = None):
    """Stop Pulse through the Edge service-to-service API key boundary."""
    return await _stop_bot(body)


@router.post("/bot/reload-state", dependencies=[Depends(validate_api_key)])
async def edge_reload_bot_state():
    """Reload Pulse runtime state through the Edge service-to-service API key boundary."""
    return await _reload_bot_state()


@router.get("/brokers/status", dependencies=[Depends(validate_api_key)])
async def edge_broker_status():
    """Return broker connection status through the Edge service-to-service API key boundary."""
    return deps.broker_mgr.get_status()


@router.post("/brokers/reconnect", dependencies=[Depends(validate_api_key)])
async def edge_reconnect_brokers():
    """Reconnect configured brokers through the Edge service-to-service API key boundary."""
    results = await deps.broker_mgr.reconnect_all()
    return {"results": results}


@router.post("/brokers/{broker_id}/disconnect", dependencies=[Depends(validate_api_key)])
async def edge_disconnect_broker(broker_id: str):
    """Disconnect one broker through the Edge service-to-service API key boundary."""
    await deps.broker_mgr.disconnect_broker(broker_id)
    return {"status": "disconnected", "broker_id": broker_id}


@router.get("/brokers/{broker_id}/positions", dependencies=[Depends(validate_api_key)])
async def edge_get_broker_positions(broker_id: str):
    """Return broker-held positions through the Edge service-to-service API key boundary."""
    return await deps.broker_mgr.reconcile_positions(broker_id)


@router.post("/brokers/{broker_id}/sync-positions", dependencies=[Depends(validate_api_key)])
async def edge_sync_broker_positions(broker_id: str):
    """Sync Pulse runtime positions from broker-held positions."""
    return await deps.engine.sync_positions_from_broker(broker_id)


@router.get("/bot/status", dependencies=[Depends(validate_api_key)])
async def edge_bot_status():
    """Return bot runtime status through the Edge service-to-service API key boundary."""
    positions = await _position_rows()
    return {
        "running": bool(deps.engine.running),
        "paused": bool(deps.engine.paused),
        "market_open": bool(deps.engine.is_market_open()),
        "trading_mode": _pulse_trading_mode(),
        "simulate_24_7": bool(deps.engine.simulate_24_7),
        "live_during_market_hours": bool(deps.engine.live_during_market_hours),
        "paper_after_hours": bool(getattr(deps.engine, "paper_after_hours", False)),
        "open_positions": len(positions),
        "pending_sells": len(_pending_sells()),
    }


@router.get("/bot/snapshot", dependencies=[Depends(validate_api_key)])
async def edge_bot_snapshot():
    """Return the Pulse dashboard snapshot through the Edge service-to-service API key boundary."""
    tickers = await deps.db.tickers.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)
    trades = await deps.db.trades.find({}, {"_id": 0}).sort("timestamp", -1).to_list(50)
    profits_collection = getattr(deps.db, "profits", None)
    profits = await profits_collection.find({}, {"_id": 0}).to_list(100) if profits_collection is not None else []
    positions = await _position_rows()
    balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
    cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0
    allocated = round(sum(ticker.get("base_power", 0) for ticker in tickers), 2)
    prices = getattr(deps.engine, "_prices", {}) or {}
    return {
        "tickers": tickers,
        "prices": prices,
        "price_sources": getattr(deps.engine, "_price_sources", {}),
        "price_errors": getattr(deps.engine, "_price_errors", {}),
        "positions": positions,
        "pending_sells": await edge_get_pending_sells(),
        "profits": profits,
        "trades": trades,
        "cash_reserve": cash_reserve,
        "account_balance": account_balance,
        "allocated": allocated,
        "available": round(account_balance - allocated, 2),
        "paused": deps.engine.paused,
        "running": deps.engine.running,
        "market_open": deps.engine.is_market_open(),
        "trading_mode": _pulse_trading_mode(),
        "simulate_24_7": deps.engine.simulate_24_7,
        "market_hours_only": bool(getattr(deps.engine, "market_hours_only", False)),
        "live_during_market_hours": deps.engine.live_during_market_hours,
        "paper_after_hours": bool(getattr(deps.engine, "paper_after_hours", False)),
        "replay": getattr(deps.engine, "replay_status", {}),
    }


@router.get("/trades", dependencies=[Depends(validate_api_key)])
async def edge_get_trades(limit: int = Query(50, ge=1, le=200)):
    """Return recent trade records through the Edge service-to-service API key boundary."""
    return await deps.db.trades.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)


@router.get("/positions", dependencies=[Depends(validate_api_key)])
async def edge_get_positions():
    """Return open Pulse positions through the Edge service-to-service API key boundary."""
    return await _position_rows()


@router.get("/positions/pending-sells", dependencies=[Depends(validate_api_key)])
async def edge_get_pending_sells():
    """Return pending limit sells through the Edge service-to-service API key boundary."""
    return {
        sym: {"limit_price": order["limit_price"], "quantity": order["qty"], "entry": order["entry"]}
        for sym, order in _pending_sells().items()
    }


@router.get("/risk/status", dependencies=[Depends(validate_api_key)])
async def edge_risk_status():
    """Return trading permission status through the Edge service-to-service API key boundary."""
    is_allowed, restriction, message = _risk_controls().isTradingAllowed()
    return {
        "trading_allowed": is_allowed,
        "restriction": restriction.value if restriction else "none",
        "message": message,
        "limits": _risk_controls().get_all_limits(),
        "kill_switches": _risk_controls().get_all_kill_switches(),
    }


@router.get("/risk/limits", dependencies=[Depends(validate_api_key)])
async def edge_risk_limits():
    """Return configured risk limits through the Edge service-to-service API key boundary."""
    return {"limits": _risk_controls().get_all_limits()}


@router.get("/orders", dependencies=[Depends(validate_api_key)])
async def edge_get_orders(
    limit: int = Query(100, ge=1, le=1000),
    status_value: str | None = Query(None, alias="status"),
    symbol: str | None = None,
):
    """Return broker order records through the Edge service-to-service API key boundary."""
    return await deps.db.orders.find(_order_query(status_value, symbol), {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.get("/orders/stats", dependencies=[Depends(validate_api_key)])
async def edge_get_order_stats():
    """Return broker order statistics through the Edge service-to-service API key boundary."""
    orders = await deps.db.orders.find({}, {"_id": 0}).to_list(5000)
    total = len(orders)
    filled = sum(1 for order in orders if order.get("status") == "filled")
    rejected = sum(1 for order in orders if order.get("status") == "rejected")
    pending = sum(1 for order in orders if order.get("status") == "pending")
    slippage_values = [float(order.get("slippage_bps", 0)) for order in orders if order.get("slippage_bps") is not None]
    lag_values = [float(order.get("execution_lag_ms", 0)) for order in orders if order.get("execution_lag_ms") is not None]
    fill_rate = (filled / total * 100) if total else 0
    return {
        "total_orders": total,
        "filled_orders": filled,
        "rejected_orders": rejected,
        "pending_orders": pending,
        "avg_slippage": round(sum(slippage_values) / len(slippage_values), 2) if slippage_values else 0,
        "avg_execution_lag_ms": round(sum(lag_values) / len(lag_values), 0) if lag_values else 0,
        "fill_rate": round(fill_rate, 1),
    }


@router.get("/portfolio/stats", dependencies=[Depends(validate_api_key)])
async def edge_portfolio_stats(period: str = Query("month", pattern="^(today|week|month|all)$")):
    """Return portfolio performance statistics through the Edge service-to-service API key boundary."""
    now = datetime.now(timezone.utc)
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    else:
        start_date = datetime(2000, 1, 1, tzinfo=timezone.utc)

    trades = await deps.db.trades.find({"timestamp": {"$gte": start_date.isoformat()}}, {"_id": 0}).to_list(10000)
    wins = [trade for trade in trades if trade.get("pnl", 0) > 0]
    losses = [trade for trade in trades if trade.get("pnl", 0) < 0]
    total_wins = sum(trade.get("pnl", 0) for trade in wins)
    total_losses = sum(trade.get("pnl", 0) for trade in losses)
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = total_wins / len(wins) if wins else 0
    avg_loss = total_losses / len(losses) if losses else 0
    profit_factor = abs(total_wins / total_losses) if total_losses != 0 else 0

    account_balance = 100000
    settings = await deps.db.settings.find_one({"key": "account_balance"})
    if settings and settings.get("value"):
        account_balance = settings.get("value", account_balance)

    total_pnl = sum(trade.get("pnl", 0) for trade in trades)
    total_pnl_pct = (total_pnl / account_balance * 100) if account_balance > 0 else 0
    daily_pnl = defaultdict(float)
    for trade in trades:
        ts = str(trade.get("timestamp", ""))
        if ts:
            daily_pnl[ts.split("T")[0]] += trade.get("pnl", 0)

    daily_returns = [(pnl / account_balance) if account_balance > 0 else 0 for pnl in daily_pnl.values()]
    sharpe_ratio = 0
    if len(daily_returns) > 1 and statistics.pstdev(daily_returns) > 0:
        sharpe_ratio = (statistics.mean(daily_returns) / statistics.pstdev(daily_returns)) * math.sqrt(252)

    equity = account_balance
    peak = account_balance
    max_drawdown = 0.0
    for date in sorted(daily_pnl):
        equity += daily_pnl[date]
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, ((equity - peak) / peak) * 100)

    return {
        "stats": {
            "totalValue": 0,
            "totalPnl": total_pnl,
            "totalPnLPct": total_pnl_pct,
            "winRate": win_rate,
            "avgWin": avg_win,
            "avgLoss": avg_loss,
            "profitFactor": profit_factor,
            "maxDrawdown": round(max_drawdown, 2),
            "sharpeRatio": round(sharpe_ratio, 2),
        }
    }


@router.get("/strategies/registry", dependencies=[Depends(validate_api_key)])
async def edge_strategy_registry():
    """Return strategy registry data through the Edge service-to-service API key boundary."""
    from routes.strategies import list_strategy_registry

    return await list_strategy_registry()


@router.get("/strategies/presets", dependencies=[Depends(validate_api_key)])
async def edge_strategy_presets():
    """Return strategy presets through the Edge service-to-service API key boundary."""
    from routes.strategies import list_presets

    return await list_presets()


@router.get("/markets", dependencies=[Depends(validate_api_key)])
async def edge_markets():
    """Return Pulse market metadata through the Edge service-to-service API key boundary."""
    from routes.markets import list_markets

    return await list_markets()


@router.get("/fx-rates", dependencies=[Depends(validate_api_key)])
async def edge_fx_rates():
    """Return FX rates through the Edge service-to-service API key boundary."""
    from routes.markets import get_fx_rates

    return await get_fx_rates()


@router.get("/replay/status", dependencies=[Depends(validate_api_key)])
async def edge_replay_status():
    """Return replay status through the Edge service-to-service API key boundary."""
    from routes.replay import get_replay_status

    return await get_replay_status()


@router.get("/replay/sessions", dependencies=[Depends(validate_api_key)])
async def edge_replay_sessions(
    limit: int = Query(50, ge=1, le=250),
    include_empty: bool = False,
):
    """Return replay sessions through the Edge service-to-service API key boundary."""
    from routes.replay import list_replay_sessions

    return await list_replay_sessions(limit=limit, include_empty=include_empty)


@router.get("/rate-limits", dependencies=[Depends(validate_api_key)])
async def edge_rate_limits():
    """Return broker resilience status through the Edge service-to-service API key boundary."""
    from routes.system import get_rate_limit_status

    return await get_rate_limit_status()


@router.get("/audit-logs", dependencies=[Depends(validate_api_key)])
async def edge_audit_logs(
    event_type: list[str] | None = Query(None, description="Filter by one or more event types"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    broker_id: str | None = Query(None, description="Filter by broker"),
    success: bool | None = Query(None, description="Filter by success status"),
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
):
    """Return audit logs through the Edge service-to-service API key boundary."""
    from routes.system import get_audit_logs

    return await get_audit_logs(
        event_type=event_type,
        symbol=symbol,
        broker_id=broker_id,
        success=success,
        limit=limit,
        skip=skip,
    )


@router.get("/settings", dependencies=[Depends(validate_api_key)])
async def edge_settings():
    """Return runtime settings through Edge auth, with stored notification secrets redacted."""
    from routes.settings import get_settings

    settings = await get_settings()
    telegram = dict(settings.get("telegram") or {})
    bot_token = telegram.pop("bot_token", "") or ""
    telegram["bot_token_configured"] = bool(bot_token)
    settings["telegram"] = telegram
    return settings


@router.get("/reconciliation/summary", dependencies=[Depends(validate_api_key)])
async def edge_reconciliation_summary():
    """Return reconciliation summary through the Edge service-to-service API key boundary."""
    from routes.reconciliation import get_summary

    return _as_plain_payload(await get_summary())


@router.get("/analytics/portfolio", dependencies=[Depends(validate_api_key)])
async def edge_analytics_portfolio(timeframe: str = Query("1d")):
    """Return portfolio analytics through the Edge service-to-service API key boundary."""
    from routes.analytics import get_portfolio_metrics

    return _as_plain_payload(await get_portfolio_metrics(timeframe=timeframe))


@router.get("/ops/services", dependencies=[Depends(validate_api_key)])
async def edge_ops_services():
    """Return service health through the Edge service-to-service API key boundary."""
    from routes.ops import get_services

    return _as_plain_payload(await get_services())


@router.get("/slo/summary", dependencies=[Depends(validate_api_key)])
async def edge_slo_summary():
    """Return SLO summary through the Edge service-to-service API key boundary."""
    from routes.slo import get_slo_summary

    return await get_slo_summary()


@router.post("/handoff", dependencies=[Depends(validate_api_key)])
async def post_handoff(body: PulseHandoffRequest):
    """Process a structured autonomous handoff from Sentinel Edge."""
    mode_rejection = _handoff_mode_mismatch(body)
    if mode_rejection is not None:
        return mode_rejection

    sym = body.symbol
    action = body.action
    if sym == "GLOBAL":
        return await _process_global_handoff(body)

    ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    if not ticker:
        if action == PulseHandoffAction.BUY:
            ticker = await _create_ticker_from_edge_buy(sym)
        else:
            return _handoff_response(
                body,
                accepted=False,
                status="rejected",
                reason="ticker_not_found",
                message=f"{sym} is not configured in Pulse",
            )

    if not ticker:
        return _handoff_response(
            body,
            accepted=False,
            status="rejected",
            reason="ticker_not_found",
            message=f"{sym} is not configured in Pulse",
        )

    position = _current_position(sym)
    position_qty = float(position.get("qty", 0) or 0)

    try:
        if action == PulseHandoffAction.BUY:
            if position_qty > 0:
                return _handoff_response(
                    body,
                    accepted=False,
                    status="rejected",
                    reason="already_have_position",
                    message=f"{sym} already has an open position",
                )
            price = await _handoff_price(sym, body)
            if price <= 0:
                return _handoff_response(body, accepted=False, status="rejected", reason="price_unavailable")
            await deps.engine.execute_buy(sym, price)

        elif action in {PulseHandoffAction.SELL, PulseHandoffAction.EMERGENCY_EXIT, PulseHandoffAction.REGULAR_STOP}:
            if position_qty <= 0:
                return _handoff_response(
                    body,
                    accepted=False,
                    status="rejected",
                    reason="no_position",
                    message=f"{sym} has no open position",
            )
            price = await _handoff_price(sym, body)
            if price <= 0:
                return _handoff_response(body, accepted=False, status="rejected", reason="price_unavailable")
            await deps.engine.execute_sell(sym, price)

        elif action == PulseHandoffAction.STOP_BUYING:
            await _set_stop_buying(sym, body.reason)

        elif action == PulseHandoffAction.STOP_ALL:
            await deps.db.tickers.update_many(
                {"enabled": True},
                {"$set": {"enabled": False, "auto_stop_reason": body.reason or "edge_stop_all"}},
            )
            deps.engine.paused = True

        elif action == PulseHandoffAction.TRAILING_STOP:
            await _set_trailing(sym, float(body.trailing_percent))

        elif action == PulseHandoffAction.OPENING_TRAILING_STOP:
            await _set_trailing(sym, float(body.trailing_percent), opening_bell=True)

        elif action == PulseHandoffAction.TIGHTEN_TRAILING_STOP:
            await _set_trailing(sym, float(body.trailing_percent))

        elif action == PulseHandoffAction.TIGHTEN_STOP:
            metadata = body.metadata if isinstance(body.metadata, dict) else {}
            updates = {"auto_stop_reason": body.reason or "edge_tighten_stop"}
            if metadata.get("stop_offset") is not None:
                updates["stop_offset"] = float(metadata["stop_offset"])
            await deps.db.tickers.update_one({"symbol": sym}, {"$set": updates})

        elif action == PulseHandoffAction.DCA:
            await _set_dca_plan(sym, body)

    except Exception as exc:
        return _handoff_response(
            body,
            accepted=False,
            status="failed",
            reason=exc.__class__.__name__,
            message=str(exc),
        )

    return _handoff_response(
        body,
        accepted=True,
        status="accepted",
        reason="pulse_accepted",
        message=f"{action.value} accepted for {sym}",
    )


@router.post("/tickers/{symbol}/decision", dependencies=[Depends(validate_api_key)])
async def post_decision(symbol: str, body: DecisionRequest):
    """Process decision from Edge.
    
    Edge calls this to control Pulse behavior:
    - buy: Open position
    - sell: Close position
    - stop: Emergency stop
    - enable_trailing_stop: Activate trailing stop
    - stop_buying: Disable new buys
    - emergency_stop: Halt all trading
    
    Returns: {"status": "ok", "symbol": "...", "decision": "..."}
    """
    sym = symbol.upper()
    decision = body.decision.lower()
    legacy_live_rejection = _legacy_live_decision_rejection(sym, decision)
    if legacy_live_rejection is not None:
        return legacy_live_rejection
    
    # Get ticker config
    ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    if not ticker:
        raise HTTPException(404, f"{sym} not found")
    
    position = _current_position(sym)
    position_qty = position.get("qty", 0)
    
    trading_mode = deps.engine.get_trading_mode()
    market_open = deps.engine.is_market_open()
    
    # Process decision
    result = {"status": "ok", "symbol": sym, "decision": decision}
    
    if decision == "buy":
        if position_qty > 0:
            result["decision"] = "hold"
            result["message"] = "already have position"
        elif body.price:
            try:
                await deps.engine.execute_buy(sym, body.price)
                result["message"] = "buy order executed"
            except Exception as e:
                result["status"] = "error"
                result["message"] = str(e)
        else:
            result["message"] = "price required for buy"
    
    elif decision == "sell":
        if position_qty == 0:
            result["decision"] = "hold"
            result["message"] = "no position to sell"
        else:
            try:
                await deps.engine.execute_sell(sym, body.price)
                result["message"] = "sell order executed"
            except Exception as e:
                result["status"] = "error"
                result["message"] = str(e)
    
    elif decision == "stop":
        if position_qty == 0:
            result["message"] = "no position to stop"
        else:
            try:
                await deps.engine.execute_sell(sym, None)  # Market order
                result["message"] = "position stopped"
            except Exception as e:
                result["status"] = "error"
                result["message"] = str(e)
    
    elif decision == "enable_trailing_stop":
        if body.trailing_percent:
            await deps.db.tickers.update_one(
                {"symbol": sym},
                {"$set": {"trailing_enabled": True, "trailing_percent": body.trailing_percent}},
            )
            await reset_trailing_state_if_needed(
                {"trailing_enabled": True, "trailing_percent": body.trailing_percent},
                [sym],
            )
            result["message"] = f"trailing stop enabled: {body.trailing_percent}%"
        else:
            result["message"] = "trailing_percent required"
    
    elif decision == "stop_buying":
        await _set_stop_buying(sym, "stop_buying")
        result["message"] = f"buying stopped for {sym}"
    
    elif decision == "emergency_stop":
        # Stop all tickers
        await deps.db.tickers.update_many(
            {"enabled": True},
            {"$set": {"enabled": False, "auto_stop_reason": "emergency_stop"}},
        )
        deps.engine.paused = True
        result["message"] = "all trading halted"
    
    else:
        result["message"] = f"unknown decision: {decision}"
    
    # Send position update to Edge if enabled. Refresh after the decision so Edge
    # gets the post-execution position rather than the stale pre-decision state.
    if edge_client.is_enabled and edge_client.is_connected:
        try:
            position = _current_position(sym)
            position_qty = position.get("qty", 0)
            current_price = await deps.price_service.get_price(sym)
            pos_update = build_position_update(
                symbol=sym,
                quantity=position_qty,
                avg_entry=position.get("avg_entry", 0),
                current_price=current_price,
                trading_mode=trading_mode,
            )
            result["edge_update_sent"] = await edge_client.send_position_update(pos_update)
        except Exception as e:
            result["edge_update_sent"] = False
            result["edge_update_error"] = str(e)
    
    return result


@router.post("/tickers/{symbol}/trailing", dependencies=[Depends(validate_api_key)])
async def enable_trailing(symbol: str, body: TrailingRequest):
    """Enable trailing stop for a symbol."""
    sym = symbol.upper()
    
    ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    if not ticker:
        raise HTTPException(404, f"{sym} not found")
    
    await deps.db.tickers.update_one(
        {"symbol": sym},
        {"$set": {"trailing_enabled": True, "trailing_percent": body.trailing_percent}},
    )
    await reset_trailing_state_if_needed(
        {"trailing_enabled": True, "trailing_percent": body.trailing_percent},
        [sym],
    )
    
    return {"status": "ok", "symbol": sym, "trailing_enabled": True, "trailing_percent": body.trailing_percent}


@router.post("/signals/{symbol}", dependencies=[Depends(validate_api_key)])
async def submit_signal(symbol: str, body: SignalRequest) -> SignalResponse:
    """Receive signals from Edge and update metrics cache.
    
    Edge sends signals here, we:
    1. Process action if provided (legacy buy/sell/stop)
    2. Update signal cache for Prometheus metrics
    
    Edge calls: POST /api/signals/{symbol} with JSON:
    {
        "action": "signal",
        "rsi": 65,
        "signal_type": "bullish",
        "orb_high": 150.25,
        "orb_low": 149.50,
        "pattern": "hs",
        "volatility": 0.25,
        "volume": 1500000
    }
    """
    sym = symbol.upper()
    
    # Legacy action handling - convert to decision
    if body.action.lower() not in ("signal", "hold"):
        decision_map = {
            "buy": "buy",
            "sell": "sell",
            "stop": "stop",
            "enable_trailing_stop": "enable_trailing_stop",
            "trailing": "enable_trailing_stop",
            "stop_buying": "stop_buying",
            "emergency_stop": "emergency_stop",
        }
        decision_body = DecisionRequest(
            symbol=sym,
            decision=decision_map.get(body.action.lower(), "hold"),
            price=body.price,
            trailing_percent=body.trailing_percent,
            confidence=body.confidence,
        )
        return await post_decision(symbol, decision_body)
    
    # Update signal cache for Prometheus metrics
    sig_data = {
        "rsi": body.rsi or 0,
        "direction": body.signal_type or "neutral",
        "orb_breakout": body.confidence >= 0.8 if body.confidence else False,
        "orb_direction": 1 if body.signal_type == "bullish" else (-1 if body.signal_type == "bearish" else 0),
        "orb_high": body.orb_high or 0,
        "orb_low": body.orb_low or 0,
        "volatility_24h": body.volatility or 0,
        "pattern_hs": body.pattern == "hs",
        "pattern_dtb": body.pattern == "dtb",
        "volume": body.volume or 0,
    }
    _signal_cache[sym] = sig_data
    
    return SignalResponse(status="ok", symbol=sym, action="signal", message="signal cached")


@router.get("/positions/{symbol}", dependencies=[Depends(validate_api_key)])
async def get_position(symbol: str):
    """Get position for a symbol.
    
    Returns position matching what Edge expects:
    - has_position, pnl, pnl_pct, trailing_enabled, entry_price, drawdown_pct
    """
    sym = symbol.upper()
    
    position = _current_position(sym)
    qty = position.get("qty", 0)
    avg_entry = position.get("avg_entry", 0)
    
    ticker = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
    trailing_enabled = ticker.get("trailing_enabled", False) if ticker else False
    trailing_percent = ticker.get("trailing_percent", 2.0) if ticker else 2.0
    
    # Get current price
    current_price = await deps.price_service.get_price(sym)
    
    # Calculate P&L
    pnl = 0.0
    pnl_pct = 0.0
    drawdown_pct = 0.0
    
    if qty > 0 and current_price > 0:
        market_value = qty * current_price
        cost_basis = qty * avg_entry
        pnl = round(market_value - cost_basis, 2)
        
        if cost_basis > 0:
            pnl_pct = round((pnl / cost_basis) * 100, 2)
            # Estimate drawdown
            high = position.get("high", current_price)
            if high > 0:
                drawdown_pct = round(((high - current_price) / high) * 100, 2)
    
    return {
        "symbol": sym,
        "has_position": qty > 0,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "trailing_enabled": trailing_enabled,
        "trailing_percent": trailing_percent if trailing_enabled else None,
        "entry_price": avg_entry,
        "drawdown_pct": drawdown_pct,
        "quantity": qty,
        "current_price": current_price,
    }


@router.get("/account/status", dependencies=[Depends(validate_api_key)])
async def get_account_status():
    """Get account status.
    
    Edge calls this to get account metrics and positions.
    
    Returns:
        Account status with balances and positions.
    """
    # Get account balances
    balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
    
    cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0
    
    # Get allocated capital
    tickers = await deps.db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
    allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)
    available = round(account_balance - allocated, 2)
    
    # Get positions
    positions = []
    total_unrealized_pnl = 0.0
    
    for sym, position in deps.engine._positions.items():
        if position.get("qty", 0) <= 0:
            continue
        
        current_price = await deps.price_service.get_price(sym)
        qty = position.get("qty", 0)
        avg_entry = position.get("avg_entry", 0)
        
        market_value = round(qty * current_price, 2)
        cost_basis = round(qty * avg_entry, 2)
        unrealized_pnl = round(market_value - cost_basis, 2)
        total_unrealized_pnl += unrealized_pnl
        
        positions.append({
            "symbol": sym,
            "quantity": qty,
            "avg_entry": avg_entry,
            "current_price": current_price,
            "market_value": market_value,
            "unrealized_pnl": unrealized_pnl,
        })
    
    # Get total realized P&L
    profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
    total_realized_pnl = round(sum(p.get("total_pnl", 0) for p in profits_list), 2)
    
    trading_mode = deps.engine.get_trading_mode()
    
    return {
        "account_balance": account_balance,
        "allocated": allocated,
        "available": available,
        "cash_reserve": cash_reserve,
        "total_realized_pnl": total_realized_pnl,
        "total_unrealized_pnl": total_unrealized_pnl,
        "open_positions": len(positions),
        "positions": positions,
        "trading_mode": trading_mode,
    }


@router.get("/tickers", dependencies=[Depends(validate_api_key)])
async def get_tickers():
    """Get all configured tickers.
    
    Edge calls this to sync tickers with Pulse.
    """
    tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
    return tickers


@router.post("/signals/evaluate", dependencies=[Depends(validate_api_key)])
async def evaluate_signal(body: SignalEvalRequest):
    """Evaluate trading signal using Edge-style scoring.
    
    6 Scoring Layers:
    1. ORB breakout analysis
    2. Volume confirmation
    3. Volume anomaly (z-score)
    4. Price momentum
    5. Volatility adjustment
    6. Pattern observation (from Pulse)
    """
    sym = body.symbol.upper()
    
    # Update volume history
    if body.volume > 0:
        deps.price_service.update_volume(sym, body.volume)
    
    # Get latest observation if not provided (query from database)
    observation = body.observation
    if not observation:
        from shared.observation_service import observation_service
        observation_service.set_db(deps.db)
        obs_doc = await observation_service.get_latest_observation(sym)
        if obs_doc:
            observation = {
                "pattern": obs_doc.get("pattern"),
                "confidence": obs_doc.get("confidence", 0.0),
                "direction": obs_doc.get("direction", "neutral"),
            }
    
    # Calculate signal
    direction, strength = deps.price_service.get_signal_strength(
        sym,
        body.price,
        body.orb_high,
        body.orb_low,
        body.volume,
        body.atr,
        body.price_change_pct,
        observation=observation,
    )
    
    volume_ratio = deps.price_service.get_volume_ratio(sym, body.volume)
    volume_zscore = deps.price_service.get_volume_zscore(sym, body.volume)
    
    return SignalEvalResponse(
        symbol=sym,
        direction=direction,
        strength=strength,
        volume_ratio=volume_ratio,
        volume_zscore=volume_zscore,
        observation_applied=observation is not None,
    )


# --- Prometheus metrics for Edge integration ---
@router.get("/metrics", response_class=PlainTextResponse, dependencies=[Depends(validate_api_key)])
async def edge_prometheus_metrics():
    """Expose Edge signals as Prometheus metrics.
    
    Prometheus scrapes this endpoint to get:
    - sentinel_rsi{...}
    - sentinel_orb_*
    - sentinel_volatility_*
    - sentinel_pattern_*
    
    These trigger alerts in sentinel_edge.yml rules.
    """
    import time
    
    lines = []
    timestamp = int(time.time())
    
    # RSI metrics
    lines.append("# HELP sentinel_rsi Relative Strength Index (0-100)")
    lines.append("# TYPE sentinel_rsi gauge")
    for sym, sig in _signal_cache.items():
        rsi = sig.get("rsi", 0)
        direction = sig.get("direction", "neutral")
        lines.append(f'sentinel_rsi{{symbol="{sym}",direction="{direction}"}} {rsi}')
    
    # ORB metrics
    lines.append("# HELP sentinel_orb_breakout Opening Range Breakout indicator")
    lines.append("# TYPE sentinel_orb_breakout gauge")
    for sym, sig in _signal_cache.items():
        breakout = 1 if sig.get("orb_breakout", False) else 0
        orb_direction = sig.get("orb_direction", 0)
        orb_high = sig.get("orb_high", 0)
        orb_low = sig.get("orb_low", 0)
        lines.append(f'sentinel_orb_breakout{{symbol="{sym}",direction="{orb_direction}"}} {breakout}')
        if orb_high or orb_low:
            lines.append(f'sentinel_orb_high{{symbol="{sym}"}} {orb_high}')
            lines.append(f'sentinel_orb_low{{symbol="{sym}"}} {orb_low}')
    
    # Volatility metrics
    lines.append("# HELP sentinel_volatility_24h 24-hour volatility")
    lines.append("# TYPE sentinel_volatility_24h gauge")
    lines.append("# HELP sentinel_volatility_10d_avg 10-day average volatility")
    lines.append("# TYPE sentinel_volatility_10d_avg gauge")
    for sym, sig in _signal_cache.items():
        vol_24h = sig.get("volatility_24h", 0)
        vol_10d = sig.get("volatility_10d_avg", 0)
        lines.append(f'sentinel_volatility_24h{{symbol="{sym}"}} {vol_24h}')
        lines.append(f'sentinel_volatility_10d_avg{{symbol="{sym}"}} {vol_10d}')
    
    # Pattern metrics
    lines.append("# HELP sentinel_pattern_head_shoulders Head & Shoulders pattern")
    lines.append("# TYPE sentinel_pattern_head_shoulders gauge")
    lines.append("# HELP sentinel_pattern_double_top_bottom Double Top/Bottom pattern")
    lines.append("# TYPE sentinel_pattern_double_top_bottom gauge")
    for sym, sig in _signal_cache.items():
        hs = 1 if sig.get("pattern_hs", False) else 0
        dtb = 1 if sig.get("pattern_dtb", False) else 0
        lines.append(f'sentinel_pattern_hs{{symbol="{sym}"}} {hs}')
        lines.append(f'sentinel_pattern_dtb{{symbol="{sym}"}} {dtb}')
    
    # Volume metrics
    lines.append("# HELP sentinel_volume Current volume")
    lines.append("# TYPE sentinel_volume gauge")
    lines.append("# HELP sentinel_volume_20d_avg 20-day average volume")
    lines.append("# TYPE sentinel_volume_20d_avg gauge")
    for sym, sig in _signal_cache.items():
        vol = sig.get("volume", 0)
        vol_20d = sig.get("volume_20d_avg", 0)
        lines.append(f'sentinel_volume{{symbol="{sym}"}} {vol}')
        lines.append(f'sentinel_volume_20d_avg{{symbol="{sym}"}} {vol_20d}')
    
    return "\n".join(lines)
