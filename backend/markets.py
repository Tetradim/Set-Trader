"""Market Registry — supported stock exchanges, trading hours, currencies, yfinance suffixes.

All timezone math uses zoneinfo (stdlib, Python 3.9+) for full DST awareness.
No static UTC offsets — IANA zone names drive everything.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo


@dataclass
class MarketConfig:
    code: str
    name: str
    flag: str
    currency: str           # ISO currency code (e.g., "AUD")
    currency_symbol: str    # Display symbol (e.g., "A$")
    currency_note: str      # Extra display note (e.g., UK pence warning)
    tz_name: str            # IANA timezone name — drives DST-aware math
    tz_label: str           # Short display label (e.g., "ET", "HKT")
    open_hour: int          # Market open, in the market's local time
    open_minute: int
    close_hour: int         # Market close, in the market's local time
    close_minute: int
    lunch_break: bool = False
    lunch_close_hour: int = 0
    lunch_close_minute: int = 0
    lunch_open_hour: int = 0
    lunch_open_minute: int = 0
    yf_suffix: str = ""         # yfinance symbol suffix (e.g., ".HK")
    yf_fx_pair: str = ""        # yfinance FX pair → USD (e.g., "AUDUSD=X")
    ticker_examples: List[str] = field(default_factory=list)
    trading_notes: str = ""

    # -----------------------------------------------------------------------
    # Core time helpers — all DST-aware via zoneinfo
    # -----------------------------------------------------------------------

    def local_now(self) -> datetime:
        """Return the current time in this market's local timezone (DST-aware)."""
        return datetime.now(ZoneInfo(self.tz_name))

    def is_in_lunch_break(self) -> bool:
        """True if the market is in its mid-session lunch break right now."""
        if not self.lunch_break:
            return False
        now = self.local_now()
        if now.weekday() >= 5:
            return False
        total   = now.hour * 60 + now.minute
        l_close = self.lunch_close_hour * 60 + self.lunch_close_minute
        l_open  = self.lunch_open_hour  * 60 + self.lunch_open_minute
        return l_close <= total < l_open

    def is_open_now(self) -> bool:
        """True if the market is currently in an active trading session."""
        now = self.local_now()
        if now.weekday() >= 5:
            return False
        total   = now.hour * 60 + now.minute
        open_t  = self.open_hour  * 60 + self.open_minute
        close_t = self.close_hour * 60 + self.close_minute
        if total < open_t or total >= close_t:
            return False
        if self.lunch_break:
            l_close = self.lunch_close_hour * 60 + self.lunch_close_minute
            l_open  = self.lunch_open_hour  * 60 + self.lunch_open_minute
            if l_close <= total < l_open:
                return False
        return True

    def is_opening_window(self, minutes: int = 30) -> bool:
        """True during the first `minutes` after market open (DST-aware)."""
        now = self.local_now()
        if now.weekday() >= 5:
            return False
        open_time = now.replace(hour=self.open_hour, minute=self.open_minute,
                                second=0, microsecond=0)
        elapsed = (now - open_time).total_seconds()
        return 0 <= elapsed <= minutes * 60

    def is_past_opening_window(self, minutes: int = 30) -> bool:
        """True when past the opening window but still within trading hours."""
        now = self.local_now()
        if now.weekday() >= 5:
            return False
        open_time  = now.replace(hour=self.open_hour,  minute=self.open_minute,  second=0, microsecond=0)
        close_time = now.replace(hour=self.close_hour, minute=self.close_minute, second=0, microsecond=0)
        elapsed = (now - open_time).total_seconds()
        return elapsed > minutes * 60 and now < close_time

    def status(self) -> str:
        """Return 'open', 'lunch', or 'closed'."""
        now = self.local_now()
        if now.weekday() >= 5:
            return "closed"
        total   = now.hour * 60 + now.minute
        open_t  = self.open_hour  * 60 + self.open_minute
        close_t = self.close_hour * 60 + self.close_minute
        if total < open_t or total >= close_t:
            return "closed"
        if self.lunch_break:
            l_close = self.lunch_close_hour * 60 + self.lunch_close_minute
            l_open  = self.lunch_open_hour  * 60 + self.lunch_open_minute
            if l_close <= total < l_open:
                return "lunch"
        return "open"

    def hours_display(self) -> str:
        s = f"{self.open_hour:02d}:{self.open_minute:02d} – {self.close_hour:02d}:{self.close_minute:02d} {self.tz_label}"
        if self.lunch_break:
            s += f" (lunch {self.lunch_close_hour:02d}:{self.lunch_close_minute:02d}–{self.lunch_open_hour:02d}:{self.lunch_open_minute:02d})"
        return s

    def to_dict(self) -> dict:
        now = self.local_now()
        return {
            "code": self.code,
            "name": self.name,
            "flag": self.flag,
            "currency": self.currency,
            "currency_symbol": self.currency_symbol,
            "currency_note": self.currency_note,
            "tz_name": self.tz_name,
            "tz_label": self.tz_label,
            "open_hour": self.open_hour,
            "open_minute": self.open_minute,
            "close_hour": self.close_hour,
            "close_minute": self.close_minute,
            "lunch_break": self.lunch_break,
            "lunch_close_hour": self.lunch_close_hour,
            "lunch_close_minute": self.lunch_close_minute,
            "lunch_open_hour": self.lunch_open_hour,
            "lunch_open_minute": self.lunch_open_minute,
            "yf_suffix": self.yf_suffix,
            "ticker_examples": self.ticker_examples,
            "trading_notes": self.trading_notes,
            "hours_display": self.hours_display(),
            "status": self.status(),
            "local_time": now.strftime("%H:%M:%S"),
            "utc_offset": now.strftime("%z"),   # e.g. "-0400" (EDT) or "-0500" (EST)
            "is_open": self.is_open_now(),
        }


# ---------------------------------------------------------------------------
# Market registry — IANA tz_name ensures DST is handled automatically
# ---------------------------------------------------------------------------

MARKETS: Dict[str, MarketConfig] = {
    "US": MarketConfig(
        code="US", name="United States (NYSE / NASDAQ)", flag="🇺🇸",
        currency="USD", currency_symbol="$", currency_note="",
        tz_name="America/New_York", tz_label="ET",
        open_hour=9, open_minute=30, close_hour=16, close_minute=0,
        yf_suffix="", yf_fx_pair="",
        ticker_examples=["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"],
        trading_notes="NYSE/NASDAQ. DST-aware: EDT (UTC-4) Mar–Nov, EST (UTC-5) Nov–Mar.",
    ),
    "HK": MarketConfig(
        code="HK", name="Hong Kong (HKEX)", flag="🇭🇰",
        currency="HKD", currency_symbol="HK$", currency_note="",
        tz_name="Asia/Hong_Kong", tz_label="HKT",
        open_hour=9, open_minute=30, close_hour=16, close_minute=0,
        lunch_break=True, lunch_close_hour=12, lunch_close_minute=0,
        lunch_open_hour=13, lunch_open_minute=0,
        yf_suffix=".HK", yf_fx_pair="HKDUSD=X",
        ticker_examples=["0700.HK", "9988.HK", "0005.HK", "1299.HK", "2318.HK"],
        trading_notes="Lunch break 12:00–13:00 HKT. No DST in Hong Kong (always UTC+8).",
    ),
    "AU": MarketConfig(
        code="AU", name="Australia (ASX)", flag="🇦🇺",
        currency="AUD", currency_symbol="A$", currency_note="",
        tz_name="Australia/Sydney", tz_label="AEST",
        open_hour=10, open_minute=0, close_hour=16, close_minute=0,
        yf_suffix=".AX", yf_fx_pair="AUDUSD=X",
        ticker_examples=["BHP.AX", "CBA.AX", "CSL.AX", "ANZ.AX", "NAB.AX"],
        trading_notes="DST-aware: AEDT (UTC+11) Oct–Apr, AEST (UTC+10) Apr–Oct.",
    ),
    "UK": MarketConfig(
        code="UK", name="United Kingdom (LSE)", flag="🇬🇧",
        currency="GBP", currency_symbol="£",
        currency_note="yfinance returns LSE prices in pence (GBX). 100 GBX = £1 GBP.",
        tz_name="Europe/London", tz_label="GMT",
        open_hour=8, open_minute=0, close_hour=16, close_minute=30,
        yf_suffix=".L", yf_fx_pair="GBPUSD=X",
        ticker_examples=["BARC.L", "HSBA.L", "BP.L", "LLOY.L", "GSK.L"],
        trading_notes="DST-aware: BST (UTC+1) Mar–Oct, GMT (UTC+0) Oct–Mar. Prices in pence (GBX).",
    ),
    "CA": MarketConfig(
        code="CA", name="Canada (TSX)", flag="🇨🇦",
        currency="CAD", currency_symbol="C$", currency_note="",
        tz_name="America/Toronto", tz_label="ET",
        open_hour=9, open_minute=30, close_hour=16, close_minute=0,
        yf_suffix=".TO", yf_fx_pair="CADUSD=X",
        ticker_examples=["RY.TO", "TD.TO", "ENB.TO", "SHOP.TO", "CNR.TO"],
        trading_notes="Same hours as US ET. DST-aware via America/Toronto. TSX Venture uses .V suffix.",
    ),
    "CN_SS": MarketConfig(
        code="CN_SS", name="China — Shanghai (SSE)", flag="🇨🇳",
        currency="CNY", currency_symbol="¥", currency_note="",
        tz_name="Asia/Shanghai", tz_label="CST",
        open_hour=9, open_minute=30, close_hour=15, close_minute=0,
        lunch_break=True, lunch_close_hour=11, lunch_close_minute=30,
        lunch_open_hour=13, lunch_open_minute=0,
        yf_suffix=".SS", yf_fx_pair="CNYUSD=X",
        ticker_examples=["600036.SS", "601318.SS", "600519.SS", "601988.SS"],
        trading_notes="Lunch break 11:30–13:00 CST. No DST in China (always UTC+8).",
    ),
    "CN_SZ": MarketConfig(
        code="CN_SZ", name="China — Shenzhen (SZSE)", flag="🇨🇳",
        currency="CNY", currency_symbol="¥", currency_note="",
        tz_name="Asia/Shanghai", tz_label="CST",
        open_hour=9, open_minute=30, close_hour=15, close_minute=0,
        lunch_break=True, lunch_close_hour=11, lunch_close_minute=30,
        lunch_open_hour=13, lunch_open_minute=0,
        yf_suffix=".SZ", yf_fx_pair="CNYUSD=X",
        ticker_examples=["000001.SZ", "000002.SZ", "002594.SZ", "300750.SZ"],
        trading_notes="Lunch break 11:30–13:00 CST. No DST in China (always UTC+8).",
    ),
}

# Suffix → market code auto-detection
SUFFIX_TO_MARKET: Dict[str, str] = {
    ".HK": "HK",
    ".AX": "AU",
    ".L":  "UK",
    ".TO": "CA",
    ".V":  "CA",
    ".SS": "CN_SS",
    ".SZ": "CN_SZ",
}


def detect_market_from_symbol(symbol: str) -> str:
    """Auto-detect market code from the yfinance symbol suffix. Defaults to 'US'."""
    sym = symbol.upper()
    for suffix, code in SUFFIX_TO_MARKET.items():
        if sym.endswith(suffix.upper()):
            return code
    return "US"
