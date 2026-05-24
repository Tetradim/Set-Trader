"""Market registry for global stock exchanges.

All timezone math uses IANA zone names through zoneinfo, so regular open,
close, lunch, and opening-bell windows stay DST-aware.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

from market_calendar import get_calendar_status


@dataclass
class MarketConfig:
    code: str
    name: str
    flag: str
    currency: str
    currency_symbol: str
    currency_note: str
    tz_name: str
    tz_label: str
    open_hour: int
    open_minute: int
    close_hour: int
    close_minute: int
    lunch_break: bool = False
    lunch_close_hour: int = 0
    lunch_close_minute: int = 0
    lunch_open_hour: int = 0
    lunch_open_minute: int = 0
    yf_suffix: str = ""
    yf_fx_pair: str = ""
    ticker_examples: List[str] = field(default_factory=list)
    trading_notes: str = ""

    def local_now(self) -> datetime:
        """Return current time in this market's local timezone."""
        return datetime.now(ZoneInfo(self.tz_name))

    def _localize(self, now: datetime | None = None) -> datetime:
        if now is None:
            return self.local_now()
        if now.tzinfo is None:
            return now.replace(tzinfo=ZoneInfo(self.tz_name))
        return now.astimezone(ZoneInfo(self.tz_name))

    def is_in_lunch_break(self, now: datetime | None = None) -> bool:
        """True if the market is in its mid-session lunch break right now."""
        if not self.lunch_break:
            return False
        now = self._localize(now)
        if now.weekday() >= 5:
            return False
        total = now.hour * 60 + now.minute
        lunch_close = self.lunch_close_hour * 60 + self.lunch_close_minute
        lunch_open = self.lunch_open_hour * 60 + self.lunch_open_minute
        return lunch_close <= total < lunch_open

    def is_open_now(self, now: datetime | None = None) -> bool:
        """True if the market is currently in an active trading session."""
        now = self._localize(now)
        calendar = get_calendar_status(self.code, now)
        if calendar:
            return calendar.is_open
        if now.weekday() >= 5:
            return False
        total = now.hour * 60 + now.minute
        open_time = self.open_hour * 60 + self.open_minute
        close_time = self.close_hour * 60 + self.close_minute
        if total < open_time or total >= close_time:
            return False
        return not self.is_in_lunch_break(now)

    def is_opening_window(self, minutes: int = 30, now: datetime | None = None) -> bool:
        """True during the first `minutes` after market open."""
        now = self._localize(now)
        calendar = get_calendar_status(self.code, now)
        if calendar and not calendar.is_session_day:
            return False
        if now.weekday() >= 5:
            return False
        open_time = now.replace(hour=self.open_hour, minute=self.open_minute, second=0, microsecond=0)
        elapsed = (now - open_time).total_seconds()
        return 0 <= elapsed <= minutes * 60

    def is_past_opening_window(self, minutes: int = 30, now: datetime | None = None) -> bool:
        """True when past the opening window but still within trading hours."""
        now = self._localize(now)
        calendar = get_calendar_status(self.code, now)
        if calendar and not calendar.is_session_day:
            return False
        if now.weekday() >= 5:
            return False
        open_time = now.replace(hour=self.open_hour, minute=self.open_minute, second=0, microsecond=0)
        close_time = now.replace(hour=self.close_hour, minute=self.close_minute, second=0, microsecond=0)
        elapsed = (now - open_time).total_seconds()
        return elapsed > minutes * 60 and now < close_time

    def status(self, now: datetime | None = None) -> str:
        """Return 'open', 'lunch', or 'closed'."""
        now = self._localize(now)
        calendar = get_calendar_status(self.code, now)
        if calendar:
            return calendar.status
        if self.is_in_lunch_break(now):
            return "lunch"
        return "open" if self.is_open_now(now) else "closed"

    def hours_display(self) -> str:
        label = f"{self.open_hour:02d}:{self.open_minute:02d} - {self.close_hour:02d}:{self.close_minute:02d} {self.tz_label}"
        if self.lunch_break:
            label += f" (lunch {self.lunch_close_hour:02d}:{self.lunch_close_minute:02d}-{self.lunch_open_hour:02d}:{self.lunch_open_minute:02d})"
        return label

    def to_dict(self) -> dict:
        now = self.local_now()
        calendar = get_calendar_status(self.code, now)
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
            "yf_fx_pair": self.yf_fx_pair,
            "ticker_examples": self.ticker_examples,
            "trading_notes": self.trading_notes,
            "hours_display": self.hours_display(),
            "status": self.status(now),
            "local_time": now.strftime("%H:%M:%S"),
            "utc_offset": now.strftime("%z"),
            "is_open": self.is_open_now(now),
            "calendar_source": calendar.source if calendar else "weekday_hours_fallback",
            "calendar_reason": calendar.reason if calendar else "",
            "is_holiday": calendar.is_holiday if calendar else False,
            "is_session_day": calendar.is_session_day if calendar else now.weekday() < 5,
            "market_open_utc": calendar.market_open if calendar else "",
            "market_close_utc": calendar.market_close if calendar else "",
            "break_start_utc": calendar.break_start if calendar else "",
            "break_end_utc": calendar.break_end if calendar else "",
        }


MARKETS: Dict[str, MarketConfig] = {
    "US": MarketConfig(
        code="US", name="United States (NYSE / NASDAQ)", flag="🇺🇸",
        currency="USD", currency_symbol="$", currency_note="",
        tz_name="America/New_York", tz_label="ET",
        open_hour=9, open_minute=30, close_hour=16, close_minute=0,
        yf_suffix="", yf_fx_pair="",
        ticker_examples=["AAPL", "TSLA", "NVDA", "MSFT", "AMZN"],
        trading_notes="NYSE/NASDAQ regular session. DST-aware via America/New_York.",
    ),
    "CA": MarketConfig(
        code="CA", name="Canada (TSX)", flag="🇨🇦",
        currency="CAD", currency_symbol="C$", currency_note="",
        tz_name="America/Toronto", tz_label="ET",
        open_hour=9, open_minute=30, close_hour=16, close_minute=0,
        yf_suffix=".TO", yf_fx_pair="CADUSD=X",
        ticker_examples=["RY.TO", "TD.TO", "ENB.TO", "SHOP.TO", "CNR.TO"],
        trading_notes="Toronto Stock Exchange. TSX Venture tickers commonly use .V.",
    ),
    "MX": MarketConfig(
        code="MX", name="Mexico (BMV)", flag="🇲🇽",
        currency="MXN", currency_symbol="MX$", currency_note="",
        tz_name="America/Mexico_City", tz_label="CST",
        open_hour=8, open_minute=30, close_hour=15, close_minute=0,
        yf_suffix=".MX", yf_fx_pair="MXNUSD=X",
        ticker_examples=["AMXL.MX", "WALMEX.MX", "GMEXICOB.MX", "FEMSAUBD.MX"],
        trading_notes="Mexican Stock Exchange local session.",
    ),
    "BR": MarketConfig(
        code="BR", name="Brazil (B3)", flag="🇧🇷",
        currency="BRL", currency_symbol="R$", currency_note="",
        tz_name="America/Sao_Paulo", tz_label="BRT",
        open_hour=10, open_minute=0, close_hour=17, close_minute=0,
        yf_suffix=".SA", yf_fx_pair="BRLUSD=X",
        ticker_examples=["PETR4.SA", "VALE3.SA", "ITUB4.SA", "BBDC4.SA"],
        trading_notes="B3 equity session in Sao Paulo local time.",
    ),
    "UK": MarketConfig(
        code="UK", name="United Kingdom (LSE)", flag="🇬🇧",
        currency="GBP", currency_symbol="£",
        currency_note="yfinance returns many LSE prices in pence (GBX). 100 GBX = £1 GBP.",
        tz_name="Europe/London", tz_label="GMT/BST",
        open_hour=8, open_minute=0, close_hour=16, close_minute=30,
        yf_suffix=".L", yf_fx_pair="GBPUSD=X",
        ticker_examples=["BARC.L", "HSBA.L", "BP.L", "LLOY.L", "GSK.L"],
        trading_notes="London Stock Exchange regular session. DST-aware via Europe/London.",
    ),
    "DE": MarketConfig(
        code="DE", name="Germany (Xetra)", flag="🇩🇪",
        currency="EUR", currency_symbol="€", currency_note="",
        tz_name="Europe/Berlin", tz_label="CET/CEST",
        open_hour=9, open_minute=0, close_hour=17, close_minute=30,
        yf_suffix=".DE", yf_fx_pair="EURUSD=X",
        ticker_examples=["SAP.DE", "SIE.DE", "DTE.DE", "ALV.DE", "BAS.DE"],
        trading_notes="Xetra continuous trading. DST-aware via Europe/Berlin.",
    ),
    "FR": MarketConfig(
        code="FR", name="France (Euronext Paris)", flag="🇫🇷",
        currency="EUR", currency_symbol="€", currency_note="",
        tz_name="Europe/Paris", tz_label="CET/CEST",
        open_hour=9, open_minute=0, close_hour=17, close_minute=30,
        yf_suffix=".PA", yf_fx_pair="EURUSD=X",
        ticker_examples=["MC.PA", "OR.PA", "AIR.PA", "SAN.PA", "BNP.PA"],
        trading_notes="Euronext Paris cash-market session.",
    ),
    "NL": MarketConfig(
        code="NL", name="Netherlands (Euronext Amsterdam)", flag="🇳🇱",
        currency="EUR", currency_symbol="€", currency_note="",
        tz_name="Europe/Amsterdam", tz_label="CET/CEST",
        open_hour=9, open_minute=0, close_hour=17, close_minute=30,
        yf_suffix=".AS", yf_fx_pair="EURUSD=X",
        ticker_examples=["ASML.AS", "INGA.AS", "ADYEN.AS", "HEIA.AS"],
        trading_notes="Euronext Amsterdam cash-market session.",
    ),
    "ES": MarketConfig(
        code="ES", name="Spain (BME Madrid)", flag="🇪🇸",
        currency="EUR", currency_symbol="€", currency_note="",
        tz_name="Europe/Madrid", tz_label="CET/CEST",
        open_hour=9, open_minute=0, close_hour=17, close_minute=30,
        yf_suffix=".MC", yf_fx_pair="EURUSD=X",
        ticker_examples=["SAN.MC", "IBE.MC", "ITX.MC", "BBVA.MC"],
        trading_notes="BME Madrid continuous session.",
    ),
    "IT": MarketConfig(
        code="IT", name="Italy (Borsa Italiana)", flag="🇮🇹",
        currency="EUR", currency_symbol="€", currency_note="",
        tz_name="Europe/Rome", tz_label="CET/CEST",
        open_hour=9, open_minute=0, close_hour=17, close_minute=30,
        yf_suffix=".MI", yf_fx_pair="EURUSD=X",
        ticker_examples=["ENEL.MI", "ISP.MI", "UCG.MI", "ENI.MI"],
        trading_notes="Borsa Italiana continuous session.",
    ),
    "CH": MarketConfig(
        code="CH", name="Switzerland (SIX)", flag="🇨🇭",
        currency="CHF", currency_symbol="CHF", currency_note="",
        tz_name="Europe/Zurich", tz_label="CET/CEST",
        open_hour=9, open_minute=0, close_hour=17, close_minute=30,
        yf_suffix=".SW", yf_fx_pair="CHFUSD=X",
        ticker_examples=["NESN.SW", "ROG.SW", "NOVN.SW", "UBSG.SW"],
        trading_notes="SIX Swiss Exchange session.",
    ),
    "SE": MarketConfig(
        code="SE", name="Sweden (Nasdaq Stockholm)", flag="🇸🇪",
        currency="SEK", currency_symbol="kr", currency_note="",
        tz_name="Europe/Stockholm", tz_label="CET/CEST",
        open_hour=9, open_minute=0, close_hour=17, close_minute=30,
        yf_suffix=".ST", yf_fx_pair="SEKUSD=X",
        ticker_examples=["ERIC-B.ST", "VOLV-B.ST", "ATCO-A.ST", "HM-B.ST"],
        trading_notes="Nasdaq Stockholm equity session.",
    ),
    "ZA": MarketConfig(
        code="ZA", name="South Africa (JSE)", flag="🇿🇦",
        currency="ZAR", currency_symbol="R",
        currency_note="Some JSE instruments may be quoted in cents by market-data providers.",
        tz_name="Africa/Johannesburg", tz_label="SAST",
        open_hour=9, open_minute=0, close_hour=17, close_minute=0,
        yf_suffix=".JO", yf_fx_pair="ZARUSD=X",
        ticker_examples=["NPN.JO", "PRX.JO", "FSR.JO", "SBK.JO"],
        trading_notes="Johannesburg Stock Exchange session. No DST in South Africa.",
    ),
    "JP": MarketConfig(
        code="JP", name="Japan (Tokyo Stock Exchange)", flag="🇯🇵",
        currency="JPY", currency_symbol="¥", currency_note="",
        tz_name="Asia/Tokyo", tz_label="JST",
        open_hour=9, open_minute=0, close_hour=15, close_minute=30,
        lunch_break=True, lunch_close_hour=11, lunch_close_minute=30,
        lunch_open_hour=12, lunch_open_minute=30,
        yf_suffix=".T", yf_fx_pair="JPYUSD=X",
        ticker_examples=["7203.T", "6758.T", "9984.T", "8306.T", "6861.T"],
        trading_notes="TSE has a lunch break. No DST in Japan. Useful after North American close.",
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
        trading_notes="Lunch break 12:00-13:00 HKT. No DST in Hong Kong.",
    ),
    "AU": MarketConfig(
        code="AU", name="Australia (ASX)", flag="🇦🇺",
        currency="AUD", currency_symbol="A$", currency_note="",
        tz_name="Australia/Sydney", tz_label="AEST/AEDT",
        open_hour=10, open_minute=0, close_hour=16, close_minute=0,
        yf_suffix=".AX", yf_fx_pair="AUDUSD=X",
        ticker_examples=["BHP.AX", "CBA.AX", "CSL.AX", "ANZ.AX", "NAB.AX"],
        trading_notes="Australian Securities Exchange. DST-aware via Australia/Sydney.",
    ),
    "CN_SS": MarketConfig(
        code="CN_SS", name="China - Shanghai (SSE)", flag="🇨🇳",
        currency="CNY", currency_symbol="¥", currency_note="",
        tz_name="Asia/Shanghai", tz_label="CST",
        open_hour=9, open_minute=30, close_hour=15, close_minute=0,
        lunch_break=True, lunch_close_hour=11, lunch_close_minute=30,
        lunch_open_hour=13, lunch_open_minute=0,
        yf_suffix=".SS", yf_fx_pair="CNYUSD=X",
        ticker_examples=["600036.SS", "601318.SS", "600519.SS", "601988.SS"],
        trading_notes="Lunch break 11:30-13:00 CST. No DST in China.",
    ),
    "CN_SZ": MarketConfig(
        code="CN_SZ", name="China - Shenzhen (SZSE)", flag="🇨🇳",
        currency="CNY", currency_symbol="¥", currency_note="",
        tz_name="Asia/Shanghai", tz_label="CST",
        open_hour=9, open_minute=30, close_hour=15, close_minute=0,
        lunch_break=True, lunch_close_hour=11, lunch_close_minute=30,
        lunch_open_hour=13, lunch_open_minute=0,
        yf_suffix=".SZ", yf_fx_pair="CNYUSD=X",
        ticker_examples=["000001.SZ", "000002.SZ", "002594.SZ", "300750.SZ"],
        trading_notes="Lunch break 11:30-13:00 CST. No DST in China.",
    ),
    "IN_NSE": MarketConfig(
        code="IN_NSE", name="India (NSE)", flag="🇮🇳",
        currency="INR", currency_symbol="₹", currency_note="",
        tz_name="Asia/Kolkata", tz_label="IST",
        open_hour=9, open_minute=15, close_hour=15, close_minute=30,
        yf_suffix=".NS", yf_fx_pair="INRUSD=X",
        ticker_examples=["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"],
        trading_notes="National Stock Exchange regular session. No DST in India.",
    ),
    "IN_BSE": MarketConfig(
        code="IN_BSE", name="India (BSE)", flag="🇮🇳",
        currency="INR", currency_symbol="₹", currency_note="",
        tz_name="Asia/Kolkata", tz_label="IST",
        open_hour=9, open_minute=15, close_hour=15, close_minute=30,
        yf_suffix=".BO", yf_fx_pair="INRUSD=X",
        ticker_examples=["RELIANCE.BO", "TCS.BO", "INFY.BO", "HDFCBANK.BO"],
        trading_notes="Bombay Stock Exchange regular session. No DST in India.",
    ),
    "SG": MarketConfig(
        code="SG", name="Singapore (SGX)", flag="🇸🇬",
        currency="SGD", currency_symbol="S$", currency_note="",
        tz_name="Asia/Singapore", tz_label="SGT",
        open_hour=9, open_minute=0, close_hour=17, close_minute=0,
        lunch_break=True, lunch_close_hour=12, lunch_close_minute=0,
        lunch_open_hour=13, lunch_open_minute=0,
        yf_suffix=".SI", yf_fx_pair="SGDUSD=X",
        ticker_examples=["D05.SI", "O39.SI", "U11.SI", "Z74.SI"],
        trading_notes="SGX session with lunch break. No DST in Singapore.",
    ),
    "KR": MarketConfig(
        code="KR", name="South Korea (KRX)", flag="🇰🇷",
        currency="KRW", currency_symbol="₩", currency_note="",
        tz_name="Asia/Seoul", tz_label="KST",
        open_hour=9, open_minute=0, close_hour=15, close_minute=30,
        yf_suffix=".KS", yf_fx_pair="KRWUSD=X",
        ticker_examples=["005930.KS", "000660.KS", "035420.KS", "005380.KS"],
        trading_notes="KRX regular session. KOSDAQ tickers commonly use .KQ.",
    ),
    "TW": MarketConfig(
        code="TW", name="Taiwan (TWSE)", flag="🇹🇼",
        currency="TWD", currency_symbol="NT$", currency_note="",
        tz_name="Asia/Taipei", tz_label="TST",
        open_hour=9, open_minute=0, close_hour=13, close_minute=30,
        yf_suffix=".TW", yf_fx_pair="TWDUSD=X",
        ticker_examples=["2330.TW", "2317.TW", "2454.TW", "2303.TW"],
        trading_notes="TWSE regular session. Taipei Exchange tickers commonly use .TWO.",
    ),
}


SUFFIX_TO_MARKET: Dict[str, str] = {
    ".TWO": "TW",
    ".HK": "HK",
    ".AX": "AU",
    ".TO": "CA",
    ".V": "CA",
    ".MX": "MX",
    ".SA": "BR",
    ".SS": "CN_SS",
    ".SZ": "CN_SZ",
    ".DE": "DE",
    ".PA": "FR",
    ".AS": "NL",
    ".MC": "ES",
    ".MI": "IT",
    ".SW": "CH",
    ".ST": "SE",
    ".JO": "ZA",
    ".NS": "IN_NSE",
    ".BO": "IN_BSE",
    ".SI": "SG",
    ".KS": "KR",
    ".KQ": "KR",
    ".TW": "TW",
    ".L": "UK",
    ".T": "JP",
}


def detect_market_from_symbol(symbol: str) -> str:
    """Auto-detect market code from the yfinance symbol suffix. Defaults to US."""
    sym = symbol.upper()
    for suffix, code in sorted(SUFFIX_TO_MARKET.items(), key=lambda item: len(item[0]), reverse=True):
        if sym.endswith(suffix):
            return code
    return "US"
