from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError


class EngineStateMixin:
    def record_ticker_error(self, symbol: str, error: Exception):
        """Record an error for a ticker for backpressure."""
        now = datetime.now(timezone.utc)
        
        # Check if this is a new error or repeated
        if symbol in self._ticker_last_error:
            time_since_last = (now - self._ticker_last_error[symbol]).total_seconds()
            if time_since_last < 60:  # Within 1 minute = consecutive
                self._ticker_errors[symbol] = self._ticker_errors.get(symbol, 0) + 1
            else:
                self._ticker_errors[symbol] = 1  # Reset after 1 min gap
        else:
            self._ticker_errors[symbol] = 1
        
        self._ticker_last_error[symbol] = now
        deps.logger.warning(f"Ticker {symbol} error #{self._ticker_errors[symbol]}: {error}")
        
        # Auto-pause if too many errors
        if self._ticker_errors[symbol] >= self._max_consecutive_errors:
            deps.logger.error(
                f" AUTO-PAUSE ticker {symbol} due to {self._ticker_errors[symbol]} consecutive errors"
            )

    def clear_ticker_error(self, symbol: str):
        """Clear error count for a ticker after successful evaluation."""
        self._ticker_errors.pop(symbol, None)
        self._ticker_last_error.pop(symbol, None)

    def should_skip_ticker(self, symbol: str) -> bool:
        """Check if ticker should be skipped due to errors."""
        return self._ticker_errors.get(symbol, 0) >= self._max_consecutive_errors

    async def save_state(self):
        await deps.db.settings.update_one(
            {"key": "engine_state"},
            {"$set": {"value": {
                "running": self.running,
                "paused": self.paused,
                "simulate_24_7": self.simulate_24_7,
                "market_hours_only": self.market_hours_only,
                "live_during_market_hours": self.live_during_market_hours,
                "paper_after_hours": self.paper_after_hours,
            }}},
            upsert=True,
        )

    async def load_state(self):
        doc = await deps.db.settings.find_one({"key": "engine_state"}, {"_id": 0})
        if doc and doc.get("value"):
            v = doc["value"]
            self.running = v.get("running", False)
            self.paused = v.get("paused", False)
            self.simulate_24_7 = v.get("simulate_24_7", False)
            self.market_hours_only = v.get("market_hours_only", True)
            self.live_during_market_hours = v.get("live_during_market_hours", False)
            self.paper_after_hours = v.get("paper_after_hours", False)
            deps.logger.info(f"Engine state restored: running={self.running}, paused={self.paused}, sim247={self.simulate_24_7}, mkt_hrs={self.market_hours_only}, live_mkt={self.live_during_market_hours}, paper_ah={self.paper_after_hours}")

    async def reconcile_positions(self):
        """Reconcile positions from DB on startup to recover state."""
        deps.logger.info("Reconciling positions from database...")
        
        # Load open positions from trades
        open_trades = await deps.db.trades.find({
            "side": "BUY",
            "status": {"$ne": "CLOSED"}
        }).to_list(length=1000)
        
        for trade in open_trades:
            sym = trade.get("symbol")
            if sym:
                self._positions[sym] = {
                    "qty": trade.get("quantity", 0),
                    "avg_entry": trade.get("price", 0),
                    "high": trade.get("price", 0),
                }
                deps.logger.info(f"Restored position: {sym} qty={trade.get('quantity')} @ ${trade.get('price')}")
        
        # Load pending sells
        pending = await deps.db.settings.find_one({"key": "pending_sells"})
        if pending and pending.get("value"):
            self._pending_sells = pending.get("value")
            deps.logger.info(f"Restored {len(self._pending_sells)} pending sells")
        
        # Load trailing highs
        trailing = await deps.db.settings.find_one({"key": "trailing_highs"})
        if trailing and trailing.get("value"):
            self._trailing_highs = trailing.get("value")
            deps.logger.info(f"Restored {len(self._trailing_highs)} trailing highs")
        
        deps.logger.info("Position reconciliation complete")

    def check_auto_mode_switch(self) -> bool:
        """Check and apply auto mode switching based on market hours. 
        Only switches on market open/close TRANSITIONS, not continuously.
        Returns True if mode changed."""
        if not self.live_during_market_hours and not self.paper_after_hours:
            return False
        
        market_open = self._is_actual_market_hours()
        
        # Only switch on transition (market state changed)
        if self._last_market_state is not None and market_open == self._last_market_state:
            return False  # No transition, don't override
        
        self._last_market_state = market_open
        mode_changed = False
        
        if market_open and self.live_during_market_hours:
            # Market just opened and user wants live trading during market hours
            if self.simulate_24_7:
                self.simulate_24_7 = False
                mode_changed = True
                deps.logger.info("AUTO MODE: Switched to LIVE trading (market opened)")
        elif not market_open and self.paper_after_hours:
            # Market just closed and user wants paper trading after hours
            if not self.simulate_24_7:
                self.simulate_24_7 = True
                mode_changed = True
                deps.logger.info("AUTO MODE: Switched to PAPER trading (market closed)")
        
        return mode_changed

    def _is_actual_market_hours(self) -> bool:
        """Check if we're in actual US market hours (ignoring simulate_24_7). DST-aware."""
        now = datetime.now(_ET)
        if now.weekday() >= 5:
            return False
        hour, minute = now.hour, now.minute
        if hour < 9 or (hour == 9 and minute < 30):
            return False
        if hour >= 16:
            return False
        return True

    def _get_market(self, ticker_doc: dict):
        """Get the MarketConfig for a ticker (auto-detected from symbol suffix if not set)."""
        from markets import MARKETS, detect_market_from_symbol
        market_code = ticker_doc.get("market") or detect_market_from_symbol(ticker_doc.get("symbol", ""))
        return MARKETS.get(market_code, MARKETS["US"])

    def _is_ticker_market_open(self, ticker_doc: dict) -> bool:
        """Check if the market for this specific ticker is currently open.

        simulate_24_7 bypasses the "market closed" gate (paper trading runs 24/7)
        but still blocks structured lunch breaks for markets that have them
        (CN_SS, CN_SZ, HK). No broker would fill an order during Shanghai/HK
        lunch regardless of mode, so we guard against those misfires.
        """
        market = self._get_market(ticker_doc)

        if self.simulate_24_7:
            # Respect lunch breaks even in simulate mode
            if market.lunch_break and market.is_in_lunch_break():
                return False
            return True

        if not self.market_hours_only:
            return True

        return market.is_open_now()

    def get_trading_mode(self) -> str:
        """Get current trading mode as string: 'paper' or 'live'."""
        if self.simulate_24_7:
            return "paper"
        # Live mode: trading with real broker
        return "live"

    def is_paper_trading(self) -> bool:
        """Check if we're currently in paper trading mode."""
        return self.simulate_24_7

    async def _validate_order_mode(self, broker_ids: list, ticker_doc: dict) -> tuple[bool, str]:
        """Validate that order mode is appropriate for the configuration.
        
        Returns (is_valid, error_message).
        """
        # No brokers = always paper
        if not broker_ids:
            return True, ""
        
        # Have brokers - check mode
        if self.simulate_24_7:
            # Paper mode with brokers - this is valid for simulation
            return True, ""
        
        # Live mode with brokers - verify brokers are connected
        from deps import broker_mgr
        for bid in broker_ids:
            if bid not in broker_mgr._adapters:
                return False, f"Broker {bid} not connected for live trading"
        
        return True, ""

    def validate_broker_config(self, ticker_doc: dict) -> list[str]:
        """Validate broker configuration for a ticker.
        
        Returns list of warnings/errors.
        """
        issues = []
        broker_ids = ticker_doc.get("broker_ids", [])
        
        if not broker_ids:
            return issues
            
        # Check if we have live brokers but are in paper mode
        if self.simulate_24_7 and broker_ids:
            issues.append("Tickers configured with brokers but running in paper mode")
        
        # Check for broker connection issues
        for bid in broker_ids:
            if bid in self._failed:
                issues.append(f"Broker {bid} in failed state: {self._failed.get(bid, 'unknown error')}")
        
        return issues

    def update_high_water_mark(self, symbol: str, current_price: float) -> None:
        """Update high water mark if current price is higher."""
        pos = self._positions.get(symbol)
        if not pos or pos.get("qty", 0) <= 0:
            return
        high = pos.get("high", 0)
        if current_price > high:
            self._positions[symbol]["high"] = current_price

    def get_drawdown_pct(self, symbol: str, current_price: float) -> float:
        """Calculate drawdown percentage from high water mark."""
        pos = self._positions.get(symbol)
        if not pos or pos.get("qty", 0) <= 0:
            return 0.0
        high = pos.get("high", 0)
        if high <= 0:
            return 0.0
        return round(((high - current_price) / high) * 100, 2)

    def _is_opening_window(self, minutes: int = 30, ticker_doc: dict = None) -> bool:
        """True during the first `minutes` after market open (DST-aware).
        Uses the ticker's specific market when ticker_doc is provided."""
        if ticker_doc is not None:
            return self._get_market(ticker_doc).is_opening_window(minutes)
        # Legacy fallback: US ET (DST-aware)
        now = datetime.now(_ET)
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        elapsed = (now - market_open).total_seconds()
        return 0 <= elapsed <= minutes * 60

    def _is_past_opening_window(self, minutes: int = 30, ticker_doc: dict = None) -> bool:
        """True when past the opening window but still within market hours (DST-aware)."""
        if ticker_doc is not None:
            return self._get_market(ticker_doc).is_past_opening_window(minutes)
        # Legacy fallback: US ET (DST-aware)
        now = datetime.now(_ET)
        if now.weekday() >= 5:
            return False
        market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
        elapsed = (now - market_open).total_seconds()
        return elapsed > minutes * 60 and now < market_close

    def is_market_open(self, market: str = None) -> bool:
        """Check if market is open for trading.
        
        Args:
            market: Market code (US, HK, AU, UK, CA). If None, checks all configured markets.
        
        In paper mode (simulate_24_7), always returns True.
        """
        # In paper mode, always allow trading (24/7 simulation)
        if self.simulate_24_7:
            return True
        
        # In live mode, respect market_hours_only setting
        if not self.market_hours_only:
            return True
        
        if market:
            # Check specific market using MarketConfig
            from markets import MARKETS
            config = MARKETS.get(market)
            if config:
                return config.is_open_now()
            # Fallback to US check
            market = "US"
        
        # Default: Check US market hours (9:30 AM - 4:00 PM ET, weekdays) — DST-aware
        now = datetime.now(_ET)
        if now.weekday() >= 5:
            return False
        hour, minute = now.hour, now.minute
        if hour < 9 or (hour == 9 and minute < 30):
            return False
        if hour >= 16:
            return False
        return True

    def get_open_markets(self) -> list[str]:
        """Get list of currently open markets."""
        from markets import MARKETS
        
        if self.simulate_24_7 or not self.market_hours_only:
            return list(MARKETS.keys())  # All markets
        
        open_markets = []
        for code, config in MARKETS.items():
            if config.is_open_now():
                open_markets.append(code)
        return open_markets
