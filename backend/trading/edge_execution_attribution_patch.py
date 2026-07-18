"""Durable execution-style attribution and post-fill movement marking."""
from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Dict

import deps
from trading import edge_entry_profitability_patch as entry_runtime
from trading import live_pretrade_patch as pretrade
from trading.edge_execution_style import execution_attribution, finite, positive
from trading.ticker_evaluation import TickerEvaluationMixin
from trading.trade_accounting import TradeAccountingMixin


_ORIGINAL_PERSIST_RESULTS = pretrade._persist_results
_ORIGINAL_RECORD_TRADE = TradeAccountingMixin._record_trade
_ORIGINAL_EVALUATE_TICKER = TickerEvaluationMixin.evaluate_ticker
_PATCH_MARKER = "_pulse_edge_execution_attribution_v1"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _watches(engine: Any) -> dict[str, list[Dict[str, Any]]]:
    value = getattr(engine, "_edge_execution_attribution_watches", None)
    if not isinstance(value, dict):
        value = {}
        setattr(engine, "_edge_execution_attribution_watches", value)
    return value


def _runtime(engine: Any, symbol: str) -> Dict[str, Any] | None:
    return entry_runtime._runtime_policies(engine).get(symbol.upper())


def _result_fill(result: Dict[str, Any]) -> tuple[float, float]:
    quantity = 0.0
    price = 0.0
    for key in ("filled_quantity", "filled_qty", "cumulative_filled_quantity"):
        quantity = finite(result.get(key))
        if quantity > 0:
            break
    for key in ("avg_fill_price", "filled_price", "average_fill_price"):
        price = finite(result.get(key))
        if price > 0:
            break
    return quantity, price


async def _persist_results_with_style(self: Any, **kwargs: Any) -> None:
    await _ORIGINAL_PERSIST_RESULTS(self, **kwargs)
    results = list(kwargs.get("results") or [])
    symbol = str(kwargs.get("symbol") or "").upper()
    runtime = _runtime(self, symbol)
    filled_quantity = 0.0
    filled_notional = 0.0
    terminal_statuses: list[str] = []
    for result in results:
        quantity, price = _result_fill(result)
        filled_quantity += quantity
        filled_notional += quantity * price
        terminal_statuses.append(str(result.get("status") or "unknown").lower())
    if isinstance(runtime, dict):
        runtime["broker_outcome"] = {
            "filled_quantity": round(filled_quantity, 8),
            "fill_price": round(filled_notional / filled_quantity, 8) if filled_quantity > 0 and filled_notional > 0 else 0.0,
            "statuses": terminal_statuses,
            "results": results,
            "recorded_at": _iso_now(),
        }

    collection = getattr(deps.db, "broker_orders", None)
    if collection is None:
        return
    intent_key = str(kwargs.get("intent_key") or "")
    for result in results:
        style = result.get("execution_style")
        if not style:
            continue
        broker_id = str(result.get("broker_id") or "")
        try:
            await collection.update_many(
                {"intent_key": intent_key, "broker_id": broker_id},
                {
                    "$set": {
                        "execution_style": style,
                        "execution_style_selection": result.get("execution_style_selection"),
                        "limit_price": result.get("limit_price"),
                        "stop_price": result.get("stop_price"),
                        "timeout_seconds": result.get("timeout_seconds"),
                        "arrival_price": result.get("arrival_price"),
                        "attribution_updated_at": _iso_now(),
                    }
                },
            )
        except Exception:
            # Broker truth was already persisted; attribution is best-effort and
            # must never make a submitted order retry.
            pass


def _filled_attribution(runtime: Dict[str, Any], trade: Any) -> Dict[str, Any]:
    selection = runtime.get("execution_style") if isinstance(runtime.get("execution_style"), dict) else {}
    return execution_attribution(
        selection,
        status="filled",
        fill_price=finite(getattr(trade, "price", 0.0)),
        filled_quantity=finite(getattr(trade, "quantity", 0.0)),
    )


async def _record_trade_with_execution_attribution(self: Any, trade: Any):
    side = str(getattr(trade, "side", "")).upper()
    runtime = _runtime(self, str(getattr(trade, "symbol", ""))) if side == "BUY" else None
    if isinstance(runtime, dict):
        selection = runtime.get("execution_style") if isinstance(runtime.get("execution_style"), dict) else {}
        trade.execution_style = str(selection.get("style") or "")
        if selection.get("order_type"):
            trade.order_type = str(selection["order_type"])

    # The inner broker-truth wrapper normalizes price and quantity before the
    # base recorder persists the trade. Compute final attribution afterwards.
    result = await _ORIGINAL_RECORD_TRADE(self, trade)

    if isinstance(runtime, dict):
        attribution = _filled_attribution(runtime, trade)
        trade.execution_attribution = attribution
        runtime["attribution"] = attribution
        try:
            await deps.db.trades.update_one(
                {"id": str(getattr(trade, "id", ""))},
                {"$set": {"execution_style": trade.execution_style, "execution_attribution": attribution, "order_type": trade.order_type}},
            )
        except Exception:
            pass

    if isinstance(runtime, dict) and positive(getattr(trade, "price", 0.0)) is not None:
        selection = runtime.get("execution_style") if isinstance(runtime.get("execution_style"), dict) else {}
        horizons = [
            max(1, int(finite(value)))
            for value in selection.get("post_fill_horizons_seconds", [])
            if finite(value) > 0
        ]
        watch = {
            "contract_version": "pulse.execution_attribution.watch.v1",
            "intent_id": runtime.get("intent_id"),
            "trade_id": str(getattr(trade, "id", "")),
            "symbol": str(getattr(trade, "symbol", "")).upper(),
            "style": selection.get("style"),
            "fill_price": finite(getattr(trade, "price", 0.0)),
            "fill_quantity": finite(getattr(trade, "quantity", 0.0)),
            "filled_at_epoch": time.time(),
            "filled_at": _iso_now(),
            "horizons_seconds": sorted(set(horizons or [30, 60, 300])),
            "marks": {},
            "selection": selection,
        }
        _watches(self).setdefault(watch["symbol"], []).append(watch)
    return result


def mark_post_fill_movement(
    watch: Dict[str, Any],
    *,
    current_price: float,
    now_epoch: float | None = None,
) -> tuple[Dict[str, Any], bool]:
    price = positive(current_price)
    fill = positive(watch.get("fill_price"))
    if price is None or fill is None:
        return watch, False
    now_value = float(now_epoch if now_epoch is not None else time.time())
    elapsed = max(0.0, now_value - finite(watch.get("filled_at_epoch"), now_value))
    marks = dict(watch.get("marks") or {})
    changed = False
    for horizon in watch.get("horizons_seconds", []):
        key = str(int(horizon))
        if key in marks or elapsed < float(horizon):
            continue
        marks[key] = {
            "horizon_seconds": int(horizon),
            "price": round(price, 8),
            "move_bps": round(((price - fill) / fill) * 10000.0, 4),
            "marked_at": _iso_now(),
            "elapsed_seconds": round(elapsed, 3),
        }
        changed = True
    watch["marks"] = marks
    watch["complete"] = len(marks) >= len(watch.get("horizons_seconds", []))
    return watch, changed


async def _persist_watch(engine: Any, watch: Dict[str, Any]) -> None:
    attribution = execution_attribution(
        watch.get("selection") or {},
        status="filled",
        fill_price=watch.get("fill_price"),
        filled_quantity=watch.get("fill_quantity"),
        post_fill_prices={key: value.get("price") for key, value in (watch.get("marks") or {}).items()},
    )
    attribution["post_fill_marks"] = dict(watch.get("marks") or {})
    attribution["post_fill_complete"] = bool(watch.get("complete"))
    try:
        collection = getattr(deps.db, "execution_attributions", None)
        if collection is not None:
            await collection.update_one(
                {"intent_id": watch.get("intent_id")},
                {"$set": {"symbol": watch.get("symbol"), "trade_id": watch.get("trade_id"), "attribution": attribution}},
                upsert=True,
            )
        await deps.db.tickers.update_one(
            {"symbol": watch.get("symbol")},
            {"$set": {"edge_execution_attribution": attribution}},
        )
        if watch.get("trade_id"):
            await deps.db.trades.update_one(
                {"id": watch.get("trade_id")},
                {"$set": {"execution_attribution": attribution, "execution_style": watch.get("style")}},
            )
    except Exception:
        pass


async def _evaluate_ticker_with_post_fill_marks(self: TickerEvaluationMixin, ticker_doc: dict):
    result = await _ORIGINAL_EVALUATE_TICKER(self, ticker_doc)
    symbol = str((ticker_doc or {}).get("symbol") or "").upper()
    watches = _watches(self).get(symbol, [])
    if not watches:
        return result
    price = finite(getattr(self, "_prices", {}).get(symbol))
    retained = []
    for watch in watches:
        watch, changed = mark_post_fill_movement(watch, current_price=price)
        if changed:
            await _persist_watch(self, watch)
        if not watch.get("complete"):
            retained.append(watch)
    if retained:
        _watches(self)[symbol] = retained
    else:
        _watches(self).pop(symbol, None)
    return result


def _safe_latest_fill(engine: Any, symbol: str) -> tuple[float, float]:
    trade = getattr(engine, "_last_broker_truth_trade", None)
    if (
        trade is not None
        and str(getattr(trade, "symbol", "")).upper() == symbol.upper()
        and str(getattr(trade, "side", "")).upper() == "BUY"
    ):
        return finite(getattr(trade, "price", 0.0)), finite(getattr(trade, "quantity", 0.0))
    runtime = _runtime(engine, symbol) or {}
    broker = runtime.get("broker_outcome") if isinstance(runtime.get("broker_outcome"), dict) else {}
    return finite(broker.get("fill_price")), finite(broker.get("filled_quantity"))


pretrade._persist_results = _persist_results_with_style
TradeAccountingMixin._record_trade = _record_trade_with_execution_attribution
TickerEvaluationMixin.evaluate_ticker = _evaluate_ticker_with_post_fill_marks
entry_runtime._latest_fill = _safe_latest_fill
