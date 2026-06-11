"""Shared bot/watchlist state snapshot builder."""
from __future__ import annotations

from typing import Any

import deps


async def build_bot_snapshot() -> dict[str, Any]:
    """Return the state needed to render the Watchlist without WebSocket state."""
    tickers = await deps.db.tickers.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)

    prices: dict[str, float] = {}
    price_sources: dict[str, str] = {}
    price_errors: dict[str, str] = {}
    for ticker in tickers:
        symbol = ticker.get("symbol")
        if not symbol:
            continue
        try:
            prices[symbol] = await deps.price_service.get_price(symbol)
        except Exception as exc:
            price_errors[symbol] = str(exc)
            deps.logger.warning("Price lookup failed for %s while building bot snapshot: %s", symbol, exc)
        price_sources[symbol] = deps.price_service.get_price_source(symbol)

    positions = {}
    for symbol, pos in deps.engine._positions.items():
        if pos.get("qty", 0) > 0:
            current_price = prices.get(symbol, pos.get("avg_entry", 0))
            market_value = round(current_price * pos["qty"], 2)
            positions[symbol] = {
                "symbol": symbol,
                "quantity": pos["qty"],
                "avg_entry": pos["avg_entry"],
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": round((current_price - pos["avg_entry"]) * pos["qty"], 2),
            }

    profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
    profits = {profit["symbol"]: profit.get("total_pnl", 0) for profit in profits_list}

    cash_doc = await deps.db.settings.find_one({"key": "cash_reserve"}, {"_id": 0})
    cash_reserve = round(cash_doc.get("value", 0), 2) if cash_doc else 0

    balance_doc = await deps.db.settings.find_one({"key": "account_balance"}, {"_id": 0})
    account_balance = round(balance_doc.get("value", 0), 2) if balance_doc else 0
    allocated = round(sum(ticker.get("base_power", 0) for ticker in tickers), 2)

    inc_doc = await deps.db.settings.find_one({"key": "increment_step"}, {"_id": 0})
    dec_doc = await deps.db.settings.find_one({"key": "decrement_step"}, {"_id": 0})
    replay_doc = await deps.db.settings.find_one({"key": "active_replay"}, {"_id": 0})

    trades = await deps.db.trades.find({}, {"_id": 0}).sort("timestamp", -1).limit(50).to_list(50)

    return {
        "tickers": tickers,
        "prices": prices,
        "price_sources": price_sources,
        "price_errors": price_errors,
        "positions": positions,
        "profits": profits,
        "trades": trades,
        "cash_reserve": cash_reserve,
        "account_balance": account_balance,
        "allocated": allocated,
        "available": round(account_balance - allocated, 2),
        "increment_step": inc_doc.get("value", 0.5) if inc_doc else 0.5,
        "decrement_step": dec_doc.get("value", 0.5) if dec_doc else 0.5,
        "paused": deps.engine.paused,
        "running": deps.engine.running,
        "market_open": deps.engine.is_market_open(),
        "simulate_24_7": deps.engine.simulate_24_7,
        "market_hours_only": deps.engine.market_hours_only,
        "live_during_market_hours": deps.engine.live_during_market_hours,
        "paper_after_hours": deps.engine.paper_after_hours,
        "replay": replay_doc.get("value") if replay_doc else None,
    }
