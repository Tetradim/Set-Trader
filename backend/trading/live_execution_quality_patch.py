"""Executable quote, quantity, parent-order and expiry behavior for live equities."""
from __future__ import annotations

import hashlib
import math
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any

import deps
from brokers.alpaca_adapter import AlpacaAdapter
from brokers.tradier_adapter import TradierAdapter
from trading import live_pretrade_patch as pretrade
from trading.broker_execution import BrokerExecutionMixin, LiveOrderExecutionError


_original_place = BrokerExecutionMixin._place_live_order_or_raise
_original_build_plans = pretrade._build_plans
_original_persist_results = pretrade._persist_results
_original_reconcile = BrokerExecutionMixin.reconcile_live_orders


def _num(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _env_positive(name: str, default: float) -> float:
    value = _num(os.getenv(name, default))
    return value if value > 0 else default


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_status(value: Any) -> str:
    return {
        "partially_filled": "partially_filled",
        "canceled": "canceled",
        "cancelled": "canceled",
        "new": "submitted",
        "accepted": "submitted",
        "open": "submitted",
    }.get(str(value or "unknown").strip().lower(), str(value or "unknown").strip().lower())


def _quantity_increment(broker_id: str) -> Decimal:
    broker_id = str(broker_id or "").lower()
    if broker_id == "tradier":
        return Decimal("1")
    if broker_id == "alpaca":
        configured = os.getenv("ALPACA_EQUITY_QUANTITY_INCREMENT", "0.000001")
        try:
            increment = Decimal(configured)
        except Exception:
            increment = Decimal("0.000001")
        return increment if increment > 0 else Decimal("0.000001")
    return Decimal("1")


def _floor_increment(quantity: float, increment: Decimal) -> float:
    value = Decimal(str(quantity))
    units = (value / increment).to_integral_value(rounding=ROUND_DOWN)
    return float(units * increment)


async def _build_plans_with_broker_increments(self, **kwargs) -> list[dict]:
    plans = await _original_build_plans(self, **kwargs)
    side = str(kwargs.get("side") or "").upper()
    normalised: list[dict] = []
    removed = 0.0
    for plan in plans:
        increment = _quantity_increment(plan.get("broker_id"))
        requested = _num(plan.get("quantity"))
        quantity = round(_floor_increment(requested, increment), 8)
        removed += max(0.0, requested - quantity)
        if quantity <= 0:
            continue
        normalised.append(
            {
                **plan,
                "quantity": quantity,
                "quantity_increment": float(increment),
                "fractional_supported": increment < Decimal("1"),
            }
        )
    if not normalised:
        raise LiveOrderExecutionError(
            f"{side or 'ORDER'} for {kwargs.get('symbol')} is below every assigned broker's minimum quantity increment"
        )
    if side == "SELL" and removed > 1e-8:
        raise LiveOrderExecutionError(
            f"SELL for {kwargs.get('symbol')} includes {removed:.8f} shares that assigned brokers cannot represent; "
            "reconcile or transfer the fractional remainder before retry"
        )
    return normalised


async def _alpaca_quote_snapshot(self, symbol: str) -> dict:
    session = await self._get_session()
    async with session.get(
        f"https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest",
        headers=self._headers(),
    ) as response:
        data = await response.json()
        if response.status != 200:
            raise RuntimeError(data.get("message") or f"Alpaca quote HTTP {response.status}")
        quote = data.get("quote") or {}
        return {
            "broker_id": "alpaca",
            "symbol": symbol.upper(),
            "bid": _num(quote.get("bp")),
            "ask": _num(quote.get("ap")),
            "bid_size": _num(quote.get("bs")),
            "ask_size": _num(quote.get("as")),
            "source_timestamp": quote.get("t"),
            "received_at_epoch": time.time(),
        }


async def _tradier_quote_snapshot(self, symbol: str) -> dict:
    session = await self._get_session()
    async with session.get(
        "https://api.tradier.com/v1/markets/quotes",
        headers=self._headers(),
        params={"symbols": symbol, "greeks": "false"},
    ) as response:
        data = await response.json()
        if response.status != 200:
            raise RuntimeError(f"Tradier quote HTTP {response.status}: {data}")
        quote = (data.get("quotes") or {}).get("quote") or {}
        if isinstance(quote, list):
            quote = quote[0] if quote else {}
        return {
            "broker_id": "tradier",
            "symbol": symbol.upper(),
            "bid": _num(quote.get("bid")),
            "ask": _num(quote.get("ask")),
            "bid_size": _num(quote.get("bidsize")),
            "ask_size": _num(quote.get("asksize")),
            "source_timestamp": quote.get("trade_date") or quote.get("bid_date") or quote.get("ask_date"),
            "received_at_epoch": time.time(),
        }


def _validated_quote(snapshot: dict) -> dict:
    bid = _num(snapshot.get("bid"))
    ask = _num(snapshot.get("ask"))
    if bid <= 0 or ask <= 0 or ask < bid:
        raise LiveOrderExecutionError(
            f"{snapshot.get('broker_id')} returned non-executable quote bid={bid} ask={ask} for {snapshot.get('symbol')}"
        )
    mid = (bid + ask) / 2
    spread = ask - bid
    spread_pct = (spread / mid) * 100 if mid > 0 else float("inf")
    max_spread_pct = _env_positive("PULSE_MAX_LIVE_SPREAD_PCT", 2.0)
    max_spread_abs = _num(os.getenv("PULSE_MAX_LIVE_SPREAD_ABS", "0"))
    if spread_pct > max_spread_pct:
        raise LiveOrderExecutionError(
            f"{snapshot.get('symbol')} spread {spread_pct:.4f}% at {snapshot.get('broker_id')} "
            f"exceeds live maximum {max_spread_pct:.4f}%"
        )
    if max_spread_abs > 0 and spread > max_spread_abs:
        raise LiveOrderExecutionError(
            f"{snapshot.get('symbol')} spread ${spread:.6f} at {snapshot.get('broker_id')} "
            f"exceeds live maximum ${max_spread_abs:.6f}"
        )
    age = max(0.0, time.time() - _num(snapshot.get("received_at_epoch")))
    max_age = _env_positive("PULSE_MAX_LIVE_QUOTE_AGE_SECONDS", 5.0)
    if age > max_age:
        raise LiveOrderExecutionError(
            f"{snapshot.get('symbol')} quote from {snapshot.get('broker_id')} is stale ({age:.3f}s > {max_age:.3f}s)"
        )
    return {
        **snapshot,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "spread_pct": spread_pct,
        "age_seconds": age,
    }


async def _place_with_executable_quotes(self, *, sym, broker_ids, broker_allocs, order_template, action_label):
    broker_ids = broker_ids or []
    broker_allocs = broker_allocs or {}
    if not self._should_place_broker_orders(broker_ids):
        return await _original_place(
            self,
            sym=sym,
            broker_ids=broker_ids,
            broker_allocs=broker_allocs,
            order_template=order_template,
            action_label=action_label,
        )

    active = self._live_broker_ids_with_allocations(broker_ids, broker_allocs)
    snapshots = []
    for broker_id in active:
        adapter = deps.broker_mgr.get_adapter(broker_id)
        getter = getattr(adapter, "get_quote_snapshot", None) if adapter else None
        if not callable(getter):
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} blocked: {broker_id} lacks executable bid/ask quote support"
            )
        try:
            snapshots.append(_validated_quote(await getter(sym)))
        except LiveOrderExecutionError:
            raise
        except Exception as exc:
            raise LiveOrderExecutionError(
                f"{action_label} for {sym} blocked: {broker_id} quote lookup failed: {exc}"
            ) from exc

    side = str((order_template or {}).get("side") or "").upper()
    executable_price = (
        max(snapshot["ask"] for snapshot in snapshots)
        if side == "BUY"
        else min(snapshot["bid"] for snapshot in snapshots)
    )
    enriched = {
        **(order_template or {}),
        "price": executable_price,
        "execution_quotes": snapshots,
        "quote_checked_at": _iso_now(),
    }
    return await _original_place(
        self,
        sym=sym,
        broker_ids=broker_ids,
        broker_allocs=broker_allocs,
        order_template=enriched,
        action_label=action_label,
    )


def _child_id(result: dict, intent_key: str) -> str:
    return str(
        result.get("broker_order_id")
        or result.get("order_id")
        or result.get("external_id")
        or result.get("idempotency_key")
        or f"unidentified:{intent_key}:{result.get('broker_id', '')}"
    )


async def _persist_results_with_parent(self, **kwargs) -> None:
    await _original_persist_results(self, **kwargs)
    intent_key = kwargs["intent_key"]
    symbol = kwargs["symbol"]
    side = kwargs["side"]
    order_type = kwargs["order_type"]
    plans = list(kwargs.get("plans") or [])
    results = list(kwargs.get("results") or [])
    child_ids = sorted(_child_id(result, intent_key) for result in results)
    digest = hashlib.sha256(
        f"{intent_key}|{'|'.join(child_ids)}".encode("utf-8")
    ).hexdigest()[:24]
    parent_id = f"parent:{symbol}:{side}:{digest}"
    statuses = [_normalise_status(result.get("status")) for result in results]
    pending = any(
        status in (self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES)
        for status in statuses
    )
    requested = round(sum(_num(plan.get("quantity")) for plan in plans), 8)
    filled = round(sum(self._broker_result_filled_quantity(result) for result in results), 8)
    state = (
        "working"
        if pending
        else "completed"
        if requested > 0 and abs(filled - requested) <= 1e-6
        else "partial_complete"
        if filled > 0
        else "failed"
    )
    lifetime = _env_positive(
        "PULSE_LIVE_MARKET_ORDER_TTL_SECONDS" if order_type.upper() == "MARKET" else "PULSE_LIVE_LIMIT_ORDER_TTL_SECONDS",
        30.0 if order_type.upper() == "MARKET" else 120.0,
    )
    valid_until = time.time() + lifetime
    now = _iso_now()

    parent_collection = getattr(deps.db, "parent_orders", None)
    if parent_collection is not None:
        await parent_collection.update_one(
            {"parent_order_id": parent_id},
            {
                "$set": {
                    "parent_order_id": parent_id,
                    "intent_key": intent_key,
                    "symbol": symbol,
                    "side": side,
                    "order_type": order_type,
                    "policy": "accept_partial",
                    "target_quantity": requested,
                    "filled_quantity": filled,
                    "remaining_quantity": round(max(0.0, requested - filled), 8),
                    "state": state,
                    "child_order_ids": child_ids,
                    "valid_until_epoch": valid_until,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    broker_collection = getattr(deps.db, "broker_orders", None)
    if broker_collection is not None:
        for result in results:
            durable_id = _child_id(result, intent_key)
            await broker_collection.update_one(
                {
                    "intent_key": intent_key,
                    "broker_id": str(result.get("broker_id") or ""),
                    "durable_order_id": durable_id,
                },
                {
                    "$set": {
                        "parent_order_id": parent_id,
                        "parent_policy": "accept_partial",
                        "valid_until_epoch": valid_until,
                    }
                },
            )


async def _refresh_parent_orders(self, symbol: str | None = None) -> int:
    parents = getattr(deps.db, "parent_orders", None)
    children = getattr(deps.db, "broker_orders", None)
    if parents is None or children is None:
        return 0
    query: dict[str, Any] = {"state": {"$in": ["working", "reconciliation_required"]}}
    if symbol:
        query["symbol"] = symbol.upper()
    docs = await parents.find(query, {"_id": 0}).to_list(200)
    updated = 0
    for parent in docs:
        rows = await children.find(
            {"parent_order_id": parent.get("parent_order_id")},
            {"_id": 0, "status": 1, "filled_quantity": 1},
        ).to_list(100)
        statuses = [_normalise_status(row.get("status")) for row in rows]
        pending = any(
            status in (self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES)
            for status in statuses
        )
        filled = round(sum(_num(row.get("filled_quantity")) for row in rows), 8)
        target = _num(parent.get("target_quantity"))
        state = (
            "working"
            if pending
            else "completed"
            if target > 0 and abs(filled - target) <= 1e-6
            else "partial_complete"
            if filled > 0
            else "failed"
        )
        await parents.update_one(
            {"parent_order_id": parent.get("parent_order_id")},
            {
                "$set": {
                    "filled_quantity": filled,
                    "remaining_quantity": round(max(0.0, target - filled), 8),
                    "state": state,
                    "updated_at": _iso_now(),
                }
            },
        )
        updated += 1
    return updated


async def _reconcile_with_expiry(self, symbol: str | None = None) -> dict:
    result = await _original_reconcile(self, symbol)
    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return result
    query: dict[str, Any] = {
        "status": {
            "$in": sorted(self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES)
        },
        "valid_until_epoch": {"$lte": time.time()},
        "cancel_requested_at": {"$exists": False},
    }
    if symbol:
        query["symbol"] = symbol.upper()
    expired = await collection.find(query, {"_id": 0}).to_list(100)
    cancel_requests = 0
    for order in expired:
        broker_id = str(order.get("broker_id") or "")
        broker_order_id = str(order.get("broker_order_id") or "")
        adapter = deps.broker_mgr.get_adapter(broker_id)
        accepted = False
        error = ""
        try:
            accepted = bool(await adapter.cancel_order(broker_order_id)) if adapter else False
        except Exception as exc:
            error = str(exc)
        await collection.update_one(
            {
                "intent_key": order.get("intent_key"),
                "broker_id": broker_id,
                "durable_order_id": order.get("durable_order_id"),
            },
            {
                "$set": {
                    "cancel_requested_at": _iso_now(),
                    "cancel_request_accepted": accepted,
                    "cancel_request_error": error,
                }
            },
        )
        cancel_requests += 1
    if cancel_requests:
        follow_up = await _original_reconcile(self, symbol)
        result = {
            "checked": result.get("checked", 0) + follow_up.get("checked", 0),
            "applied": result.get("applied", 0) + follow_up.get("applied", 0),
            "unresolved": follow_up.get("unresolved", result.get("unresolved", 0)),
        }
    await _refresh_parent_orders(self, symbol)
    result["cancel_requests"] = cancel_requests
    return result


AlpacaAdapter.get_quote_snapshot = _alpaca_quote_snapshot
TradierAdapter.get_quote_snapshot = _tradier_quote_snapshot
pretrade._build_plans = _build_plans_with_broker_increments
pretrade._persist_results = _persist_results_with_parent
BrokerExecutionMixin._place_live_order_or_raise = _place_with_executable_quotes
BrokerExecutionMixin.reconcile_live_orders = _reconcile_with_expiry
BrokerExecutionMixin.refresh_parent_orders = _refresh_parent_orders
