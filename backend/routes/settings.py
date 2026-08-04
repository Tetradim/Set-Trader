"""Global runtime settings endpoints."""
import os
import secrets

from fastapi import APIRouter, HTTPException

import deps
from audit_service import AuditEventType, audit_service
from schemas import SettingsUpdate
from shared import edge_client

router = APIRouter()

LIVE_TRADING_CONFIRMATION = "ENABLE LIVE TRADING"
LIVE_TRADING_OPERATOR_SECRET_ENV = "SENTINEL_PULSE_LIVE_TRADING_OPERATOR_SECRET"
REMOVED_LOCAL_EXECUTION_ERROR = "local_paper_execution_removed"


def _engine_is_dry_run() -> bool:
    is_dry_run = getattr(deps.engine, "is_dry_run", None)
    if callable(is_dry_run):
        return bool(is_dry_run())
    return bool(getattr(deps.engine, "_dry_run_mode", False))


def _candidate_live_mode(body: SettingsUpdate) -> bool:
    return True


def _current_live_mode() -> bool:
    return True


def _mode_label(is_live: bool) -> str:
    return "live"


def _requested_mode_fields(body: SettingsUpdate) -> list[str]:
    return [
        field
        for field, value in (
            ("simulate_24_7", body.simulate_24_7),
            ("market_hours_only", body.market_hours_only),
            ("live_during_market_hours", body.live_during_market_hours),
            ("paper_after_hours", body.paper_after_hours),
        )
        if value is not None
    ]


def _configured_live_trading_operator_secret() -> str:
    return os.getenv(LIVE_TRADING_OPERATOR_SECRET_ENV, "").strip()


def _live_trading_operator_secret_matches(body: SettingsUpdate) -> bool:
    expected = _configured_live_trading_operator_secret()
    provided = (body.live_trading_operator_secret or "").strip()
    if not expected or not provided:
        return False
    return secrets.compare_digest(expected, provided)


async def _audit_mode_setting_attempt(
    body: SettingsUpdate,
    old_mode: str,
    new_mode: str,
    *,
    success: bool,
    error_message: str | None = None,
):
    await audit_service.log(
        AuditEventType.SETTING_CHANGED,
        {
            "setting": "trading_mode",
            "old_value": old_mode,
            "new_value": new_mode,
            "source": "settings_api",
            "requested_fields": _requested_mode_fields(body),
            "dry_run_enabled": _engine_is_dry_run(),
        },
        success=success,
        error_message=error_message,
    )


@router.post("/settings")
async def update_settings(body: SettingsUpdate):
    if body.simulate_24_7 is True or body.paper_after_hours is True or body.live_during_market_hours is False:
        raise HTTPException(
            status_code=400,
            detail={
                "error": REMOVED_LOCAL_EXECUTION_ERROR,
                "message": "Pulse local paper/demo execution is removed; runtime trades must route to assigned brokers.",
            },
        )

    mode_fields_requested = any(
        value is not None
        for value in (
            body.simulate_24_7,
            body.market_hours_only,
            body.live_during_market_hours,
            body.paper_after_hours,
        )
    )
    current_live_mode = _current_live_mode()
    candidate_live_mode = _candidate_live_mode(body) if mode_fields_requested else current_live_mode
    current_mode_label = _mode_label(current_live_mode)
    candidate_mode_label = _mode_label(candidate_live_mode)

    if mode_fields_requested and not current_live_mode and candidate_live_mode:
        if body.live_trading_confirmation != LIVE_TRADING_CONFIRMATION:
            await _audit_mode_setting_attempt(
                body,
                current_mode_label,
                candidate_mode_label,
                success=False,
                error_message="live_trading_confirmation_required",
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "live_trading_confirmation_required",
                    "required_confirmation": LIVE_TRADING_CONFIRMATION,
                },
            )
        if not _configured_live_trading_operator_secret():
            await _audit_mode_setting_attempt(
                body,
                current_mode_label,
                candidate_mode_label,
                success=False,
                error_message="live_trading_operator_secret_unconfigured",
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "live_trading_operator_secret_unconfigured",
                    "required_env": LIVE_TRADING_OPERATOR_SECRET_ENV,
                },
            )
        if not _live_trading_operator_secret_matches(body):
            await _audit_mode_setting_attempt(
                body,
                current_mode_label,
                candidate_mode_label,
                success=False,
                error_message="live_trading_operator_secret_required",
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "live_trading_operator_secret_required",
                },
            )

    if mode_fields_requested:
        deps.engine.simulate_24_7 = False
        if body.market_hours_only is not None:
            deps.engine.market_hours_only = body.market_hours_only
        deps.engine.live_during_market_hours = True
        deps.engine.paper_after_hours = False
        await deps.engine.save_state()
        await _audit_mode_setting_attempt(
            body,
            current_mode_label,
            candidate_mode_label,
            success=True,
        )

    if body.pattern_detection_enabled is not None:
        await deps.db.settings.update_one(
            {"key": "pattern_detection_enabled"},
            {"$set": {"value": body.pattern_detection_enabled}},
            upsert=True,
        )
    if body.pattern_min_confidence is not None:
        await deps.db.settings.update_one(
            {"key": "pattern_min_confidence"},
            {"$set": {"value": body.pattern_min_confidence}},
            upsert=True,
        )
    if body.pattern_send_to_edge is not None:
        await deps.db.settings.update_one(
            {"key": "pattern_send_to_edge"},
            {"$set": {"value": body.pattern_send_to_edge}},
            upsert=True,
        )
    if body.edge_retry_max_attempts is not None:
        if body.edge_retry_max_attempts < 0 or body.edge_retry_max_attempts > 100:
            raise HTTPException(400, "Edge retry attempts must be between 0 and 100.")
        edge_client.set_max_retry_attempts(body.edge_retry_max_attempts)
        await deps.db.settings.update_one(
            {"key": "edge_retry_max_attempts"},
            {"$set": {"value": body.edge_retry_max_attempts}},
            upsert=True,
        )
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
    if body.global_daily_drawdown is not None:
        drawdown_doc = body.global_daily_drawdown.model_dump()
        if drawdown_doc["limit"] < 0 or drawdown_doc["limit"] > 100_000_000:
            raise HTTPException(400, "Global daily drawdown limit is outside the allowed range.")
        await deps.db.settings.update_one(
            {"key": "global_daily_drawdown"},
            {"$set": {"value": drawdown_doc}},
            upsert=True,
        )
    if body.telegram:
        doc = body.telegram.model_dump()
        await deps.db.settings.update_one({"key": "telegram"}, {"$set": {"value": doc}}, upsert=True)
        if doc.get("bot_token"):
            try:
                await deps.telegram_service.start(doc["bot_token"], doc.get("chat_ids", []))
            except Exception as exc:
                deps.logger.error(f"Telegram start failed: {exc}")
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
    drawdown_doc = await deps.db.settings.find_one({"key": "global_daily_drawdown"}, {"_id": 0})
    pattern_enabled_doc = await deps.db.settings.find_one({"key": "pattern_detection_enabled"}, {"_id": 0})
    pattern_min_conf_doc = await deps.db.settings.find_one({"key": "pattern_min_confidence"}, {"_id": 0})
    pattern_edge_doc = await deps.db.settings.find_one({"key": "pattern_send_to_edge"}, {"_id": 0})
    edge_retry_doc = await deps.db.settings.find_one({"key": "edge_retry_max_attempts"}, {"_id": 0})

    tickers = await deps.db.tickers.find({}, {"_id": 0, "base_power": 1}).to_list(100)
    allocated = sum(t.get("base_power", 0) for t in tickers)
    account_balance = balance_doc.get("value", 0) if balance_doc else 0
    cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0
    return {
        "simulate_24_7": False,
        "market_hours_only": deps.engine.market_hours_only,
        "live_during_market_hours": True,
        "paper_after_hours": False,
        "trading_mode": deps.engine.get_trading_mode(),
        "telegram": tg.get("value", {}) if tg else {"bot_token": "", "chat_ids": []},
        "telegram_connected": deps.telegram_service.running,
        "increment_step": inc_doc.get("value", 0.5) if inc_doc else 0.5,
        "decrement_step": dec_doc.get("value", 0.5) if dec_doc else 0.5,
        "cash_reserve": cash_reserve,
        "account_balance": round(account_balance, 2),
        "allocated": round(allocated, 2),
        "available": round(account_balance - allocated, 2),
        "global_daily_drawdown": drawdown_doc.get("value", {"enabled": False, "limit": 3, "type": "percent"}) if drawdown_doc else {"enabled": False, "limit": 3, "type": "percent"},
        "pattern_detection_enabled": pattern_enabled_doc.get("value", True) if pattern_enabled_doc else True,
        "pattern_min_confidence": pattern_min_conf_doc.get("value", 0.65) if pattern_min_conf_doc else 0.65,
        "pattern_send_to_edge": pattern_edge_doc.get("value", True) if pattern_edge_doc else True,
        "edge_retry_max_attempts": edge_retry_doc.get("value", 10) if edge_retry_doc else 10,
    }


@router.post("/settings/telegram/test")
async def test_telegram():
    if not deps.telegram_service.running:
        raise HTTPException(400, "Telegram bot is not connected. Save a valid token first.")
    await deps.telegram_service._broadcast_alert("Test alert from Sentinel Pulse! Connection verified.")
    return {"ok": True, "sent_to": deps.telegram_service.chat_ids}
