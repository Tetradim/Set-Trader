"""Exchange calendar adapter for market-hours decisions.

The bot can run without this optional dependency, but when
`pandas_market_calendars` is installed it provides exchange holidays,
half-days, and lunch breaks from the exchange calendar instead of using only
weekday/hour checks.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


CALENDAR_BY_MARKET = {
    "US": "XNYS",
    "CA": "XTSE",
    "MX": "XMEX",
    "BR": "BVMF",
    "UK": "XLON",
    "DE": "XETR",
    "FR": "XPAR",
    "NL": "XAMS",
    "ES": "XMAD",
    "IT": "XMIL",
    "CH": "XSWX",
    "SE": "XSTO",
    "ZA": "XJSE",
    "JP": "XTKS",
    "HK": "XHKG",
    "AU": "XASX",
    "CN_SS": "XSHG",
    # No Shenzhen calendar is registered by pandas_market_calendars.
    # Use Shanghai for mainland China session days/hours instead of falling back.
    "CN_SZ": "XSHG",
    "IN_NSE": "XNSE",
    "IN_BSE": "XBOM",
    "SG": "XSES",
    "KR": "XKRX",
    "TW": "XTAI",
}


@dataclass(frozen=True)
class CalendarStatus:
    status: str
    is_open: bool
    is_session_day: bool
    is_holiday: bool
    source: str
    reason: str = ""
    market_open: str = ""
    market_close: str = ""
    break_start: str = ""
    break_end: str = ""


_CALENDAR_CACHE = {}


def _load_calendar(name: str):
    try:
        import pandas_market_calendars as mcal
    except Exception:
        return None
    if name not in _CALENDAR_CACHE:
        _CALENDAR_CACHE[name] = mcal.get_calendar(name)
    return _CALENDAR_CACHE[name]


def get_calendar_status(market_code: str, now: datetime) -> Optional[CalendarStatus]:
    """Return exchange-calendar status, or None when the adapter is unavailable."""
    calendar_name = CALENDAR_BY_MARKET.get(market_code)
    if not calendar_name:
        return None
    calendar = _load_calendar(calendar_name)
    if calendar is None:
        return None

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local_date = now.date().isoformat()

    try:
        schedule = calendar.schedule(start_date=local_date, end_date=local_date)
    except Exception:
        return None

    source = f"pandas_market_calendars:{calendar_name}"
    if schedule.empty:
        return CalendarStatus(
            status="closed",
            is_open=False,
            is_session_day=False,
            is_holiday=True,
            source=source,
            reason="exchange_closed",
        )

    row = schedule.iloc[0]
    now_utc = now.astimezone(timezone.utc)
    market_open = row["market_open"].to_pydatetime().astimezone(timezone.utc)
    market_close = row["market_close"].to_pydatetime().astimezone(timezone.utc)
    break_start = row.get("break_start")
    break_end = row.get("break_end")

    if break_start is not None and break_end is not None:
        break_start_dt = break_start.to_pydatetime().astimezone(timezone.utc)
        break_end_dt = break_end.to_pydatetime().astimezone(timezone.utc)
        if break_start_dt <= now_utc < break_end_dt:
            return CalendarStatus(
                status="lunch",
                is_open=False,
                is_session_day=True,
                is_holiday=False,
                source=source,
                reason="exchange_break",
                market_open=market_open.isoformat(),
                market_close=market_close.isoformat(),
                break_start=break_start_dt.isoformat(),
                break_end=break_end_dt.isoformat(),
            )

    is_open = market_open <= now_utc < market_close
    return CalendarStatus(
        status="open" if is_open else "closed",
        is_open=is_open,
        is_session_day=True,
        is_holiday=False,
        source=source,
        reason="regular_session" if is_open else "outside_session",
        market_open=market_open.isoformat(),
        market_close=market_close.isoformat(),
        break_start=break_start.to_pydatetime().astimezone(timezone.utc).isoformat() if break_start is not None else "",
        break_end=break_end.to_pydatetime().astimezone(timezone.utc).isoformat() if break_end is not None else "",
    )
