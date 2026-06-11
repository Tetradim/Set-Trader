"""Market replay endpoints for importing and inspecting Pulse-owned sessions."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import deps
from replay_service import MarketReplayService, REPLAY_BARS_COLLECTION, REPLAY_SESSIONS_COLLECTION


router = APIRouter(tags=["Replay"])
replay_service = MarketReplayService()


class YFinanceReplayImportRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=25)
    trading_date: date
    interval: Literal["1m", "2m", "5m", "15m", "30m", "60m"] = "1m"
    include_prepost: bool = False
    name: str | None = Field(None, max_length=120)


class AlpacaReplayImportRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=100)
    trading_date: date
    interval: Literal["1m", "2m", "5m", "15m", "30m", "60m"] = "1m"
    feed: Literal["iex", "sip", "otc"] = "iex"
    api_key: str | None = Field(None, max_length=200)
    api_secret: str | None = Field(None, max_length=200)
    name: str | None = Field(None, max_length=120)


class StartReplayRequest(BaseModel):
    speed: float = Field(1.0, ge=0.01, le=240.0)
    loop: bool = False


@router.get("/replay/sessions")
async def list_replay_sessions(limit: int = Query(50, ge=1, le=250)):
    sessions = await deps.db[REPLAY_SESSIONS_COLLECTION].find({}, {"_id": 0}).sort("imported_at", -1).to_list(limit)
    return {"sessions": sessions}


@router.get("/replay/sessions/{session_id}")
async def get_replay_session(session_id: str, limit: int = Query(500, ge=1, le=5000)):
    session = await deps.db[REPLAY_SESSIONS_COLLECTION].find_one({"session_id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(404, f"Replay session '{session_id}' not found.")
    bars = await deps.db[REPLAY_BARS_COLLECTION].find({"session_id": session_id}, {"_id": 0}).sort([
        ("timestamp", 1),
        ("symbol", 1),
    ]).to_list(limit)
    return {"session": session, "bars": bars}


@router.get("/replay/status")
async def get_replay_status():
    return {"replay": await replay_service.get_status(deps.db)}


@router.post("/replay/sessions/{session_id}/start")
async def start_replay_session(session_id: str, body: StartReplayRequest):
    if not getattr(deps.engine, "simulate_24_7", False):
        raise HTTPException(400, "Replay can only be started while Simulate 24/7 paper mode is enabled.")
    try:
        state = await replay_service.start_replay(
            deps.db,
            session_id=session_id,
            speed=body.speed,
            loop=body.loop,
        )
        return {"ok": True, "replay": state}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/replay/stop")
async def stop_replay_session():
    return {"ok": True, "replay": await replay_service.stop_replay(deps.db)}


@router.post("/replay/import/yfinance")
async def import_yfinance_session(body: YFinanceReplayImportRequest):
    try:
        session = await replay_service.import_yfinance_session(
            deps.db,
            symbols=body.symbols,
            trading_date=body.trading_date,
            interval=body.interval,
            include_prepost=body.include_prepost,
            name=body.name,
        )
        return {"ok": True, "session": session}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/replay/import/alpaca")
async def import_alpaca_session(body: AlpacaReplayImportRequest):
    try:
        session = await replay_service.import_alpaca_session(
            deps.db,
            symbols=body.symbols,
            trading_date=body.trading_date,
            interval=body.interval,
            api_key=body.api_key,
            api_secret=body.api_secret,
            feed=body.feed,
            name=body.name,
        )
        return {"ok": True, "session": session}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
