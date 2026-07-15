"""Durable reconciliation for non-terminal live broker orders."""

from __future__ import annotations

from datetime import datetime, timezone

import deps
from schemas import TradeRecord
from trading.broker_execution import BrokerExecutionMixin
from trading.ticker_evaluation import TickerEvaluationMixin
from trading.trade_accounting import TradeAccountingMixin

try:
    from brokers.alpaca_adapter import AlpacaAdapter
except ImportError:  # pragma: no cover
    AlpacaAdapter = None


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


async def _alpaca_get_order_status(self, broker_order_id: str) -> dict:
    if not broker_order_id:
        return {"status": "error", "error": "missing broker order id"}
    session = await self._get_session()
    async with session.get(
        f"{self._base_url()}/v2/orders/{broker_order_id}",
        headers=self._headers(),
    ) as response:
        data = await response.json()
        if response.status != 200:
            return {
                "status": "error",
                "broker_order_id": broker_order_id,
                "error": data.get("message", f"HTTP {response.status}"),
            }
        return {
            "status": str(data.get("status") or "unknown").lower(),
            "broker_order_id": str(data.get("id") or broker_order_id),
            "filled_quantity": _num(data.get("filled_qty")),
            "filled_price": _num(data.get("filled_avg_price")),
            "error": str(data.get("reject_reason") or data.get("cancel_reason") or ""),
        }


async def _apply_fill_delta(self, order_doc: dict, broker_update: dict) -> float:
    cumulative_qty = _num(broker_update.get("filled_quantity"))
    cumulative_avg = _num(broker_update.get("filled_price") or broker_update.get("avg_fill_price"))
    applied_qty = _num(order_doc.get("applied_quantity"))
    applied_notional = _num(order_doc.get("applied_notional"))
    delta_qty = round(max(0.0, cumulative_qty - applied_qty), 8)
    if delta_qty <= 0:
        return 0.0

    cumulative_notional = cumulative_qty * cumulative_avg
    delta_notional = max(0.0, cumulative_notional - applied_notional)
    delta_price = delta_notional / delta_qty if delta_notional > 0 else cumulative_avg
    if delta_price <= 0:
        raise RuntimeError(
            f"Broker fill for {order_doc.get('symbol')} has quantity but no usable fill price"
        )

    symbol = str(order_doc.get("symbol") or "").upper()
    side = str(order_doc.get("side") or "").upper()
    broker_id = str(order_doc.get("broker_id") or "")
    broker_order_id = str(order_doc.get("broker_order_id") or "")
    current = dict(getattr(self, "_positions", {}).get(symbol, {}) or {})
    current_qty = _num(current.get("qty"))
    current_entry = _num(current.get("avg_entry"))

    result = {
        "broker_id": broker_id,
        "status": "filled",
        "broker_order_id": broker_order_id,
        "filled_quantity": delta_qty,
        "filled_price": delta_price,
        "ledger_reconciliation": True,
    }

    if side == "BUY":
        new_qty = round(current_qty + delta_qty, 8)
        new_entry = (
            ((current_qty * current_entry) + (delta_qty * delta_price)) / new_qty
            if new_qty > 0
            else 0.0
        )
        trade = TradeRecord(
            symbol=symbol,
            side="BUY",
            price=delta_price,
            quantity=delta_qty,
            reason="Broker reconciliation fill",
            order_type=str(order_doc.get("order_type") or ""),
            rule_mode="BROKER_RECONCILIATION",
            total_value=round(delta_qty * delta_price, 2),
            buy_power=round(delta_qty * delta_price, 2),
            trading_mode="live",
            broker_results=[result],
        )
        await self._record_trade(trade)
        self._positions[symbol] = {
            "qty": new_qty,
            "avg_entry": round(new_entry, 8),
            "high": max(_num(current.get("high")), delta_price, new_entry),
        }
    elif side == "SELL":
        if current_qty + 1e-8 < delta_qty:
            raise RuntimeError(
                f"Broker sell fill exceeds local reconciled position for {symbol}: "
                f"{delta_qty} > {current_qty}"
            )
        realized_qty = min(current_qty, delta_qty)
        pnl = round((delta_price - current_entry) * realized_qty, 2)
        trade = TradeRecord(
            symbol=symbol,
            side="SELL",
            price=delta_price,
            quantity=realized_qty,
            reason="Broker reconciliation fill",
            pnl=pnl,
            order_type=str(order_doc.get("order_type") or ""),
            rule_mode="BROKER_RECONCILIATION",
            entry_price=current_entry,
            total_value=round(realized_qty * delta_price, 2),
            trading_mode="live",
            broker_results=[{**result, "filled_quantity": realized_qty}],
        )
        await self._record_trade(trade)
        remaining = round(max(0.0, current_qty - realized_qty), 8)
        if remaining > 0:
            self._positions[symbol] = {
                "qty": remaining,
                "avg_entry": current_entry,
                "high": _num(current.get("high")),
            }
        else:
            self._positions[symbol] = {"qty": 0.0, "avg_entry": 0.0, "high": 0.0}
            self._trailing_highs.pop(symbol, None)
        ticker = await deps.db.tickers.find_one({"symbol": symbol}, {"_id": 0})
        compound = bool((ticker or {}).get("compound_profits", True))
        await self._update_profit(symbol, pnl, compound)
    else:
        raise RuntimeError(f"Unsupported broker-order side: {side}")

    await deps.db.broker_orders.update_one(
        {
            "intent_key": order_doc.get("intent_key"),
            "broker_id": broker_id,
            "durable_order_id": order_doc.get("durable_order_id"),
        },
        {
            "$set": {
                "applied_quantity": cumulative_qty,
                "applied_notional": cumulative_notional,
                "last_applied_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    await self.save_state()
    return delta_qty


async def _reconcile_live_orders(self, symbol: str | None = None) -> dict:
    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return {"checked": 0, "applied": 0, "unresolved": 0}

    query = {
        "$or": [
            {
                "status": {
                    "$in": sorted(
                        self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES
                    )
                }
            },
            {
                "status": {"$in": sorted(self._BROKER_CONFIRMED_STATUSES)},
                "$expr": {
                    "$gt": [
                        {"$ifNull": ["$filled_quantity", 0]},
                        {"$ifNull": ["$applied_quantity", 0]},
                    ]
                },
            },
        ]
    }
    if symbol:
        query["symbol"] = symbol.upper()

    docs = await collection.find(query, {"_id": 0}).sort("created_at", 1).to_list(200)
    applied = 0.0
    unresolved = 0

    for doc in docs:
        broker_id = str(doc.get("broker_id") or "")
        order_id = str(doc.get("broker_order_id") or "")
        adapter = deps.broker_mgr.get_adapter(broker_id) if hasattr(deps.broker_mgr, "get_adapter") else None
        update = {
            "status": str(doc.get("status") or "unknown").lower(),
            "broker_order_id": order_id,
            "filled_quantity": _num(doc.get("filled_quantity")),
            "filled_price": _num(doc.get("avg_fill_price")),
            "error": str(doc.get("error") or ""),
        }

        if update["status"] in (self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES):
            if not adapter or not hasattr(adapter, "get_order_status"):
                unresolved += 1
                continue
            update = await adapter.get_order_status(order_id)
            await collection.update_one(
                {
                    "intent_key": doc.get("intent_key"),
                    "broker_id": broker_id,
                    "durable_order_id": doc.get("durable_order_id"),
                },
                {
                    "$set": {
                        "status": str(update.get("status") or "unknown").lower(),
                        "filled_quantity": _num(update.get("filled_quantity")),
                        "avg_fill_price": _num(
                            update.get("filled_price") or update.get("avg_fill_price")
                        ),
                        "error": str(update.get("error") or ""),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )

        status = str(update.get("status") or "").lower()
        if status in self._BROKER_PARTIAL_STATUSES | self._BROKER_CONFIRMED_STATUSES:
            applied += await _apply_fill_delta(self, doc, update)
        elif status in self._BROKER_PENDING_STATUSES:
            unresolved += 1

    return {"checked": len(docs), "applied": applied, "unresolved": unresolved}


async def _has_unresolved_live_order(self, symbol: str) -> bool:
    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return False
    doc = await collection.find_one(
        {
            "symbol": symbol.upper(),
            "status": {
                "$in": sorted(
                    self._BROKER_PENDING_STATUSES | self._BROKER_PARTIAL_STATUSES
                )
            },
        },
        {"_id": 1},
    )
    return bool(doc)


_current_evaluate_ticker = TickerEvaluationMixin.evaluate_ticker
_current_record_trade = TradeAccountingMixin._record_trade


async def _evaluate_ticker_after_reconciliation(self, ticker_doc: dict):
    symbol = str(ticker_doc.get("symbol") or "").upper()
    await _reconcile_live_orders(self, symbol)
    if await _has_unresolved_live_order(self, symbol):
        deps.logger.info(
            "[%s] evaluation deferred while broker order awaits reconciliation",
            symbol,
        )
        return
    return await _current_evaluate_ticker(self, ticker_doc)


async def _record_trade_and_mark_applied(self, trade):
    result = await _current_record_trade(self, trade)
    if str(getattr(trade, "trading_mode", "")).lower() != "live":
        return result

    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return result
    now = datetime.now(timezone.utc).isoformat()
    for broker_result in list(getattr(trade, "broker_results", None) or []):
        if broker_result.get("ledger_reconciliation"):
            continue
        broker_order_id = str(
            broker_result.get("broker_order_id")
            or broker_result.get("order_id")
            or broker_result.get("external_id")
            or ""
        )
        if not broker_order_id:
            continue
        qty = _num(broker_result.get("filled_quantity") or broker_result.get("filled_qty"))
        price = _num(
            broker_result.get("filled_price")
            or broker_result.get("avg_fill_price")
            or broker_result.get("average_fill_price")
        )
        await collection.update_many(
            {"broker_order_id": broker_order_id},
            {
                "$set": {
                    "applied_quantity": qty,
                    "applied_notional": qty * price,
                    "last_applied_at": now,
                }
            },
        )
    return result


if AlpacaAdapter is not None:
    AlpacaAdapter.get_order_status = _alpaca_get_order_status

BrokerExecutionMixin.reconcile_live_orders = _reconcile_live_orders
BrokerExecutionMixin.has_unresolved_live_order = _has_unresolved_live_order
TickerEvaluationMixin.evaluate_ticker = _evaluate_ticker_after_reconciliation
TradeAccountingMixin._record_trade = _record_trade_and_mark_applied
