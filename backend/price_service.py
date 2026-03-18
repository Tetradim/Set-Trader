"""Price service — fetches live prices via yfinance with caching and drift simulation."""
import asyncio
import random
from datetime import datetime, timezone
from typing import Dict

import deps


class PriceService:
    def __init__(self):
        self._cache: Dict[str, dict] = {}
        self._last_fetch: Dict[str, datetime] = {}

    async def get_price(self, symbol: str) -> float:
        now = datetime.now(timezone.utc)
        cached = self._cache.get(symbol)
        last = self._last_fetch.get(symbol)

        if cached and last and (now - last).total_seconds() < 15:
            noise = cached["price"] * random.uniform(-0.001, 0.001)
            return round(cached["price"] + noise, 2)

        if deps.YF_AVAILABLE:
            try:
                loop = asyncio.get_event_loop()
                price = await loop.run_in_executor(None, self._fetch_yf, symbol)
                if price > 0:
                    self._cache[symbol] = {"price": price}
                    self._last_fetch[symbol] = now
                    return price
            except Exception as e:
                deps.logger.warning(f"yfinance error for {symbol}: {e}")

        if cached:
            drift = cached["price"] * random.uniform(-0.005, 0.005)
            new_price = max(0.01, cached["price"] + drift)
            self._cache[symbol] = {"price": round(new_price, 2)}
            return round(new_price, 2)

        base = random.uniform(50, 500)
        self._cache[symbol] = {"price": round(base, 2)}
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
