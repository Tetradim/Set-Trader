"""Market Registry — supported stock exchanges, trading hours, currencies, yfinance suffixes."""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List


@dataclass
class MarketConfig:
    code: str
    name: str
    flag: str
    currency: str           # ISO currency code (e.g., "AUD")
    currency_symbol: str    # Display symbol (e.g., "A$")
    currency_note: str      # Extra display note (e.g., UK pence warning)
    tz_offset_hours: int    # Standard UTC offset in hours (DST not adjusted)
    tz_label: str           # Human label (e.g., "HKT")
    open_hour: int
    open_minute: int
    close_hour: int
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

    def local_now(self) -> datetime:
        return datetime.now(timezone(timedelta(hours=self.tz_offset_hours)))

    def is_open_now(self) -> bool:
        now = self.local_now()
        if now.weekday() >= 5:
            return False
        total = now.hour * 60 + now.minute
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
        now = self.local_now()
        if now.weekday() >= 5:
            return False
        open_time = now.replace(hour=self.open_hour, minute=self.open_minute,
                                second=0, microsecond=0)
        elapsed = (now - open_time).total_seconds()
        return 0 <= elapsed <= minutes * 60

    def is_past_opening_window(self, minutes: int = 30) -> bool:
        now = self.local_now()
        if now.weekday() >= 5:
            return False
        open_time  = now.replace(hour=self.open_hour,  minute=self.open_minute,  second=0, microsecond=0)
        close_time = now.replace(hour=self.close_hour, minute=self.close_minute, second=0, microsecond=0)
        elapsed = (now - open_time).total_seconds()
        return elapsed > minutes * 60 and now < close_time

    def status(self) -> str:
        now = self.local_now()
        if now.weekday() >= 5:
            return "closed"
        total  = now.hour * 60 + now.minute
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
        return {
            "code": self.code,
            "name": self.name,
            "flag": self.flag,
            "currency": self.currency,
            "currency_symbol": self.currency_symbol,
            "currency_note": self.currency_note,
            "tz_offset_hours": self.tz_offset_hours,
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
            "local_time": self.local_now().strftime("%H:%M:%S"),
            "is_open": self.is_open_now(),
        }


MARKETS: Dict[str, MarketConfig] = {
    "US": MarketConfig(
        code="US", name="United States (NYSE / NASDAQ)", flag="🇺🇸",
        currency="USD", currency_symbol="$", currency_note="",
        tz_offset_hours=-5, tz_label="ET",
        open_hour=9, open_minute=30, close_hour=16, close_minute=0,
        yf_suffix="", yf_fx_pair="",
        ticker_examples=["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"],
        trading_notes="Standard US market hours (EST). DST (EDT, UTC-4) from Mar–Nov is not auto-adjusted.",
    ),
    "HK": MarketConfig(
        code="HK", name="Hong Kong (HKEX)", flag="🇭🇰",
        currency="HKD", currency_symbol="HK$", currency_note="",
        tz_offset_hours=8, tz_label="HKT",
        open_hour=9, open_minute=30, close_hour=16, close_minute=0,
        lunch_break=True, lunch_close_hour=12, lunch_close_minute=0,
        lunch_open_hour=13, lunch_open_minute=0,
        yf_suffix=".HK", yf_fx_pair="HKDUSD=X",
        ticker_examples=["0700.HK", "9988.HK", "0005.HK", "1299.HK", "2318.HK"],
        trading_notes="Lunch break 12:00–13:00 HKT. Use 4-digit codes with .HK suffix. No DST in Hong Kong.",
    ),
    "AU": MarketConfig(
        code="AU", name="Australia (ASX)", flag="🇦🇺",
        currency="AUD", currency_symbol="A$", currency_note="",
        tz_offset_hours=10, tz_label="AEST",
        open_hour=10, open_minute=0, close_hour=16, close_minute=0,
        yf_suffix=".AX", yf_fx_pair="AUDUSD=X",
        ticker_examples=["BHP.AX", "CBA.AX", "CSL.AX", "ANZ.AX", "NAB.AX"],
        trading_notes="Uses AEST (UTC+10). AEDT (UTC+11) from Oct–Apr is not auto-adjusted.",
    ),
    "UK": MarketConfig(
        code="UK", name="United Kingdom (LSE)", flag="🇬🇧",
        currency="GBP", currency_symbol="£",
        currency_note="yfinance returns LSE prices in pence (GBX). 100 GBX = £1 GBP.",
        tz_offset_hours=0, tz_label="GMT",
        open_hour=8, open_minute=0, close_hour=16, close_minute=30,
        yf_suffix=".L", yf_fx_pair="GBPUSD=X",
        ticker_examples=["BARC.L", "HSBA.L", "BP.L", "LLOY.L", "GSK.L"],
        trading_notes="BST (UTC+1) from Mar–Oct is not auto-adjusted. Prices from yfinance are in pence (GBX).",
    ),
    "CA": MarketConfig(
        code="CA", name="Canada (TSX)", flag="🇨🇦",
        currency="CAD", currency_symbol="C$", currency_note="",
        tz_offset_hours=-5, tz_label="ET",
        open_hour=9, open_minute=30, close_hour=16, close_minute=0,
        yf_suffix=".TO", yf_fx_pair="CADUSD=X",
        ticker_examples=["RY.TO", "TD.TO", "ENB.TO", "SHOP.TO", "CNR.TO"],
        trading_notes="Same hours as US ET. TSX Venture Exchange uses .V suffix instead of .TO.",
    ),
    "CN_SS": MarketConfig(
        code="CN_SS", name="China — Shanghai (SSE)", flag="🇨🇳",
        currency="CNY", currency_symbol="¥", currency_note="",
        tz_offset_hours=8, tz_label="CST",
        open_hour=9, open_minute=30, close_hour=15, close_minute=0,
        lunch_break=True, lunch_close_hour=11, lunch_close_minute=30,
        lunch_open_hour=13, lunch_open_minute=0,
        yf_suffix=".SS", yf_fx_pair="CNYUSD=X",
        ticker_examples=["600036.SS", "601318.SS", "600519.SS", "601988.SS"],
        trading_notes="Lunch break 11:30–13:00 CST. Use 6-digit codes with .SS suffix for Shanghai SSE.",
    ),
    "CN_SZ": MarketConfig(
        code="CN_SZ", name="China — Shenzhen (SZSE)", flag="🇨🇳",
        currency="CNY", currency_symbol="¥", currency_note="",
        tz_offset_hours=8, tz_label="CST",
        open_hour=9, open_minute=30, close_hour=15, close_minute=0,
        lunch_break=True, lunch_close_hour=11, lunch_close_minute=30,
        lunch_open_hour=13, lunch_open_minute=0,
        yf_suffix=".SZ", yf_fx_pair="CNYUSD=X",
        ticker_examples=["000001.SZ", "000002.SZ", "002594.SZ", "300750.SZ"],
        trading_notes="Lunch break 11:30–13:00 CST. Use 6-digit codes with .SZ suffix for Shenzhen SZSE.",
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
