from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError


class OrderLifecycleMixin:
    async def manual_sell(self, symbol: str, order_type: str, limit_price: float = 0) -> dict:
        """Execute a manual sell from the Positions tab.
        order_type: 'market' (immediate) or 'limit' (pending).
        Returns trade result dict."""
        sym = symbol.upper()
        pos = self._positions.get(sym)
        if not pos or pos["qty"] <= 0:
            return {"error": f"No open position for {sym}"}

        qty = pos["qty"]
        entry = pos["avg_entry"]

        if order_type == "limit" and limit_price > 0:
            # Store as pending limit sell — engine will execute when price >= limit_price
            self._pending_sells[sym] = {
                "limit_price": limit_price,
                "qty": qty,
                "entry": entry,
            }
            await deps.ws_manager.broadcast({
                "type": "PENDING_SELL",
                "symbol": sym,
                "limit_price": limit_price,
                "qty": qty,
            })
            deps.logger.info(f"PENDING LIMIT SELL: {sym} @ ${limit_price:.2f} x{qty:.4f}")
            return {
                "status": "pending",
                "symbol": sym,
                "order_type": "limit",
                "limit_price": limit_price,
                "quantity": qty,
            }

        # Market sell — execute immediately
        price = self._prices.get(sym) or await deps.price_service.get_price(sym)
        return await self._execute_sell(sym, price, qty, entry, "MARKET", "Manual market sell")

    async def cancel_pending_sell(self, symbol: str) -> dict:
        """Cancel a pending limit sell order."""
        sym = symbol.upper()
        removed = self._pending_sells.pop(sym, None)
        if removed:
            await deps.ws_manager.broadcast({"type": "PENDING_SELL_CANCELLED", "symbol": sym})
            return {"status": "cancelled", "symbol": sym}
        return {"error": f"No pending sell for {sym}"}

    async def check_pending_sells(self):
        """Called by the trading loop — execute pending limit sells when price is reached."""
        to_remove = []
        for sym, order in self._pending_sells.items():
            price = self._prices.get(sym, 0)
            if price >= order["limit_price"]:
                await self._execute_sell(
                    sym, price, order["qty"], order["entry"],
                    "LIMIT", f"Manual limit sell filled @ ${price:.2f} (target ${order['limit_price']:.2f})"
                )
                to_remove.append(sym)
        for sym in to_remove:
            self._pending_sells.pop(sym, None)

    async def _execute_sell(self, sym: str, price: float, qty: float, entry: float, order_type: str, reason: str) -> dict:
        """Shared sell execution logic for both manual and engine-driven sells."""
        pnl = round((price - entry) * qty, 2)
        is_paper = self.simulate_24_7
        ticker_doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
        broker_ids = ticker_doc.get("broker_ids", []) if ticker_doc else []
        broker_allocs = ticker_doc.get("broker_allocations", {}) if ticker_doc else {}
        broker_results = []

        if not is_paper and broker_ids:
            broker_results = await deps.broker_mgr.place_orders_for_ticker(
                broker_ids=broker_ids, allocations=broker_allocs,
                order_template={
                    "symbol": sym, "side": "SELL", "order_type": order_type,
                    "price": price, "quantity": qty,
                },
            )

        trade = TradeRecord(
            symbol=sym, side="SELL", price=price, quantity=qty,
            reason=reason, pnl=pnl,
            order_type=order_type,
            entry_price=entry,
            total_value=round(price * qty, 2),
            buy_power=ticker_doc.get("base_power", 0) if ticker_doc else 0,
            trading_mode="paper" if is_paper or not broker_ids else "live",
            broker_results=broker_results,
        )
        await self._record_trade(trade)
        self._positions[sym] = {"qty": 0, "avg_entry": 0, "high": 0}
        self._trailing_highs.pop(sym, None)
        compound = ticker_doc.get("compound_profits", True) if ticker_doc else True
        await self._update_profit(sym, pnl, compound)

        return {
            "status": "executed",
            "symbol": sym,
            "order_type": order_type.lower(),
            "price": price,
            "quantity": qty,
            "pnl": pnl,
            "total_value": round(price * qty, 2),
            "trading_mode": trade.trading_mode,
        }
