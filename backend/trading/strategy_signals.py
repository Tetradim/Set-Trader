from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError


class StrategySignalMixin:
    async def _run_strategy_signal(
        self,
        strategy,
        ticker_doc: dict,
        sym: str,
        price: float,
        pos: dict,
        entry: float,
        effective_power: float,
        broker_ids: list,
        broker_allocs: dict,
        sell_target: float,
        stop_target: float,
        compound: bool,
        avg: float,
    ) -> bool:
        """
        Call a signal strategy and execute the resulting action.
        Returns True if the signal was handled (caller should skip bracket logic).
        Returns False to fall through to bracket logic.
        """
        if not await strategy.validate_ticker(ticker_doc):
            return False

        params = strategy.get_params(ticker_doc)

        try:
            market_data   = await deps.price_service.get_enriched_market_data(ticker_doc)
            market_status = self._get_market(ticker_doc).to_dict()
            signal = await strategy.generate_signals(
                ticker_doc, price, market_data, market_status, broker_allocs, params
            )
        except Exception as exc:
            deps.logger.error(
                f"Strategy '{strategy.metadata.name}' error on {sym}: {exc}", exc_info=True
            )
            return False  # safe fallback to bracket logic

        if signal is None:
            return False  # strategy deferred — use brackets

        if signal.action == "HOLD":
            deps.logger.debug(f"[{sym}] Strategy HOLD (confidence={signal.confidence:.2f})")
            return True   # explicitly hold — skip everything this cycle

        is_paper = self.is_paper_trading()

        # --- BUY ---
        if signal.action == "BUY" and pos["qty"] == 0:
            if ticker_doc.get("buying_paused", False):
                deps.logger.debug(f"[{sym}] Strategy BUY blocked because buying is paused")
                return True
            if self._is_reentry_cooldown_active(sym, ticker_doc):
                return True
            qty = round(effective_power / price, 4) if price > 0 else 0
            if qty <= 0:
                return False
            broker_results = []
            if not is_paper and broker_ids:
                broker_results = await deps.broker_mgr.place_orders_for_ticker(
                    broker_ids=broker_ids, allocations=broker_allocs,
                    order_template={"symbol": sym, "side": "BUY", "order_type": "MARKET", "price": price},
                )
                if any(r.get("status") == "error" for r in broker_results) and broker_results:
                    all_failed = all(r.get("status") == "error" for r in broker_results)
                    if all_failed:
                        return False
            self._positions[sym] = {"qty": qty, "avg_entry": price}
            trade = TradeRecord(
                symbol=sym, side="BUY", price=price, quantity=qty,
                reason=f"[STRATEGY:{strategy.metadata.name}] {signal.reason} (conf={signal.confidence:.0%})",
                order_type="MARKET", rule_mode="STRATEGY",
                target_price=price, total_value=round(price * qty, 2),
                buy_power=effective_power, avg_price=avg,
                sell_target=sell_target, stop_target=stop_target,
                trading_mode="paper" if is_paper or not broker_ids else "live",
                broker_results=broker_results,
            )
            await self._record_trade(trade)
            return True

        # --- SELL / STOP_LOSS ---
        if signal.action in ("SELL", "STOP_LOSS", "TAKE_PROFIT") and pos["qty"] <= 0:
            deps.logger.debug(f"[{sym}] Strategy {signal.action} while flat; skipping bracket fallback")
            return True

        if signal.action in ("SELL", "STOP_LOSS", "TAKE_PROFIT") and pos["qty"] > 0:
            pnl = round((price - entry) * pos["qty"], 2)
            broker_results = []
            if not is_paper and broker_ids:
                broker_results = await deps.broker_mgr.place_orders_for_ticker(
                    broker_ids=broker_ids, allocations=broker_allocs,
                    order_template={
                        "symbol": sym, "side": "SELL", "order_type": "MARKET",
                        "price": price, "quantity": pos["qty"],
                    },
                )
            trade = TradeRecord(
                symbol=sym, side=signal.action if signal.action != "STOP_LOSS" else "STOP",
                price=price, quantity=pos["qty"],
                reason=f"[STRATEGY:{strategy.metadata.name}] {signal.reason} (conf={signal.confidence:.0%})",
                pnl=pnl, order_type="MARKET", rule_mode="STRATEGY",
                entry_price=entry, target_price=price,
                total_value=round(price * pos["qty"], 2),
                buy_power=effective_power, avg_price=avg,
                sell_target=sell_target, stop_target=stop_target,
                trading_mode="paper" if is_paper or not broker_ids else "live",
                broker_results=broker_results,
            )
            await self._record_trade(trade)
            self._positions[sym] = {"qty": 0, "avg_entry": 0, "high": 0}
            self._trailing_highs.pop(sym, None)
            await self._update_profit(sym, pnl, compound)
            return True

        # Unrecognised action — fall through to brackets
        deps.logger.warning(f"[{sym}] Unknown signal action '{signal.action}' from {strategy.metadata.name}")
        return False
