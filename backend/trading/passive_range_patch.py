"""Opt-in passive range scalping for exact resting limit orders.

This patch intentionally leaves the existing bracket evaluator unchanged unless
``passive_range_enabled`` is true for a ticker. The passive mode rests a buy
limit immediately, advances only from broker-confirmed cumulative fills, rests
the matching sell limit after entry, and records completed-cycle telemetry.

The first live implementation is deliberately conservative:
* one broker per passive ticker;
* adapter order-status evidence is mandatory;
* partial fills are cancelled and managed as the confirmed filled quantity by
  default;
* unsupported adapters fail closed rather than treating a quote touch as fill.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import deps
from schemas import TradeRecord
from trading.price_precision import bracket_target, decimal_to_float, infer_tick_size
from trading.ticker_evaluation import TickerEvaluationMixin


_ORIGINAL_EVALUATE_TICKER = TickerEvaluationMixin.evaluate_ticker
_PENDING = {"accepted", "new", "open", "pending", "submitted", "working"}
_PARTIAL = {"partial", "partially_filled", "partially-filled"}
_FILLED = {"complete", "completed", "executed", "fill", "filled"}
_FAILED = {"cancelled", "canceled", "expired", "failed", "rejected", "error"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().isoformat()


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _status(value: Any) -> str:
    return str(value or "").strip().lower()


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _elapsed_seconds(value: Any) -> float:
    started = _parse_time(value)
    if not started:
        return 0.0
    return max(0.0, (_now() - started).total_seconds())


def _active_broker(ticker_doc: dict) -> tuple[str, float] | tuple[None, float]:
    broker_ids = ticker_doc.get("broker_ids") or []
    allocations = ticker_doc.get("broker_allocations") or {}
    active = [
        (str(broker_id), _number(allocations.get(broker_id)))
        for broker_id in broker_ids
        if _number(allocations.get(broker_id)) > 0
    ]
    if len(active) != 1:
        return None, 0.0
    return active[0]


def _order_result(broker_id: str, value: Any) -> dict:
    if isinstance(value, dict):
        result = dict(value)
    else:
        result = {
            "status": getattr(value, "status", ""),
            "broker_order_id": getattr(value, "broker_order_id", ""),
            "filled_price": getattr(value, "filled_price", 0),
            "filled_quantity": getattr(value, "filled_quantity", 0),
            "error": getattr(value, "error", ""),
        }
    result["broker_id"] = broker_id
    result["broker_order_id"] = str(
        result.get("broker_order_id") or result.get("order_id") or ""
    )
    result["order_id"] = result["broker_order_id"]
    result["status"] = _status(result.get("status"))
    result["filled_price"] = _number(
        result.get("filled_price") or result.get("avg_fill_price")
    )
    result["filled_quantity"] = _number(
        result.get("filled_quantity") or result.get("filled_qty")
    )
    result["error"] = str(result.get("error") or "")
    return result


def _is_paper(self, ticker_doc: dict) -> bool:
    return self.is_paper_trading() or not (ticker_doc.get("broker_ids") or [])


async def _load_state(self, symbol: str) -> dict:
    states = getattr(self, "_passive_range_states", None)
    if states is None:
        states = self._passive_range_states = {}
    loaded = getattr(self, "_passive_range_loaded", None)
    if loaded is None:
        loaded = self._passive_range_loaded = set()

    if symbol not in loaded:
        loaded.add(symbol)
        try:
            doc = await deps.db.passive_range_state.find_one(
                {"symbol": symbol}, {"_id": 0}
            )
            if doc:
                states[symbol] = doc
        except Exception as exc:
            deps.logger.debug("Passive range state load skipped for %s: %s", symbol, exc)

    return states.setdefault(
        symbol,
        {
            "symbol": symbol,
            "phase": "IDLE",
            "cycle_id": "",
            "position_qty": 0.0,
            "entry_price": 0.0,
            "touch_count": 0,
            "updated_at": _iso_now(),
        },
    )


async def _persist_state(self, state: dict) -> None:
    state["updated_at"] = _iso_now()
    try:
        await deps.db.passive_range_state.update_one(
            {"symbol": state["symbol"]},
            {"$set": dict(state)},
            upsert=True,
        )
    except Exception as exc:
        deps.logger.warning(
            "Could not persist passive range state for %s: %s",
            state.get("symbol"),
            exc,
        )


async def _quote_snapshot(self, ticker_doc: dict, symbol: str, last_price: float) -> dict:
    broker_id, _ = _active_broker(ticker_doc)
    if broker_id and deps.broker_mgr:
        adapter = deps.broker_mgr.get_adapter(broker_id)
        getter = getattr(adapter, "get_quote_snapshot", None) if adapter else None
        if getter:
            try:
                snapshot = await getter(symbol)
                if isinstance(snapshot, dict):
                    snapshot = dict(snapshot)
                    snapshot.setdefault("last", last_price)
                    return snapshot
            except Exception as exc:
                deps.logger.warning("Passive quote snapshot failed for %s: %s", symbol, exc)
    return {"bid": 0.0, "ask": 0.0, "last": last_price, "timestamp": _iso_now()}


async def _poll_live_order(self, broker_id: str, order: dict) -> Optional[dict]:
    adapter = deps.broker_mgr.get_adapter(broker_id) if deps.broker_mgr else None
    getter = getattr(adapter, "get_order_status", None) if adapter else None
    if not getter:
        deps.logger.error(
            "Passive range order polling blocked for %s: adapter lacks get_order_status",
            broker_id,
        )
        return None
    try:
        result = await getter(order.get("broker_order_id", ""))
    except Exception as exc:
        deps.logger.warning("Passive range order poll failed for %s: %s", broker_id, exc)
        return None
    return _order_result(broker_id, result) if result else None


async def _cancel_live_order(self, broker_id: str, order: dict) -> bool:
    adapter = deps.broker_mgr.get_adapter(broker_id) if deps.broker_mgr else None
    if not adapter or not order.get("broker_order_id"):
        return False
    try:
        return bool(await adapter.cancel_order(order["broker_order_id"]))
    except Exception as exc:
        deps.logger.warning("Passive range cancel failed for %s: %s", broker_id, exc)
        return False


def _quantity_for_power(power: float, limit_price: float, fractional: bool) -> float:
    if power <= 0 or limit_price <= 0:
        return 0.0
    quantity = power / limit_price
    if fractional:
        return round(quantity, 8)
    return float(math.floor(quantity))


async def _submit_live_limit(
    self,
    *,
    ticker_doc: dict,
    symbol: str,
    side: str,
    quantity: float,
    limit_price: float,
) -> Optional[dict]:
    broker_id, allocation = _active_broker(ticker_doc)
    if not broker_id:
        deps.logger.error(
            "Passive range live mode for %s requires exactly one positively allocated broker",
            symbol,
        )
        return None

    if hasattr(self, "pre_trade_check"):
        allowed, reason = await self.pre_trade_check(symbol, side, quantity, limit_price)
        if not allowed:
            deps.logger.warning("Passive range %s blocked for %s: %s", side, symbol, reason)
            return None

    results = await deps.broker_mgr.place_orders_for_ticker(
        broker_ids=[broker_id],
        allocations={broker_id: max(allocation, quantity * limit_price)},
        order_template={
            "symbol": symbol,
            "side": side,
            "order_type": "LIMIT",
            "price": limit_price,
            "limit_price": limit_price,
            "quantity": quantity,
        },
    )
    if not results:
        return None
    result = _order_result(broker_id, results[0])
    if result["error"] or result["status"] in _FAILED:
        deps.logger.warning("Passive range %s rejected for %s: %s", side, symbol, result)
        return None
    if not result["broker_order_id"]:
        deps.logger.warning("Passive range %s for %s returned no broker order ID", side, symbol)
        return None
    result.update(
        {
            "side": side,
            "limit_price": limit_price,
            "requested_quantity": quantity,
            "submitted_at": _iso_now(),
        }
    )
    return result


def _paper_order(side: str, quantity: float, limit_price: float) -> dict:
    return {
        "broker_id": "paper",
        "broker_order_id": f"paper:{uuid.uuid4()}",
        "order_id": "",
        "status": "working",
        "filled_price": 0.0,
        "filled_quantity": 0.0,
        "error": "",
        "side": side,
        "limit_price": limit_price,
        "requested_quantity": quantity,
        "submitted_at": _iso_now(),
    }


async def _record_fill(
    self,
    *,
    ticker_doc: dict,
    symbol: str,
    side: str,
    price: float,
    quantity: float,
    target: float,
    broker_result: dict,
    entry_price: float = 0.0,
    pnl: float = 0.0,
    reason: str,
) -> None:
    is_paper = _is_paper(self, ticker_doc)
    trade = TradeRecord(
        symbol=symbol,
        side=side,
        price=price,
        quantity=quantity,
        reason=reason,
        pnl=round(pnl, 2),
        order_type="LIMIT",
        rule_mode="PASSIVE_RANGE",
        entry_price=entry_price,
        target_price=target,
        total_value=round(price * quantity, 2),
        buy_power=_number(ticker_doc.get("base_power")),
        trading_mode="paper" if is_paper else "live",
        broker_results=[] if is_paper else [broker_result],
    )
    await self._record_trade(trade)


async def _complete_cycle(
    self,
    *,
    ticker_doc: dict,
    state: dict,
    exit_price: float,
    exit_quantity: float,
    pnl: float,
    exit_reason: str,
) -> None:
    symbol = state["symbol"]
    cycle = {
        "cycle_id": state.get("cycle_id") or str(uuid.uuid4()),
        "symbol": symbol,
        "buy_target": state.get("buy_target", 0.0),
        "sell_target": state.get("sell_target", 0.0),
        "entry_price": state.get("entry_price", 0.0),
        "exit_price": exit_price,
        "quantity": exit_quantity,
        "gross_pnl": round(pnl, 4),
        "started_at": state.get("cycle_started_at"),
        "buy_filled_at": state.get("buy_filled_at"),
        "completed_at": _iso_now(),
        "duration_seconds": _elapsed_seconds(state.get("cycle_started_at")),
        "exit_reason": exit_reason,
        "trading_mode": "paper" if _is_paper(self, ticker_doc) else "live",
    }
    try:
        await deps.db.passive_range_cycles.insert_one(cycle)
    except Exception as exc:
        deps.logger.warning("Could not persist passive range cycle for %s: %s", symbol, exc)


async def _arm_buy(
    self,
    *,
    ticker_doc: dict,
    state: dict,
    buy_target: float,
    effective_power: float,
) -> None:
    symbol = state["symbol"]
    quantity = _quantity_for_power(
        effective_power,
        buy_target,
        bool(ticker_doc.get("passive_fractional_shares", False)),
    )
    if quantity <= 0:
        deps.logger.warning("Passive range buy for %s has zero executable quantity", symbol)
        return

    if _is_paper(self, ticker_doc):
        order = _paper_order("BUY", quantity, buy_target)
    else:
        order = await _submit_live_limit(
            self,
            ticker_doc=ticker_doc,
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            limit_price=buy_target,
        )
        if not order:
            return

    state.update(
        {
            "phase": "BUY_WORKING",
            "cycle_id": str(uuid.uuid4()),
            "cycle_started_at": _iso_now(),
            "buy_target": buy_target,
            "sell_target": 0.0,
            "buy_order": order,
            "sell_order": None,
            "position_qty": 0.0,
            "entry_price": 0.0,
            "touch_count": 0,
        }
    )
    await _persist_state(self, state)


async def _arm_sell(
    self,
    *,
    ticker_doc: dict,
    state: dict,
    sell_target: float,
) -> None:
    quantity = _number(state.get("position_qty"))
    if quantity <= 0:
        return
    symbol = state["symbol"]
    if _is_paper(self, ticker_doc):
        order = _paper_order("SELL", quantity, sell_target)
    else:
        order = await _submit_live_limit(
            self,
            ticker_doc=ticker_doc,
            symbol=symbol,
            side="SELL",
            quantity=quantity,
            limit_price=sell_target,
        )
        if not order:
            return
    state.update(
        {
            "phase": "SELL_WORKING",
            "sell_target": sell_target,
            "sell_order": order,
            "touch_count": 0,
        }
    )
    await _persist_state(self, state)


async def _paper_fill_if_touched(
    *,
    ticker_doc: dict,
    state: dict,
    order: dict,
    quote: dict,
) -> Optional[dict]:
    side = order["side"]
    limit_price = _number(order["limit_price"])
    bid = _number(quote.get("bid"))
    ask = _number(quote.get("ask"))
    last = _number(quote.get("last"))
    touched = (ask > 0 and ask <= limit_price) if side == "BUY" else (bid > 0 and bid >= limit_price)
    if bid <= 0 or ask <= 0:
        touched = last <= limit_price if side == "BUY" else last >= limit_price

    if not touched:
        state["touch_count"] = 0
        return None

    state["touch_count"] = int(state.get("touch_count", 0)) + 1
    min_touches = max(1, int(ticker_doc.get("passive_paper_min_touches", 2) or 2))
    if state["touch_count"] < min_touches:
        return None

    result = dict(order)
    result.update(
        {
            "status": "filled",
            "filled_price": limit_price,
            "filled_quantity": _number(order.get("requested_quantity")),
        }
    )
    return result


async def _current_order_result(
    self,
    *,
    ticker_doc: dict,
    state: dict,
    order: dict,
    quote: dict,
) -> Optional[dict]:
    if _is_paper(self, ticker_doc):
        return await _paper_fill_if_touched(
            ticker_doc=ticker_doc, state=state, order=order, quote=quote
        )
    broker_id, _ = _active_broker(ticker_doc)
    return await _poll_live_order(self, broker_id, order) if broker_id else None


async def _maybe_cancel_partial(
    self,
    *,
    ticker_doc: dict,
    result: dict,
) -> bool:
    if _is_paper(self, ticker_doc):
        return True
    if not ticker_doc.get("passive_cancel_on_partial", True):
        return False
    broker_id, _ = _active_broker(ticker_doc)
    return bool(broker_id and await _cancel_live_order(self, broker_id, result))


async def _handle_buy_fill(
    self,
    *,
    ticker_doc: dict,
    state: dict,
    result: dict,
    tick_size: float,
) -> None:
    status = _status(result.get("status"))
    quantity = _number(result.get("filled_quantity"))
    price = _number(result.get("filled_price"))
    if status in _PARTIAL:
        if quantity <= 0 or price <= 0 or not await _maybe_cancel_partial(
            self, ticker_doc=ticker_doc, result=result
        ):
            return
    elif status not in _FILLED:
        return
    if quantity <= 0 or price <= 0:
        return

    symbol = state["symbol"]
    state.update(
        {
            "phase": "LONG",
            "position_qty": quantity,
            "entry_price": price,
            "buy_filled_at": _iso_now(),
            "buy_order": {**result, "status": "filled"},
            "touch_count": 0,
        }
    )
    self._positions[symbol] = {"qty": quantity, "avg_entry": price, "high": price}
    await _record_fill(
        self,
        ticker_doc=ticker_doc,
        symbol=symbol,
        side="BUY",
        price=price,
        quantity=quantity,
        target=_number(state.get("buy_target")),
        broker_result={**result, "status": "filled"},
        reason=f"[PASSIVE LIMIT] Confirmed buy fill at ${price}",
    )

    sell_target = decimal_to_float(
        bracket_target(
            price,
            ticker_doc.get("sell_offset", 0),
            is_percent=bool(ticker_doc.get("sell_percent", False)),
            tick_size=tick_size,
            side="sell",
        )
    )
    await _persist_state(self, state)
    await _arm_sell(self, ticker_doc=ticker_doc, state=state, sell_target=sell_target)


async def _handle_sell_fill(
    self,
    *,
    ticker_doc: dict,
    state: dict,
    result: dict,
) -> None:
    status = _status(result.get("status"))
    filled_quantity = _number(result.get("filled_quantity"))
    filled_price = _number(result.get("filled_price"))
    if status in _PARTIAL:
        if filled_quantity <= 0 or filled_price <= 0 or not await _maybe_cancel_partial(
            self, ticker_doc=ticker_doc, result=result
        ):
            return
    elif status not in _FILLED:
        return
    if filled_quantity <= 0 or filled_price <= 0:
        return

    symbol = state["symbol"]
    entry = _number(state.get("entry_price"))
    held = _number(state.get("position_qty"))
    sold = min(held, filled_quantity)
    pnl = (filled_price - entry) * sold
    remaining = round(max(0.0, held - sold), 8)

    await _record_fill(
        self,
        ticker_doc=ticker_doc,
        symbol=symbol,
        side="SELL",
        price=filled_price,
        quantity=sold,
        target=_number(state.get("sell_target")),
        broker_result={**result, "filled_quantity": sold, "status": "filled"},
        entry_price=entry,
        pnl=pnl,
        reason=f"[PASSIVE LIMIT] Confirmed sell fill at ${filled_price}",
    )
    await self._update_profit(symbol, round(pnl, 2), ticker_doc.get("compound_profits", True))

    state["position_qty"] = remaining
    state["sell_order"] = None
    self._positions[symbol] = {
        "qty": remaining,
        "avg_entry": entry if remaining > 0 else 0.0,
        "high": max(entry, filled_price) if remaining > 0 else 0.0,
    }

    if remaining > 0:
        state["phase"] = "LONG"
        await _persist_state(self, state)
        await _arm_sell(
            self,
            ticker_doc=ticker_doc,
            state=state,
            sell_target=_number(state.get("sell_target")),
        )
        return

    await _complete_cycle(
        self,
        ticker_doc=ticker_doc,
        state=state,
        exit_price=filled_price,
        exit_quantity=sold,
        pnl=pnl,
        exit_reason="sell_target",
    )
    state.update(
        {
            "phase": "COOLDOWN",
            "last_exit_at": _iso_now(),
            "position_qty": 0.0,
            "entry_price": 0.0,
            "touch_count": 0,
        }
    )
    self._last_exit_ts[symbol] = _now()
    await _persist_state(self, state)


async def _expire_working_buy(
    self,
    *,
    ticker_doc: dict,
    state: dict,
) -> bool:
    order = state.get("buy_order") or {}
    ttl = int(ticker_doc.get("passive_order_ttl_seconds", 300) or 0)
    if ttl <= 0 or _elapsed_seconds(order.get("submitted_at")) < ttl:
        return False
    if not _is_paper(self, ticker_doc):
        broker_id, _ = _active_broker(ticker_doc)
        if not broker_id or not await _cancel_live_order(self, broker_id, order):
            return False
    state.update({"phase": "IDLE", "buy_order": None, "touch_count": 0})
    await _persist_state(self, state)
    return True


async def _evaluate_passive_range(self, ticker_doc: dict) -> None:
    symbol = str(ticker_doc.get("symbol") or "").upper()
    if not symbol or not ticker_doc.get("enabled", False) or ticker_doc.get("auto_stopped", False):
        return
    if not self._is_ticker_market_open(ticker_doc):
        return

    price = _number(await deps.price_service.get_price(symbol))
    if price <= 0:
        return
    self._prices[symbol] = price

    needs_avg = bool(ticker_doc.get("buy_percent", False))
    avg = _number(await deps.price_service.get_avg_price(symbol, ticker_doc.get("avg_days", 30))) if needs_avg else price
    tick = infer_tick_size(price, ticker_doc.get("price_tick_size", 0))
    tick_float = decimal_to_float(tick)
    buy_target = decimal_to_float(
        bracket_target(
            avg,
            ticker_doc.get("buy_offset", 0),
            is_percent=bool(ticker_doc.get("buy_percent", False)),
            tick_size=tick,
            side="buy",
        )
    )
    absolute_sell = decimal_to_float(
        bracket_target(
            price,
            ticker_doc.get("sell_offset", 0),
            is_percent=False,
            tick_size=tick,
            side="sell",
        )
    ) if not ticker_doc.get("sell_percent", False) else 0.0
    if buy_target <= 0 or (absolute_sell > 0 and buy_target >= absolute_sell):
        deps.logger.error(
            "Passive range configuration invalid for %s: buy=%s sell=%s",
            symbol,
            buy_target,
            absolute_sell,
        )
        return

    state = await _load_state(self, symbol)
    quote = await _quote_snapshot(self, ticker_doc, symbol, price)
    broker_id, broker_allocation = _active_broker(ticker_doc)
    effective_power = broker_allocation if broker_id else _number(ticker_doc.get("base_power", 100))

    if not _is_paper(self, ticker_doc) and not broker_id:
        deps.logger.error(
            "Passive range live mode for %s requires exactly one positively allocated broker",
            symbol,
        )
        return

    phase = state.get("phase", "IDLE")
    if phase == "COOLDOWN":
        cooldown = max(0, int(ticker_doc.get("passive_reentry_seconds", 0) or 0))
        if _elapsed_seconds(state.get("last_exit_at")) < cooldown:
            return
        state["phase"] = "IDLE"
        phase = "IDLE"

    if phase == "IDLE":
        await _arm_buy(
            self,
            ticker_doc=ticker_doc,
            state=state,
            buy_target=buy_target,
            effective_power=effective_power,
        )
        phase = state.get("phase")

    if phase == "BUY_WORKING":
        if await _expire_working_buy(self, ticker_doc=ticker_doc, state=state):
            return
        order = state.get("buy_order") or {}
        result = await _current_order_result(
            self, ticker_doc=ticker_doc, state=state, order=order, quote=quote
        )
        if not result:
            await _persist_state(self, state)
            return
        status = _status(result.get("status"))
        state["buy_order"] = {**order, **result}
        if status in _FAILED and _number(result.get("filled_quantity")) <= 0:
            state.update({"phase": "IDLE", "buy_order": None, "touch_count": 0})
            await _persist_state(self, state)
            return
        await _handle_buy_fill(
            self,
            ticker_doc=ticker_doc,
            state=state,
            result={**order, **result},
            tick_size=tick_float,
        )
        await _persist_state(self, state)
        return

    if phase == "LONG":
        sell_target = absolute_sell or decimal_to_float(
            bracket_target(
                state.get("entry_price", price),
                ticker_doc.get("sell_offset", 0),
                is_percent=True,
                tick_size=tick,
                side="sell",
            )
        )
        await _arm_sell(self, ticker_doc=ticker_doc, state=state, sell_target=sell_target)
        return

    if phase == "SELL_WORKING":
        order = state.get("sell_order") or {}
        result = await _current_order_result(
            self, ticker_doc=ticker_doc, state=state, order=order, quote=quote
        )
        if not result:
            await _persist_state(self, state)
            return
        status = _status(result.get("status"))
        state["sell_order"] = {**order, **result}
        if status in _FAILED and _number(result.get("filled_quantity")) <= 0:
            state.update({"phase": "LONG", "sell_order": None, "touch_count": 0})
            await _persist_state(self, state)
            return
        await _handle_sell_fill(
            self,
            ticker_doc=ticker_doc,
            state=state,
            result={**order, **result},
        )
        await _persist_state(self, state)


async def _patched_evaluate_ticker(self, ticker_doc: dict):
    if ticker_doc.get("passive_range_enabled", False):
        return await _evaluate_passive_range(self, ticker_doc)
    return await _ORIGINAL_EVALUATE_TICKER(self, ticker_doc)


TickerEvaluationMixin.evaluate_ticker = _patched_evaluate_ticker
