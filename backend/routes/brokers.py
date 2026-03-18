"""Broker endpoints — list, test, connect, status, reconnect."""
from fastapi import APIRouter, HTTPException

import deps
from schemas import BrokerTestRequest
from brokers import BROKER_REGISTRY, get_broker_info, get_broker_adapter

router = APIRouter()


@router.get("/brokers")
async def list_brokers():
    result = []
    for broker_id, info in BROKER_REGISTRY.items():
        entry = {
            "id": info.id, "name": info.name, "description": info.description,
            "supported": info.supported, "auth_fields": info.auth_fields,
            "docs_url": info.docs_url, "color": info.color, "risk_warning": None,
        }
        if info.risk_warning:
            entry["risk_warning"] = {"level": info.risk_warning.level.value, "message": info.risk_warning.message}
        result.append(entry)
    return result


@router.get("/brokers/status")
async def broker_connection_status():
    return deps.broker_mgr.get_status()


@router.post("/brokers/reconnect")
async def reconnect_brokers():
    results = await deps.broker_mgr.reconnect_all()
    return {"results": results}


@router.get("/brokers/{broker_id}")
async def get_broker(broker_id: str):
    info = get_broker_info(broker_id)
    if not info:
        raise HTTPException(404, f"Broker '{broker_id}' not found.")
    entry = {
        "id": info.id, "name": info.name, "description": info.description,
        "supported": info.supported, "auth_fields": info.auth_fields,
        "docs_url": info.docs_url, "color": info.color, "risk_warning": None,
    }
    if info.risk_warning:
        entry["risk_warning"] = {"level": info.risk_warning.level.value, "message": info.risk_warning.message}
    return entry


@router.post("/brokers/{broker_id}/test")
async def test_broker_connection(broker_id: str, body: BrokerTestRequest):
    info = get_broker_info(broker_id)
    if not info:
        raise HTTPException(404, f"Broker '{broker_id}' not found.")

    results = {"broker_id": broker_id, "broker_name": info.name, "checks": [], "overall": "fail"}

    missing = [f for f in info.auth_fields if not body.credentials.get(f, "").strip()]
    if missing:
        results["checks"].append({"name": "required_fields", "status": "fail", "message": f"Missing required credentials: {', '.join(missing)}"})
        return results
    results["checks"].append({"name": "required_fields", "status": "pass", "message": "All required credential fields provided."})

    format_issues = []
    creds = body.credentials
    if broker_id == "ibkr":
        gw = creds.get("gateway_url", "")
        if gw and not (gw.startswith("http://") or gw.startswith("https://")):
            format_issues.append("'gateway_url' must start with http:// or https://")
    if broker_id == "robinhood":
        mfa = creds.get("mfa_code", "")
        if mfa and (len(mfa) != 6 or not mfa.isdigit()):
            format_issues.append("'mfa_code' should be a 6-digit code")
    if broker_id == "webull":
        pin = creds.get("trade_token", "")
        if pin and (len(pin) < 4 or not pin.isdigit()):
            format_issues.append("'trade_token' should be a numeric PIN (4+ digits)")
    if broker_id == "alpaca":
        for field in ["api_key", "api_secret"]:
            val = creds.get(field, "")
            if val and len(val) < 10:
                format_issues.append(f"'{field}' appears too short — get keys from https://app.alpaca.markets")
        paper = creds.get("paper", "")
        if paper and paper.lower() not in ("true", "false", "1", "0", "yes", "no"):
            format_issues.append("'paper' must be true/false (true for paper trading, false for live)")
    if broker_id == "td_ameritrade":
        for field in ["client_id", "refresh_token"]:
            val = creds.get(field, "")
            if val and len(val) < 8:
                format_issues.append(f"'{field}' appears too short — get from Schwab Developer Portal")
    if broker_id == "tradier":
        token = creds.get("access_token", "")
        if token and len(token) < 10:
            format_issues.append("'access_token' appears too short — get from Tradier dashboard")
    if broker_id == "tradestation":
        for field in ["ts_client_id", "ts_client_secret", "ts_refresh_token"]:
            val = creds.get(field, "")
            if val and len(val) < 8:
                format_issues.append(f"'{field}' appears too short — get from TradeStation API portal")
    if broker_id == "thinkorswim":
        for field in ["tos_consumer_key", "tos_refresh_token"]:
            val = creds.get(field, "")
            if val and len(val) < 8:
                format_issues.append(f"'{field}' appears too short — get from Schwab Developer Portal")

    if format_issues:
        results["checks"].append({"name": "format_validation", "status": "fail", "message": "; ".join(format_issues)})
        return results
    results["checks"].append({"name": "format_validation", "status": "pass", "message": "Credential formats look valid."})

    adapter = get_broker_adapter(broker_id, body.credentials)
    if not adapter:
        results["checks"].append({
            "name": "adapter_available", "status": "warn",
            "message": f"Live adapter for {info.name} is not yet implemented. Credential format validated but connection could not be tested end-to-end.",
        })
        results["overall"] = "partial"
        return results

    try:
        connected = await adapter.check_connection()
        if connected:
            results["checks"].append({"name": "live_connection", "status": "pass", "message": f"Successfully authenticated with {info.name}."})
            try:
                account = await adapter.get_account()
                results["checks"].append({
                    "name": "account_access", "status": "pass",
                    "message": f"Account accessible. Balance: ${account.balance:.2f}, Buying Power: ${account.buying_power:.2f}",
                })
            except Exception as e:
                results["checks"].append({"name": "account_access", "status": "fail", "message": f"Authenticated but could not access account data: {e}"})
            await adapter.close()
            results["overall"] = "pass"
        else:
            results["checks"].append({"name": "live_connection", "status": "fail", "message": "Authentication failed — check your credentials."})
    except Exception as e:
        results["checks"].append({"name": "live_connection", "status": "fail", "message": f"Connection error: {e}"})

    return results


@router.post("/brokers/{broker_id}/connect")
async def connect_broker(broker_id: str, body: BrokerTestRequest):
    info = get_broker_info(broker_id)
    if not info:
        raise HTTPException(404, f"Broker '{broker_id}' not found.")
    ok = await deps.broker_mgr.connect_broker(broker_id, body.credentials)
    if ok:
        return {"status": "connected", "broker_id": broker_id}
    return {"status": "failed", "broker_id": broker_id, "error": deps.broker_mgr._failed.get(broker_id, "Unknown")}
