"""Health, traces, metrics, beta registration, feedback endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import PlainTextResponse

import deps
from schemas import BetaRegistration, FeedbackReport

router = APIRouter()


@router.get("/health")
async def health():
    connected_brokers = sum(1 for _ in deps.broker_mgr._adapters)
    
    # Get environment info
    env_info = {}
    try:
        from config import get_config, get_environment
        env_info = {
            "environment": get_environment().value,
            "debug": get_config().debug,
            "log_level": get_config().log_level,
        }
    except ImportError:
        pass
    
    # Get circuit breaker status
    circuit_status = "unknown"
    try:
        from resilience import broker_resilience
        if broker_resilience.circuit_open:
            circuit_status = "open"
        else:
            circuit_status = "closed"
    except Exception:
        pass
    
    # Get WS manager stats
    ws_stats = {}
    if hasattr(deps.ws_manager, 'get_stats'):
        ws_stats = deps.ws_manager.get_stats()
    
    return {
        "status": "online",
        "running": deps.engine.running,
        "paused": deps.engine.paused,
        "market_open": deps.engine.is_market_open(),
        "market_hours_only": deps.engine.market_hours_only,
        "trading_mode": "paper" if deps.engine.simulate_24_7 else "live",
        "yfinance": deps.YF_AVAILABLE,
        "telegram": deps.telegram_service.running,
        "ws_clients": len(deps.ws_manager.active),
        "brokers_connected": connected_brokers,
        "environment": env_info,
        "circuit_breaker": circuit_status,
        "ws_stats": ws_stats,
    }


@router.get("/traces")
async def get_traces(limit: int = Query(100, ge=1, le=500), name: str = Query("", description="Filter by span name")):
    from telemetry import get_stored_spans
    spans = get_stored_spans(limit=limit, name_filter=name)
    return {"count": len(spans), "spans": spans}


@router.get("/beta/status")
async def beta_status():
    reg = await deps.db.beta_registrations.find_one({}, {"_id": 0})
    return {"registered": reg is not None, "registration": reg}


@router.post("/beta/register")
async def beta_register(body: BetaRegistration):
    if not body.agreement_accepted:
        raise HTTPException(400, "You must accept the Beta Tester Agreement to proceed.")
    if not body.first_name or not body.last_name or not body.email:
        raise HTTPException(400, "Name and email are required.")
    if len(body.ssn_last4) != 4 or not body.ssn_last4.isdigit():
        raise HTTPException(400, "Last 4 of SSN must be exactly 4 digits.")
    doc = body.model_dump()
    doc["ip_address"] = ""
    await deps.db.beta_registrations.delete_many({})
    await deps.db.beta_registrations.insert_one(doc)
    doc.pop("_id", None)
    deps.logger.info(f"BETA REGISTRATION: {body.first_name} {body.last_name} ({body.email})")
    from email_service import send_registration_email
    try:
        send_registration_email(doc)
    except Exception as e:
        deps.logger.warning(f"Registration email failed (non-blocking): {e}")
    return {"status": "registered", "registration": doc}


@router.post("/feedback")
async def submit_feedback(body: FeedbackReport):
    if not body.subject.strip() or not body.description.strip():
        raise HTTPException(400, "Subject and description are required.")
    if body.type not in ("bug", "error", "suggestion", "complaint"):
        raise HTTPException(400, "Type must be one of: bug, error, suggestion, complaint.")
    reg = await deps.db.beta_registrations.find_one({}, {"_id": 0})
    user = reg or {"first_name": "Unregistered", "last_name": "", "email": "unknown"}
    from email_service import send_feedback_email, APP_VERSION, _check_rate_limit
    doc = {
        "type": body.type, "subject": body.subject, "description": body.description,
        "error_log": body.error_log,
        "user_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
        "user_email": user.get("email", "unknown"),
        "app_version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await deps.db.feedback.insert_one(doc)
    doc.pop("_id", None)
    email_sent = False
    try:
        email_sent = send_feedback_email(
            {"type": body.type, "subject": body.subject, "description": body.description, "error_log": body.error_log},
            user,
        )
    except Exception as e:
        deps.logger.warning(f"Feedback email failed (non-blocking): {e}")
    rate_limited = not _check_rate_limit()
    return {"status": "submitted", "email_sent": email_sent, "rate_limited": rate_limited, "feedback": doc}


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    lines = []
    lines.append("# HELP sentinel_pulse_up Whether the bot engine is running.")
    lines.append("# TYPE sentinel_pulse_up gauge")
    lines.append(f"sentinel_pulse_up {1 if deps.engine.running else 0}")

    lines.append("# HELP sentinel_pulse_running Whether the bot engine is running (alias).")
    lines.append("# TYPE sentinel_pulse_running gauge")
    lines.append(f"sentinel_pulse_running {1 if deps.engine.running else 0}")

    lines.append("# HELP sentinel_pulse_demo_mode Whether running in demo mode (no MongoDB).")
    lines.append("# TYPE sentinel_pulse_demo_mode gauge")
    lines.append(f"sentinel_pulse_demo_mode {1 if deps.DEMO_MODE else 0}")

    lines.append("# HELP sentinel_pulse_simulate_24_7 Whether in paper/simulation mode.")
    lines.append("# TYPE sentinel_pulse_simulate_24_7 gauge")
    lines.append(f"sentinel_pulse_simulate_24_7 {1 if deps.engine.simulate_24_7 else 0}")

    lines.append("# HELP sentinel_pulse_paused Whether the bot engine is paused.")
    lines.append("# TYPE sentinel_pulse_paused gauge")
    lines.append(f"sentinel_pulse_paused {1 if deps.engine.paused else 0}")

    lines.append("# HELP sentinel_pulse_market_open Whether the market is open.")
    lines.append("# TYPE sentinel_pulse_market_open gauge")
    lines.append(f"sentinel_pulse_market_open {1 if deps.engine.is_market_open() else 0}")

    lines.append("# HELP sentinel_pulse_ws_clients Active WebSocket connections.")
    lines.append("# TYPE sentinel_pulse_ws_clients gauge")
    lines.append(f"sentinel_pulse_ws_clients {len(deps.ws_manager.active)}")

    balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
    tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
    allocated = round(sum(t.get("base_power", 0) for t in tickers), 2)
    available = round(account_balance - allocated, 2)

    lines.append("# HELP sentinel_pulse_account_balance_usd Total account balance.")
    lines.append("# TYPE sentinel_pulse_account_balance_usd gauge")
    lines.append(f"sentinel_pulse_account_balance_usd {account_balance}")
    lines.append("# HELP sentinel_pulse_allocated_usd Allocated capital.")
    lines.append("# TYPE sentinel_pulse_allocated_usd gauge")
    lines.append(f"sentinel_pulse_allocated_usd {allocated}")
    lines.append("# HELP sentinel_pulse_available_usd Available capital.")
    lines.append("# TYPE sentinel_pulse_available_usd gauge")
    lines.append(f"sentinel_pulse_available_usd {available}")

    lines.append("# HELP sentinel_pulse_tickers_total Configured tickers.")
    lines.append("# TYPE sentinel_pulse_tickers_total gauge")
    lines.append(f"sentinel_pulse_tickers_total {len(tickers)}")
    tickers_enabled = sum(1 for t in tickers if t.get("enabled", True))
    lines.append("# HELP sentinel_pulse_tickers_enabled Enabled tickers.")
    lines.append("# TYPE sentinel_pulse_tickers_enabled gauge")
    lines.append(f"sentinel_pulse_tickers_enabled {tickers_enabled}")

    for t in tickers:
        sym = t.get("symbol", "unknown")
        bp = t.get("base_power", 0)
        lines.append(f'sentinel_pulse_ticker_buy_power_usd{{symbol="{sym}"}} {bp}')

    total_trades = await deps.db.trades.count_documents({})
    lines.append("# HELP sentinel_pulse_trades_total Total trades executed.")
    lines.append("# TYPE sentinel_pulse_trades_total counter")
    lines.append(f"sentinel_pulse_trades_total {total_trades}")

    buy_trades = await deps.db.trades.count_documents({"side": "BUY"})
    sell_trades = await deps.db.trades.count_documents({"side": {"$in": ["SELL", "STOP", "TRAILING_STOP"]}})
    lines.append("# HELP sentinel_pulse_trades_by_side_total Trade count by side.")
    lines.append("# TYPE sentinel_pulse_trades_by_side_total counter")
    lines.append(f'sentinel_pulse_trades_by_side_total{{side="BUY"}} {buy_trades}')
    lines.append(f'sentinel_pulse_trades_by_side_total{{side="SELL"}} {sell_trades}')

    profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
    total_pnl = 0.0
    lines.append("# HELP sentinel_pulse_ticker_pnl_usd Realized P&L per ticker.")
    lines.append("# TYPE sentinel_pulse_ticker_pnl_usd gauge")
    for p in profits_list:
        sym = p.get("symbol", "unknown")
        pnl = p.get("total_pnl", 0)
        total_pnl += pnl
        lines.append(f'sentinel_pulse_ticker_pnl_usd{{symbol="{sym}"}} {round(pnl, 2)}')

    lines.append("# HELP sentinel_pulse_total_pnl_usd Total realized P&L.")
    lines.append("# TYPE sentinel_pulse_total_pnl_usd gauge")
    lines.append(f"sentinel_pulse_total_pnl_usd {round(total_pnl, 2)}")

    cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0
    lines.append("# HELP sentinel_pulse_cash_reserve_usd Cash reserve.")
    lines.append("# TYPE sentinel_pulse_cash_reserve_usd gauge")
    lines.append(f"sentinel_pulse_cash_reserve_usd {cash_reserve}")

    positions = await deps.db.positions.find({}, {"_id": 0}).to_list(100)
    lines.append("# HELP sentinel_pulse_open_positions Open positions.")
    lines.append("# TYPE sentinel_pulse_open_positions gauge")
    lines.append(f"sentinel_pulse_open_positions {len(positions)}")

    for pos in positions:
        sym = pos.get("symbol", "unknown")
        qty = pos.get("quantity", 0)
        upnl = pos.get("unrealized_pnl", 0)
        lines.append(f'sentinel_pulse_position_quantity{{symbol="{sym}"}} {qty}')
        lines.append(f'sentinel_pulse_position_unrealized_pnl_usd{{symbol="{sym}"}} {round(upnl, 2)}')

    # Today's trading stats
    from datetime import datetime, timezone
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_trades = await deps.db.trades.find({"timestamp": {"$gte": today_start.isoformat()}}).to_list(100)
    trades_today = len(today_trades)
    wins_today = sum(1 for t in today_trades if t.get("pnl", 0) > 0)
    losses_today = sum(1 for t in today_trades if t.get("pnl", 0) < 0)
    win_rate = wins_today / trades_today if trades_today > 0 else 0
    pnl_today = sum(t.get("pnl", 0) for t in today_trades)

    lines.append("# HELP sentinel_pulse_trades_today Trades executed today.")
    lines.append("# TYPE sentinel_pulse_trades_today gauge")
    lines.append(f"sentinel_pulse_trades_today {trades_today}")

    lines.append("# HELP sentinel_pulse_wins_today Winning trades today.")
    lines.append("# TYPE sentinel_pulse_wins_today gauge")
    lines.append(f"sentinel_pulse_wins_today {wins_today}")

    lines.append("# HELP sentinel_pulse_losses_today Losing trades today.")
    lines.append("# TYPE sentinel_pulse_losses_today gauge")
    lines.append(f"sentinel_pulse_losses_today {losses_today}")

    lines.append("# HELP sentinel_pulse_win_rate_today Today's win rate.")
    lines.append("# TYPE sentinel_pulse_win_rate_today gauge")
    lines.append(f"sentinel_pulse_win_rate_today {round(win_rate, 3)}")

    lines.append("# HELP sentinel_pulse_pnl_today_usd Today's P&L.")
    lines.append("# TYPE sentinel_pulse_pnl_today_usd gauge")
    lines.append(f"sentinel_pulse_pnl_today_usd {round(pnl_today, 2)}")

    return "\n".join(lines) + "\n"
