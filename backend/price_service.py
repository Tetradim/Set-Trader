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
        self._fx_cache: Dict[str, float] = {"USD": 1.0}
        self._fx_last_fetch: Optional[datetime] = None
    
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

    async def get_fx_rates(self) -> Dict[str, float]:
        """Fetch FX rates (native currency → USD) for all supported markets.
        Results are cached for 5 minutes."""
        now = datetime.now(timezone.utc)
        if self._fx_last_fetch and (now - self._fx_last_fetch).total_seconds() < 300:
            return dict(self._fx_cache)

        from markets import MARKETS
        pairs: Dict[str, str] = {}
        for m in MARKETS.values():
            if m.yf_fx_pair:
                pairs[m.currency] = m.yf_fx_pair

        for currency, pair in pairs.items():
            try:
                loop = asyncio.get_event_loop()
                rate = await loop.run_in_executor(None, self._fetch_fx_rate, pair)
                if rate > 0:
                    self._fx_cache[currency] = round(rate, 6)
            except Exception as e:
                deps.logger.warning(f"FX rate fetch failed for {pair}: {e}")

        self._fx_last_fetch = now
        deps.logger.info(f"FX rates refreshed: {self._fx_cache}")
        return dict(self._fx_cache)

    def _fetch_fx_rate(self, pair: str) -> float:
        """Fetch a single FX pair rate from yfinance."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(pair)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
        return 0.0

    # ------------------------------------------------------------------
    # OHLCV history — used by signal-based strategies
    # ------------------------------------------------------------------

    async def get_ohlcv(self, symbol: str, period: str = "3mo"):
        """Fetch OHLCV history for a symbol via yfinance.
        Returns a pandas DataFrame (columns: open, high, low, close, volume)
        or None if unavailable."""
        if not deps.YF_AVAILABLE:
            return None
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._fetch_ohlcv_yf, symbol, period)
        except Exception as e:
            deps.logger.warning(f"get_ohlcv failed for {symbol}: {e}")
            return None

    def _fetch_ohlcv_yf(self, symbol: str, period: str):
        try:
            import yfinance as yf
            import pandas as pd
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period)
            if not hist.empty:
                hist.columns = [c.lower() for c in hist.columns]
                return hist
        except Exception:
            pass
        return None

    async def get_enriched_market_data(self, ticker_doc: dict) -> dict:
        """Build the market_data dict passed to BaseStrategy.generate_signals().
        Returns: {history: DataFrame|None, current_price: float, fx_rate: float}
        """
        symbol      = ticker_doc.get("symbol", "")
        market_code = ticker_doc.get("market", "US")
        avg_days    = ticker_doc.get("avg_days", 30)

        # Choose yfinance period based on lookback requirement
        period = "6mo" if avg_days > 90 else "3mo"
        history = await self.get_ohlcv(symbol, period=period)

        current_price = await self.get_price(symbol)

        # FX rate (native currency → USD)
        from markets import MARKETS
        market_cfg = MARKETS.get(market_code, MARKETS["US"])
        fx_rates   = await self.get_fx_rates()
        fx_rate    = fx_rates.get(market_cfg.currency, 1.0)

        return {
            "history":       history,       # pd.DataFrame | None
            "current_price": current_price,
            "fx_rate":       fx_rate,
        }
