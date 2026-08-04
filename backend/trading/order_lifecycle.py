from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError
from trading.broker_execution import LiveOrderExecutionError


class OrderLifecycleMixin:
    async def execute_buy(self, symbol: str, price: float) -> dict:
        """Execute an immediate buy from an external control path such as Edge."""
        sym = symbol.upper()
        try:
            exec_price = float(price)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid buy price for {sym}")
        if exec_price <= 0:
            raise ValueError(f"Invalid buy price for {sym}")

        pos = self._positions.get(sym, {})
        if float(pos.get("qty", 0) or 0) > 0:
            raise ValueError(f"Open position already exists for {sym}")

        ticker_doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
        if not ticker_doc:
            raise ValueError(f"{sym} is not configured")

        remaining = self._reentry_cooldown_remaining(sym, ticker_doc)
        if remaining > 0:
            raise ValueError(f"{sym} re-entry cooldown active for {remaining:.0f}s")

        broker_ids = ticker_doc.get("broker_ids", []) or []
        broker_allocs = ticker_doc.get("broker_allocations", {}) or {}
        is_paper = self.is_paper_trading()
        should_place_broker_order = self._should_place_broker_orders(broker_ids)
        effective_power = float(ticker_doc.get("base_power", 0) or 0)
        order_power = effective_power
        if should_place_broker_order:
            active_allocations = [
                max(0.0, float((broker_allocs or {}).get(broker_id, 0) or 0))
                for broker_id in broker_ids
            ]
            live_power = round(sum(active_allocations), 8)
            if live_power <= 0:
                raise ValueError(f"No live broker buying power configured for {sym}")
            if live_power > effective_power:
                raise ValueError(
                    f"Live broker allocations for {sym} exceed ticker buy power "
                    f"(${live_power:.2f} > ${effective_power:.2f})"
                )
            order_power = live_power

        qty = round(order_power / exec_price, 4) if exec_price > 0 else 0
        if qty <= 0:
            raise ValueError(f"No buying power configured for {sym}")

        broker_results = []

        try:
            broker_results = await self._place_live_order_or_raise(
                sym=sym,
                broker_ids=broker_ids,
                broker_allocs=broker_allocs,
                action_label="EDGE_BUY",
                order_template={
                    "symbol": sym,
                    "side": "BUY",
                    "order_type": "MARKET",
                    "price": exec_price,
                },
            )
        except LiveOrderExecutionError as exc:
            deps.logger.warning(str(exc))
            raise RuntimeError(str(exc)) from exc

        if broker_results:
            broker_filled_qty = self._broker_results_filled_quantity(broker_results)
            if broker_filled_qty > 0:
                qty = round(broker_filled_qty, 4)
                order_power = round(exec_price * qty, 2)

        self._prices[sym] = exec_price
        self._positions[sym] = {"qty": qty, "avg_entry": exec_price, "high": exec_price}
        trade = TradeRecord(
            symbol=sym,
            side="BUY",
            price=exec_price,
            quantity=qty,
            reason="Edge handoff buy",
            order_type="MARKET",
            rule_mode="EDGE",
            target_price=exec_price,
            total_value=round(exec_price * qty, 2),
            buy_power=order_power,
            trading_mode="live",
            broker_results=broker_results,
        )
        await self._record_trade(trade)

        return {
            "status": "executed",
            "symbol": sym,
            "order_type": "market",
            "price": exec_price,
            "quantity": qty,
            "total_value": round(exec_price * qty, 2),
            "trading_mode": trade.trading_mode,
        }

    async def execute_sell(self, symbol: str, price: float = None) -> dict:
        """Execute an immediate sell from an external control path such as Edge."""
        sym = symbol.upper()
        pos = self._positions.get(sym)
        if not pos or float(pos.get("qty", 0) or 0) <= 0:
            raise ValueError(f"No open position for {sym}")

        qty = float(pos.get("qty", 0) or 0)
        entry = float(pos.get("avg_entry", 0) or 0)
        if price is None:
            exec_price = self._prices.get(sym) or await deps.price_service.get_price(sym)
        else:
            try:
                exec_price = float(price)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid sell price for {sym}")
        if exec_price <= 0:
            raise ValueError(f"Invalid sell price for {sym}")

        self._prices[sym] = exec_price
        return await self._execute_sell(sym, exec_price, qty, entry, "MARKET", "Edge handoff sell")

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
            await self._persist_trade_state()
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
            await self._persist_trade_state()
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
        if to_remove:
            await self._persist_trade_state()

    async def _execute_sell(self, sym: str, price: float, qty: float, entry: float, order_type: str, reason: str) -> dict:
        """Shared sell execution logic for both manual and engine-driven sells."""
        is_paper = self.is_paper_trading()
        ticker_doc = await deps.db.tickers.find_one({"symbol": sym}, {"_id": 0})
        broker_ids = ticker_doc.get("broker_ids", []) if ticker_doc else []
        broker_allocs = ticker_doc.get("broker_allocations", {}) if ticker_doc else {}
        broker_results = []

        try:
            broker_results = await self._place_live_order_or_raise(
                sym=sym,
                broker_ids=broker_ids,
                broker_allocs=broker_allocs,
                action_label=f"{order_type}_SELL",
                order_template={
                    "symbol": sym, "side": "SELL", "order_type": order_type,
                    "price": price, "quantity": qty,
                },
            )
        except LiveOrderExecutionError as exc:
            deps.logger.warning(str(exc))
            raise RuntimeError(str(exc)) from exc

        executed_qty = qty
        if broker_results:
            broker_filled_qty = self._broker_results_filled_quantity(broker_results)
            if broker_filled_qty > 0:
                executed_qty = min(qty, round(broker_filled_qty, 4))
        pnl = round((price - entry) * executed_qty, 2)

        trade = TradeRecord(
            symbol=sym, side="SELL", price=price, quantity=executed_qty,
            reason=reason, pnl=pnl,
            order_type=order_type,
            entry_price=entry,
            total_value=round(price * executed_qty, 2),
            buy_power=ticker_doc.get("base_power", 0) if ticker_doc else 0,
            trading_mode="live",
            broker_results=broker_results,
        )
        await self._record_trade(trade)
        remaining_qty = round(max(0.0, qty - executed_qty), 4)
        if remaining_qty > 0:
            current_pos = self._positions.get(sym, {})
            self._positions[sym] = {
                "qty": remaining_qty,
                "avg_entry": entry,
                "high": current_pos.get("high", price),
            }
        else:
            self._positions[sym] = {"qty": 0, "avg_entry": 0, "high": 0}
            self._trailing_highs.pop(sym, None)
        compound = ticker_doc.get("compound_profits", True) if ticker_doc else True
        await self._update_profit(sym, pnl, compound)

        return {
            "status": "executed",
            "symbol": sym,
            "order_type": order_type.lower(),
            "price": price,
            "quantity": executed_qty,
            "pnl": pnl,
            "total_value": round(price * executed_qty, 2),
            "trading_mode": trade.trading_mode,
        }
