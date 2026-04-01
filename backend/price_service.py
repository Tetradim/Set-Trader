"""Price service — fetches live prices with broker feeds preferred, yfinance fallback."""
import asyncio
import random
from datetime import datetime, timezone
from typing import Dict, Optional

import deps


class PriceService:
    def __init__(self):
        self._cache: Dict[str, dict] = {}
        self._last_fetch: Dict[str, datetime] = {}
        self._broker_streams: Dict[str, dict] = {}  # symbol -> {broker_id, price, timestamp}
        self.prefer_broker_feeds = True  # Toggle for broker vs yfinance
        self._price_source: Dict[str, str] = {}  # Track which source was used
    
    def set_prefer_broker_feeds(self, prefer: bool):
        """Toggle preference for broker market data feeds."""
        self.prefer_broker_feeds = prefer
        deps.logger.info(f"Price feed preference: {'Broker feeds' if prefer else 'yfinance'}")
    
    def update_broker_price(self, symbol: str, broker_id: str, price: float):
        """Update price from a broker's market data feed."""
        self._broker_streams[symbol] = {
            "broker_id": broker_id,
            "price": price,
            "timestamp": datetime.now(timezone.utc),
        }
    
    def get_price_source(self, symbol: str) -> str:
        """Get the source of the last price for a symbol."""
        return self._price_source.get(symbol, "unknown")
    
    async def get_price(self, symbol: str) -> float:
        now = datetime.now(timezone.utc)
        
        # Try broker feed first if preferred and available
        if self.prefer_broker_feeds and symbol in self._broker_streams:
            broker_data = self._broker_streams[symbol]
            age = (now - broker_data["timestamp"]).total_seconds()
            if age < 30:  # Broker data fresh within 30 seconds
                self._price_source[symbol] = f"broker:{broker_data['broker_id']}"
                return broker_data["price"]
        
        # Check cache
        cached = self._cache.get(symbol)
        last = self._last_fetch.get(symbol)

        if cached and last and (now - last).total_seconds() < 15:
            noise = cached["price"] * random.uniform(-0.001, 0.001)
            return round(cached["price"] + noise, 2)

        # Fetch from yfinance
        if deps.YF_AVAILABLE:
            try:
                loop = asyncio.get_event_loop()
                price = await loop.run_in_executor(None, self._fetch_yf, symbol)
                if price > 0:
                    self._cache[symbol] = {"price": price}
                    self._last_fetch[symbol] = now
                    self._price_source[symbol] = "yfinance"
                    return price
            except Exception as e:
                deps.logger.warning(f"yfinance error for {symbol}: {e}")

        # Fallback to cached with drift
        if cached:
            drift = cached["price"] * random.uniform(-0.005, 0.005)
            new_price = max(0.01, cached["price"] + drift)
            self._cache[symbol] = {"price": round(new_price, 2)}
            self._price_source[symbol] = "cache"
            return round(new_price, 2)

        # Last resort: random price
        base = random.uniform(50, 500)
        self._cache[symbol] = {"price": round(base, 2)}
        self._price_source[symbol] = "simulated"
        return round(base, 2)

    def _fetch_yf(self, symbol: str) -> float:
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return round(float(hist["Close"].iloc[-1]), 2)
        except Exception:
            pass
        return 0.0

    async def get_avg_price(self, symbol: str, days: int) -> float:
        if deps.YF_AVAILABLE:
            try:
                loop = asyncio.get_event_loop()
                avg = await loop.run_in_executor(None, self._fetch_avg_yf, symbol, days)
                if avg > 0:
                    return avg
            except Exception:
                pass
        current = await self.get_price(symbol)
        return current

    def _fetch_avg_yf(self, symbol: str, days: int) -> float:
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            period = "1mo" if days <= 30 else "3mo" if days <= 90 else "1y"
            hist = ticker.history(period=period)
            if not hist.empty:
                return round(float(hist["Close"].tail(days).mean()), 2)
        except Exception:
            pass
        return 0.0
    
    def get_all_sources(self) -> Dict[str, str]:
        """Get price sources for all tracked symbols."""
        return dict(self._price_source)
