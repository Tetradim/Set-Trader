"""Position-scoped Edge strategy authorization for Pulse handoffs."""
from __future__ import annotations

from datetime import datetime, timezone
import functools
import math
import os
from typing import Any

from fastapi.routing import APIRoute, APIRouter


_original_include_router = APIRouter.include_router
_PATCH_MARKER = "_pulse_edge_strategy_authorization_v1"
_RISK_REDUCING_ACTIONS = {"sell", "stop_buying", "stop_all", "emergency_exit"}


def _metadata(body: Any) -> dict[str, Any]:
    value = getattr(body, "metadata", None)
    return value if isinstance(value, dict) else {}


def _trade_card(body: Any) -> dict[str, Any]:
    value = _metadata(body).get("trade_card")
    return value if isinstance(value, dict) else {}


def _action(body: Any) -> str:
    value = getattr(body, "action", "")
    return str(getattr(value, "value", value) or "").lower()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _response(edge_module: Any, body: Any, reason: str, message: str) -> dict[str, Any]:
    return edge_module._handoff_response(
        body,
        accepted=False,
        status="rejected",
        reason=reason,
        message=message,
    )


def _authorization_required(body: Any) -> bool:
    action = _action(body)
    if action in _RISK_REDUCING_ACTIONS:
        return False
    return os.getenv("PULSE_REQUIRE_EDGE_TRADE_CARD", "true").strip().lower() in {"1", "true", "yes", "on"}


async def _validate(edge_module: Any, body: Any) -> dict[str, Any] | None:
    metadata = _metadata(body)
    card = _trade_card(body)
    action = _action(body)
    if not card:
        if _authorization_required(body):
            return _response(edge_module, body, "edge_trade_card_required", "New Pulse exposure requires an Edge trade card.")
        return None

    if str(card.get("target_bot") or metadata.get("target_bot") or "").lower() != "sentinel-pulse":
        return _response(edge_module, body, "edge_trade_card_wrong_bot", "Trade card is not assigned to Sentinel Pulse.")
    symbol = str(getattr(body, "symbol", "") or "").upper()
    if str(card.get("symbol") or "").upper() != symbol:
        return _response(edge_module, body, "edge_trade_card_symbol_mismatch", "Trade card symbol does not match the handoff.")
    if not all(str(card.get(key) or "").strip() for key in ("card_id", "strategy_id", "thesis_id", "position_id")):
        return _response(edge_module, body, "edge_trade_card_identity_missing", "Trade card identity fields are incomplete.")
    state = str(card.get("state") or "").lower()
    allowed_states = {"armed", "entering", "active", "reducing", "exiting"}
    if state not in allowed_states:
        return _response(edge_module, body, "edge_trade_card_not_active", f"Trade card state {state or 'missing'} is not executable.")
    expiry = _parse_time(card.get("expires_at"))
    if expiry is not None and expiry <= datetime.now(timezone.utc):
        return _response(edge_module, body, "edge_trade_card_expired", "Trade card expired before Pulse execution.")
    metadata_position_id = str(metadata.get("position_id") or "")
    if metadata_position_id and metadata_position_id != str(card.get("position_id")):
        return _response(edge_module, body, "edge_position_id_mismatch", "Handoff position_id does not match the trade card.")
    lifecycle = metadata.get("strategy_lifecycle") if isinstance(metadata.get("strategy_lifecycle"), dict) else {}
    stop_owner = lifecycle.get("stop_owner") if isinstance(lifecycle.get("stop_owner"), dict) else {}
    if stop_owner and stop_owner.get("position_id") != card.get("position_id"):
        return _response(edge_module, body, "edge_stop_owner_mismatch", "Position-scoped stop owner does not match the trade card.")

    ticker = await edge_module.deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
    persisted_position_id = str((ticker or {}).get("edge_position_id") or "")
    if action == "buy":
        maximum_entry = _positive(card.get("maximum_entry_price"))
        requested_price = _positive(metadata.get("price") or metadata.get("current_price"))
        if maximum_entry is not None and requested_price is not None and requested_price > maximum_entry:
            return _response(edge_module, body, "edge_maximum_entry_exceeded", "Current price is above the trade card maximum entry price.")
        if persisted_position_id and persisted_position_id != str(card.get("position_id")):
            position = edge_module._current_position(symbol)
            quantity = float((position or {}).get("qty", (position or {}).get("quantity", 0)) or 0)
            if quantity > 0:
                return _response(edge_module, body, "edge_position_already_owned", "A different Edge position already owns the Pulse symbol.")
    elif action not in _RISK_REDUCING_ACTIONS or metadata.get("supervisory_directive") in {"set_stop", "reduce_position"}:
        if not persisted_position_id:
            return _response(edge_module, body, "edge_position_owner_missing", "Pulse has no persisted Edge position owner for this directive.")
        if persisted_position_id != str(card.get("position_id")):
            return _response(edge_module, body, "edge_position_owner_mismatch", "Directive targets a different Edge position.")
    return None


async def _persist_after(edge_module: Any, body: Any, response: Any) -> None:
    if not isinstance(response, dict):
        return
    status = str(response.get("status") or "").lower()
    accepted = bool(response.get("accepted") or response.get("sent")) and status not in {"rejected", "failed", "cancelled", "canceled"}
    if not accepted:
        return
    metadata = _metadata(body)
    card = _trade_card(body)
    if not card:
        return
    symbol = str(getattr(body, "symbol", "") or "").upper()
    action = _action(body)
    identity = {
        "edge_card_id": card.get("card_id"),
        "edge_strategy_id": card.get("strategy_id"),
        "edge_thesis_id": card.get("thesis_id"),
        "edge_position_id": card.get("position_id"),
        "edge_trade_card_state": card.get("state"),
        "edge_trade_card_expires_at": card.get("expires_at"),
        "edge_risk_budget_pct": card.get("risk_budget_pct"),
        "edge_target_notional": card.get("target_notional"),
    }
    if action == "buy":
        await edge_module.deps.db.tickers.update_one({"symbol": symbol}, {"$set": identity})
        return
    if action == "tighten_stop" or metadata.get("supervisory_directive") == "set_stop":
        await edge_module.deps.db.tickers.update_one(
            {"symbol": symbol},
            {"$set": {**identity, "edge_stop_position_id": card.get("position_id"), "edge_stop_inherit_on_reentry": False}},
        )
        return
    if action in {"sell", "emergency_exit"} and metadata.get("invalidate_position_scoped_stop"):
        position = edge_module._current_position(symbol)
        quantity = float((position or {}).get("qty", (position or {}).get("quantity", 0)) or 0)
        if quantity <= 0:
            await edge_module.deps.db.tickers.update_one(
                {"symbol": symbol, "edge_position_id": card.get("position_id")},
                {
                    "$unset": {
                        "edge_card_id": "",
                        "edge_strategy_id": "",
                        "edge_thesis_id": "",
                        "edge_position_id": "",
                        "edge_trade_card_state": "",
                        "edge_trade_card_expires_at": "",
                        "edge_stop_position_id": "",
                        "edge_stop_inherit_on_reentry": "",
                        "edge_stop_price": "",
                        "edge_stop_intent_id": "",
                    },
                    "$set": {"stop_offset": 0.0, "stop_percent": True},
                },
            )


def _wrap_edge_handoff(route: APIRoute) -> None:
    if getattr(route.endpoint, _PATCH_MARKER, False):
        return
    original_endpoint = route.endpoint

    @functools.wraps(original_endpoint)
    async def wrapped(*args: Any, **kwargs: Any):
        body = kwargs.get("body")
        if body is None and args:
            body = args[0]
        if body is None:
            return await original_endpoint(*args, **kwargs)
        edge_module = __import__("routes.edge", fromlist=["post_handoff"])
        rejection = await _validate(edge_module, body)
        if rejection is not None:
            return rejection
        response = await original_endpoint(*args, **kwargs)
        await _persist_after(edge_module, body, response)
        if isinstance(response, dict):
            card = _trade_card(body)
            if card:
                response.setdefault("card_id", card.get("card_id"))
                response.setdefault("position_id", card.get("position_id"))
                response.setdefault("strategy_id", card.get("strategy_id"))
        return response

    setattr(wrapped, _PATCH_MARKER, True)
    route.endpoint = wrapped


def _include_router_with_strategy_contract(self: APIRouter, router: APIRouter, *args: Any, **kwargs: Any):
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute) and route.path == "/edge/handoff" and "POST" in (route.methods or set()):
            _wrap_edge_handoff(route)
    return _original_include_router(self, router, *args, **kwargs)


if not getattr(APIRouter.include_router, _PATCH_MARKER, False):
    setattr(_include_router_with_strategy_contract, _PATCH_MARKER, True)
    APIRouter.include_router = _include_router_with_strategy_contract
