from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError


_ET = ZoneInfo("America/New_York")


class EngineStateMixin:
    def _serialize_timestamps(self, values: dict) -> dict:
        serialized = {}
        for key, value in (values or {}).items():
            if isinstance(value, datetime):
                serialized[key] = value.astimezone(timezone.utc).isoformat()
            else:
                serialized[key] = value
        return serialized

    def _restore_timestamps(self, values: dict) -> dict:
        restored = {}
        for key, value in (values or {}).items():
            if isinstance(value, datetime):
                ts = value
            else:
                try:
                    ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                except ValueError:
                    continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            restored[key] = ts.astimezone(timezone.utc)
        return restored

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
        now = datetime.now(timezone.utc).isoformat()
        await deps.db.settings.update_one(
            {"key": "engine_state"},
            {"$set": {"value": {
                "running": self.running,
                "paused": self.paused,
                "simulate_24_7": self.simulate_24_7,
                "market_hours_only": self.market_hours_only,
                "live_during_market_hours": self.live_during_market_hours,
                "paper_after_hours": self.paper_after_hours,
                "dry_run_mode": getattr(self, "_dry_run_mode", False),
                "positions": self._positions,
                "prices": self._prices,
                "trailing_highs": self._trailing_highs,
                "pending_sells": self._pending_sells,
                "last_exit_ts": self._serialize_timestamps(self._last_exit_ts),
                "recent_prices": self._recent_prices,
                "last_rebracket_ts": self._serialize_timestamps(self._last_rebracket_ts),
                "opening_bell_highs": self._opening_bell_highs,
                "opening_bell_rebracket_done": self._opening_bell_rebracket_done,
            }, "updated_at": now}},
            upsert=True,
        )

    async def load_state(self):
        doc = await deps.db.settings.find_one({"key": "engine_state"}, {"_id": 0})
        if doc and doc.get("value"):
            v = doc["value"]
            self.running = v.get("running", False)
            self.paused = v.get("paused", False)
            self.simulate_24_7 = False
            self.market_hours_only = v.get("market_hours_only", True)
            self.live_during_market_hours = True
            self.paper_after_hours = False
            self._dry_run_mode = False
            self._positions = v.get("positions", {}) or {}
            self._prices = v.get("prices", {}) or {}
            self._trailing_highs = v.get("trailing_highs", {}) or {}
            self._pending_sells = v.get("pending_sells", {}) or {}
            self._last_exit_ts.update(self._restore_timestamps(v.get("last_exit_ts", {}) or {}))
            self._recent_prices = v.get("recent_prices", {}) or {}
            self._last_rebracket_ts.update(self._restore_timestamps(v.get("last_rebracket_ts", {}) or {}))
            self._opening_bell_highs = v.get("opening_bell_highs", {}) or {}
            self._opening_bell_rebracket_done = v.get("opening_bell_rebracket_done", {}) or {}
            deps.logger.info(f"Engine state restored: running={self.running}, paused={self.paused}, sim247={self.simulate_24_7}, mkt_hrs={self.market_hours_only}, live_mkt={self.live_during_market_hours}, paper_ah={self.paper_after_hours}, dry_run={self._dry_run_mode}")

    async def sync_positions_from_broker(self, broker_id: str) -> dict:
        broker_positions = await deps.broker_mgr.reconcile_positions(broker_id)
        if not broker_positions:
            return {
                "broker_id": broker_id,
                "synced": 0,
                "added": [],
                "updated": [],
                "removed": [],
                "skipped_external": [],
            }

        allowed_symbols = set()
        try:
            ticker_docs = await deps.db.tickers.find({}, {"_id": 0, "symbol": 1}).to_list(1000)
            allowed_symbols = {str(doc.get("symbol", "")).upper() for doc in ticker_docs if doc.get("symbol")}
        except Exception as exc:
            deps.logger.warning("Could not load ticker symbols before broker sync: %s", exc)

        previous = self._positions or {}
        synced_positions = {}
        added = []
        updated = []
        skipped_external = []

        for symbol, broker_position in broker_positions.items():
            sym = str(symbol).upper()
            if allowed_symbols and sym not in allowed_symbols:
                skipped_external.append(sym)
                continue
            try:
                quantity = float(broker_position.get("quantity", 0) or 0)
            except (TypeError, ValueError):
                quantity = 0.0
            if quantity <= 0:
                continue

            try:
                avg_entry = float(broker_position.get("avg_entry", 0) or 0)
            except (TypeError, ValueError):
                avg_entry = 0.0
            try:
                current_price = float(broker_position.get("current_price", 0) or 0)
            except (TypeError, ValueError):
                current_price = 0.0

            old = previous.get(sym, {}) or {}
            try:
                old_quantity = float(old.get("qty", 0) or 0)
            except (TypeError, ValueError):
                old_quantity = 0.0
            try:
                old_high = float(old.get("high", 0) or 0)
            except (TypeError, ValueError):
                old_high = 0.0

            high = max(old_high, current_price, avg_entry)
            synced_positions[sym] = {
                "qty": round(quantity, 8),
                "avg_entry": avg_entry,
                "high": high,
            }
            if current_price > 0:
                self._prices[sym] = current_price

            if old_quantity <= 0:
                added.append(sym)
            elif abs(old_quantity - quantity) > 1e-8:
                updated.append(sym)

        removed = [
            symbol
            for symbol, position in previous.items()
            if float((position or {}).get("qty", 0) or 0) > 0 and symbol not in synced_positions
        ]

        self._positions = synced_positions
        now = datetime.now(timezone.utc)
        for symbol in removed:
            self._trailing_highs.pop(symbol, None)
            self._opening_bell_highs.pop(symbol, None)
            self._last_exit_ts[symbol] = now
        for symbol, position in synced_positions.items():
            self._trailing_highs[symbol] = max(
                float(self._trailing_highs.get(symbol, 0) or 0),
                float(position.get("high", 0) or 0),
            )

        await self.save_state()
        deps.logger.info(
            "Synced %s broker positions from %s (added=%s, updated=%s, removed=%s)",
            len(synced_positions),
            broker_id,
            added,
            updated,
            removed,
        )
        return {
            "broker_id": broker_id,
            "synced": len(synced_positions),
            "added": added,
            "updated": updated,
            "removed": removed,
            "skipped_external": skipped_external,
        }

    async def reset_trailing_runtime_state(self, symbols: list[str] | None = None):
        """Clear cached trailing highs when trailing configuration changes."""
        if symbols is None:
            self._trailing_highs.clear()
        else:
            for symbol in symbols:
                self._trailing_highs.pop(str(symbol).upper(), None)
        await self.save_state()

    async def load_recent_exit_cooldowns(self, limit: int = 200):
        """Hydrate recent exit timestamps so restart/reload preserves re-entry guards."""
        docs = await deps.db.trades.find(
            {"side": {"$ne": "BUY"}},
            {"_id": 0, "symbol": 1, "side": 1, "timestamp": 1},
        ).sort("timestamp", -1).limit(limit).to_list(limit)

        loaded = 0
        for trade in docs:
            if trade.get("side") == "BUY":
                continue
            sym = trade.get("symbol")
            raw_ts = trade.get("timestamp")
            if not sym or not raw_ts or sym in self._last_exit_ts:
                continue
            try:
                if isinstance(raw_ts, datetime):
                    ts = raw_ts
                else:
                    ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            self._last_exit_ts[sym] = ts.astimezone(timezone.utc)
            loaded += 1

        if loaded:
            deps.logger.info(f"Hydrated recent exit cooldowns for {loaded} symbols")

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
        self.simulate_24_7 = False
        self.paper_after_hours = False
        self.live_during_market_hours = True
        self._dry_run_mode = False
        return False

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
        """Check if the market for this specific ticker is currently open."""
        market = self._get_market(ticker_doc)

        if not self.market_hours_only:
            return True

        return market.is_open_now()

    def get_trading_mode(self) -> str:
        """Get current execution mode. Runtime trades are broker-routed only."""
        return "live"

    def is_paper_trading(self) -> bool:
        """Pulse no longer supports internal paper execution."""
        return False

    async def _validate_order_mode(self, broker_ids: list, ticker_doc: dict) -> tuple[bool, str]:
        """Validate that order mode is appropriate for the configuration.
        
        Returns (is_valid, error_message).
        """
        if not broker_ids:
            return False, "No broker accounts assigned for broker-routed execution"

        from deps import broker_mgr
        for bid in broker_ids:
            if bid not in broker_mgr._adapters:
                return False, f"Broker {bid} not connected for trading"
        
        return True, ""

    def validate_broker_config(self, ticker_doc: dict) -> list[str]:
        """Validate broker configuration for a ticker.
        
        Returns list of warnings/errors.
        """
        issues = []
        broker_ids = ticker_doc.get("broker_ids", [])
        
        if not broker_ids:
            issues.append("Ticker has no broker assignment; runtime execution is blocked")
            return issues
        
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
        
        """
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
        
        if not self.market_hours_only:
            return list(MARKETS.keys())  # All markets
        
        open_markets = []
        for code, config in MARKETS.items():
            if config.is_open_now():
                open_markets.append(code)
        return open_markets
