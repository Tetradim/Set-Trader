"""Market replay import and storage helpers.

Replay sessions are Sentinel Pulse-owned market logs. Third-party providers
are import sources only; playback uses the stored replay_bars collection.
"""
import asyncio
import hashlib
import math
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable


REPLAY_SESSIONS_COLLECTION = "replay_sessions"
REPLAY_BARS_COLLECTION = "replay_bars"
ACTIVE_REPLAY_SETTING = "active_replay"


def _clean_symbols(symbols: Iterable[str]) -> list[str]:
    cleaned = sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()})
    if not cleaned:
        raise ValueError("At least one symbol is required.")
    return cleaned


def build_session_id(source: str, symbols: Iterable[str], trading_date: str | date, interval: str) -> str:
    clean_source = str(source).strip().lower()
    clean_date = trading_date.isoformat() if isinstance(trading_date, date) else str(trading_date)
    clean_interval = str(interval).strip()
    symbol_part = ",".join(_clean_symbols(symbols))
    digest = hashlib.sha1(f"{clean_source}|{clean_date}|{clean_interval}|{symbol_part}".encode("utf-8")).hexdigest()[:12]
    return f"{clean_source}-{clean_date}-{clean_interval}-{digest}"


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _is_finite_positive(value: Any) -> bool:
    try:
        number = float(value)
        return math.isfinite(number) and number > 0
    except (TypeError, ValueError):
        return False


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_utc_iso(value: Any) -> str:
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_utc_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def build_replay_bar(
    *,
    session_id: str,
    source: str,
    symbol: str,
    timestamp: Any,
    open_price: Any,
    high: Any,
    low: Any,
    close: Any,
    volume: Any = 0,
    vwap: Any = None,
    trade_count: Any = None,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "source": str(source).strip().lower(),
        "symbol": str(symbol).strip().upper(),
        "timestamp": _to_utc_iso(timestamp),
        "open": _to_float(open_price),
        "high": _to_float(high),
        "low": _to_float(low),
        "close": _to_float(close),
        "volume": _to_float(volume),
        "vwap": None if vwap is None else _to_float(vwap),
        "trade_count": _to_int_or_none(trade_count),
    }


def normalize_alpaca_bars(session_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    grouped = payload.get("bars", {})
    if not isinstance(grouped, dict):
        return bars

    for symbol, symbol_bars in grouped.items():
        for item in symbol_bars or []:
            close = item.get("c")
            timestamp = item.get("t")
            if close is None or not timestamp:
                continue
            if not _is_finite_positive(close):
                continue
            bars.append(build_replay_bar(
                session_id=session_id,
                source="alpaca",
                symbol=symbol,
                timestamp=timestamp,
                open_price=item.get("o"),
                high=item.get("h"),
                low=item.get("l"),
                close=close,
                volume=item.get("v", 0),
                vwap=item.get("vw"),
                trade_count=item.get("n"),
            ))
    return bars


def normalize_yfinance_frame(session_id: str, symbols: Iterable[str], frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []

    clean_symbols = _clean_symbols(symbols)
    bars: list[dict[str, Any]] = []

    for symbol in clean_symbols:
        try:
            if len(clean_symbols) == 1 and "Close" in frame.columns:
                symbol_frame = frame
            else:
                symbol_frame = frame[symbol]
        except Exception:
            continue

        for timestamp, row in symbol_frame.iterrows():
            close = row.get("Close")
            if close is None:
                continue
            if not _is_finite_positive(close):
                continue
            bars.append(build_replay_bar(
                session_id=session_id,
                source="yfinance",
                symbol=symbol,
                timestamp=timestamp,
                open_price=row.get("Open"),
                high=row.get("High"),
                low=row.get("Low"),
                close=close,
                volume=row.get("Volume", 0),
            ))
    return bars


def _next_day(value: date) -> date:
    return value + timedelta(days=1)


def alpaca_timeframe(interval: str) -> str:
    mapping = {
        "1m": "1Min",
        "2m": "2Min",
        "5m": "5Min",
        "15m": "15Min",
        "30m": "30Min",
        "60m": "1Hour",
    }
    return mapping.get(interval, interval)


class MarketReplayService:
    async def get_status(self, db: Any) -> dict[str, Any]:
        doc = await db.settings.find_one({"key": ACTIVE_REPLAY_SETTING}, {"_id": 0})
        return doc.get("value", {"active": False}) if doc else {"active": False}

    async def start_replay(
        self,
        db: Any,
        *,
        session_id: str,
        speed: float = 1.0,
        loop: bool = False,
    ) -> dict[str, Any]:
        session = await db[REPLAY_SESSIONS_COLLECTION].find_one({"session_id": session_id}, {"_id": 0})
        if not session:
            raise ValueError(f"Replay session '{session_id}' not found.")

        first_bar = await db[REPLAY_BARS_COLLECTION].find_one(
            {"session_id": session_id},
            {"_id": 0},
            sort=[("timestamp", 1)],
        )
        last_bar = await db[REPLAY_BARS_COLLECTION].find_one(
            {"session_id": session_id},
            {"_id": 0},
            sort=[("timestamp", -1)],
        )
        if not first_bar or not last_bar:
            raise ValueError(f"Replay session '{session_id}' has no bars.")

        first_timestamp = first_bar["timestamp"]
        last_timestamp = last_bar["timestamp"]
        duration_seconds = max(0.0, (_parse_utc_iso(last_timestamp) - _parse_utc_iso(first_timestamp)).total_seconds())
        state = {
            "active": True,
            "session_id": session_id,
            "source": session.get("source"),
            "symbols": session.get("symbols", []),
            "speed": float(speed),
            "loop": bool(loop),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
            "duration_seconds": duration_seconds,
        }
        await db.settings.update_one(
            {"key": ACTIVE_REPLAY_SETTING},
            {"$set": {"value": state}},
            upsert=True,
        )
        return state

    async def stop_replay(self, db: Any) -> dict[str, Any]:
        state = await self.get_status(db)
        state = {**state, "active": False, "stopped_at": datetime.now(timezone.utc).isoformat()}
        await db.settings.update_one(
            {"key": ACTIVE_REPLAY_SETTING},
            {"$set": {"value": state}},
            upsert=True,
        )
        return state

    async def store_imported_bars(
        self,
        db: Any,
        *,
        session_id: str,
        source: str,
        symbols: list[str],
        trading_date: date,
        interval: str,
        bars: list[dict[str, Any]],
        name: str | None = None,
        provider_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_doc = {
            "session_id": session_id,
            "name": name or f"{source} {trading_date.isoformat()} {', '.join(symbols)}",
            "source": source,
            "symbols": symbols,
            "trading_date": trading_date.isoformat(),
            "interval": interval,
            "bar_count": len(bars),
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "provider_metadata": provider_metadata or {},
        }

        await db[REPLAY_BARS_COLLECTION].delete_many({"session_id": session_id})
        if bars:
            await db[REPLAY_BARS_COLLECTION].insert_many(bars)
        await db[REPLAY_SESSIONS_COLLECTION].update_one(
            {"session_id": session_id},
            {"$set": session_doc},
            upsert=True,
        )
        return session_doc

    async def import_yfinance_session(
        self,
        db: Any,
        *,
        symbols: list[str],
        trading_date: date,
        interval: str = "1m",
        include_prepost: bool = False,
        name: str | None = None,
    ) -> dict[str, Any]:
        import yfinance as yf

        clean_symbols = _clean_symbols(symbols)
        session_id = build_session_id("yfinance", clean_symbols, trading_date, interval)
        end_date = _next_day(trading_date)

        loop = asyncio.get_event_loop()
        frame = await loop.run_in_executor(
            None,
            lambda: yf.download(
                tickers=" ".join(clean_symbols),
                start=trading_date.isoformat(),
                end=end_date.isoformat(),
                interval=interval,
                group_by="ticker",
                auto_adjust=False,
                prepost=include_prepost,
                progress=False,
                threads=True,
            ),
        )
        bars = normalize_yfinance_frame(session_id, clean_symbols, frame)
        return await self.store_imported_bars(
            db,
            session_id=session_id,
            source="yfinance",
            symbols=clean_symbols,
            trading_date=trading_date,
            interval=interval,
            bars=bars,
            name=name,
            provider_metadata={"include_prepost": include_prepost},
        )

    async def import_alpaca_session(
        self,
        db: Any,
        *,
        symbols: list[str],
        trading_date: date,
        interval: str = "1m",
        api_key: str | None = None,
        api_secret: str | None = None,
        feed: str = "iex",
        name: str | None = None,
    ) -> dict[str, Any]:
        import aiohttp

        clean_symbols = _clean_symbols(symbols)
        session_id = build_session_id("alpaca", clean_symbols, trading_date, interval)
        key = api_key or os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
        secret = api_secret or os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise ValueError("Alpaca API key and secret are required for Alpaca replay imports.")

        start_dt = datetime.combine(trading_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(_next_day(trading_date), time.min, tzinfo=timezone.utc)
        params: dict[str, Any] = {
            "symbols": ",".join(clean_symbols),
            "timeframe": alpaca_timeframe(interval),
            "start": start_dt.isoformat().replace("+00:00", "Z"),
            "end": end_dt.isoformat().replace("+00:00", "Z"),
            "limit": 10000,
            "adjustment": "raw",
            "feed": feed,
            "sort": "asc",
        }
        headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}

        payload = {"bars": {}}
        page_token = None
        async with aiohttp.ClientSession() as session:
            while True:
                request_params = dict(params)
                if page_token:
                    request_params["page_token"] = page_token
                async with session.get("https://data.alpaca.markets/v2/stocks/bars", params=request_params, headers=headers) as resp:
                    data = await resp.json()
                    if resp.status >= 400:
                        raise RuntimeError(data.get("message", f"Alpaca replay import failed with HTTP {resp.status}"))
                    for symbol, symbol_bars in data.get("bars", {}).items():
                        payload["bars"].setdefault(symbol, []).extend(symbol_bars or [])
                    page_token = data.get("next_page_token")
                    if not page_token:
                        break

        bars = normalize_alpaca_bars(session_id, payload)
        return await self.store_imported_bars(
            db,
            session_id=session_id,
            source="alpaca",
            symbols=clean_symbols,
            trading_date=trading_date,
            interval=interval,
            bars=bars,
            name=name,
            provider_metadata={"feed": feed},
        )


async def _find_valid_replay_bar(db: Any, session_id: str, symbol: str, target_iso: str) -> dict[str, Any] | None:
    query = {"session_id": session_id, "symbol": symbol, "timestamp": {"$lte": target_iso}}
    recent_bars = await db[REPLAY_BARS_COLLECTION].find(query, {"_id": 0}).sort("timestamp", -1).limit(500).to_list(500)
    for bar in recent_bars:
        if not _is_finite_positive(bar.get("close")):
            continue
        return bar

    earliest_bars = await db[REPLAY_BARS_COLLECTION].find(
        {"session_id": session_id, "symbol": symbol},
        {"_id": 0},
    ).sort("timestamp", 1).limit(500).to_list(500)
    for bar in earliest_bars:
        if not _is_finite_positive(bar.get("close")):
            continue
        return bar

    return None


async def get_active_replay_price(db: Any, symbol: str, now: datetime | None = None) -> dict[str, Any] | None:
    doc = await db.settings.find_one({"key": ACTIVE_REPLAY_SETTING}, {"_id": 0})
    state = doc.get("value", {}) if doc else {}
    if not state.get("active"):
        return None

    clean_symbol = str(symbol).strip().upper()
    if state.get("symbols") and clean_symbol not in state["symbols"]:
        return None

    session_id = state.get("session_id")
    first_timestamp = state.get("first_timestamp")
    started_at = state.get("started_at")
    if not session_id or not first_timestamp or not started_at:
        return None

    current_time = now or datetime.now(timezone.utc)
    elapsed = max(0.0, (current_time - _parse_utc_iso(started_at)).total_seconds()) * float(state.get("speed", 1.0))
    duration = float(state.get("duration_seconds") or 0.0)
    if state.get("loop") and duration > 0:
        elapsed = elapsed % duration
    elif duration > 0:
        elapsed = min(elapsed, duration)

    target = _parse_utc_iso(first_timestamp) + timedelta(seconds=elapsed)
    target_iso = target.isoformat()
    bar = await _find_valid_replay_bar(db, session_id, clean_symbol, target_iso)
    if not bar:
        return None

    return {
        "session_id": session_id,
        "symbol": clean_symbol,
        "price": float(bar["close"]),
        "timestamp": bar["timestamp"],
        "bar": bar,
    }
