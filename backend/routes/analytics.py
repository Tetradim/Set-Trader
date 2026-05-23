"""Analytics API routes calculated from stored trading data."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

import deps
from auth import TokenData, get_current_user


router = APIRouter(prefix="/analytics", tags=["analytics"])


class PortfolioMetrics(BaseModel):
    total_value: float = 0
    total_pnl: float = 0
    daily_pnl: float = 0
    total_return: float = 0
    sharpe_ratio: float = 0
    max_drawdown: float = 0
    win_rate: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    turnover: float = 0
    trade_count: int = 0


async def _load_trade_docs(limit: int = 5000) -> list[dict]:
    return await deps.db.trades.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)


def _parse_timestamp(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@router.get("/portfolio", response_model=PortfolioMetrics)
async def get_portfolio_metrics(
    timeframe: str = Query("1d"),
    current_user: TokenData = Depends(get_current_user),
):
    """Get portfolio metrics from trades, profits, and open engine positions."""
    trades = await _load_trade_docs()
    profits = await deps.db.profits.find({}, {"_id": 0}).to_list(500)
    total_pnl = sum(float(p.get("total_pnl", 0) or 0) for p in profits)

    now = datetime.now(timezone.utc)
    day_start = now - timedelta(days=1)
    pnl_values = [float(t.get("pnl", 0) or 0) for t in trades]
    wins = [pnl for pnl in pnl_values if pnl > 0]
    losses = [pnl for pnl in pnl_values if pnl < 0]
    daily_pnl = sum(
        float(t.get("pnl", 0) or 0)
        for t in trades
        if (ts := _parse_timestamp(t.get("timestamp"))) and ts >= day_start
    )

    open_value = 0.0
    if deps.engine:
        for symbol, position in deps.engine._positions.items():
            quantity = float(position.get("qty", 0) or 0)
            if quantity <= 0:
                continue
            current_price = float(deps.engine._prices.get(symbol, position.get("avg_entry", 0)) or 0)
            open_value += quantity * current_price

    base_value = open_value - total_pnl
    total_return = (total_pnl / base_value * 100) if base_value else 0
    win_rate = (len(wins) / (len(wins) + len(losses))) if (wins or losses) else 0

    return PortfolioMetrics(
        total_value=round(open_value + total_pnl, 2),
        total_pnl=round(total_pnl, 2),
        daily_pnl=round(daily_pnl, 2),
        total_return=round(total_return, 2),
        win_rate=round(win_rate, 4),
        avg_win=round(sum(wins) / len(wins), 2) if wins else 0,
        avg_loss=round(sum(losses) / len(losses), 2) if losses else 0,
        trade_count=len(trades),
    )


@router.get("/attribution")
async def get_attribution(current_user: TokenData = Depends(get_current_user)):
    """Get P&L attribution by recorded strategy."""
    trades = await _load_trade_docs()
    pnl_by_strategy = defaultdict(float)
    total_abs = 0.0
    for trade in trades:
        strategy = trade.get("strategy") or trade.get("reason") or "unclassified"
        pnl = float(trade.get("pnl", 0) or 0)
        pnl_by_strategy[strategy] += pnl
        total_abs += abs(pnl)

    attribution = [
        {
            "strategy": strategy,
            "pnl": round(pnl, 2),
            "allocation": round(abs(pnl) / total_abs, 4) if total_abs else 0,
        }
        for strategy, pnl in sorted(pnl_by_strategy.items())
    ]
    return {"attribution": attribution}


@router.get("/regimes")
async def get_regimes(current_user: TokenData = Depends(get_current_user)):
    """Get performance grouped by recorded market regime."""
    trades = await _load_trade_docs()
    groups: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        groups[trade.get("regime") or "unclassified"].append(float(trade.get("pnl", 0) or 0))

    regimes = []
    for regime, pnls in sorted(groups.items()):
        wins = sum(1 for pnl in pnls if pnl > 0)
        losses = sum(1 for pnl in pnls if pnl < 0)
        regimes.append({
            "regime": regime,
            "count": len(pnls),
            "win_rate": round(wins / (wins + losses), 4) if wins + losses else 0,
        })
    return {"regimes": regimes}


@router.get("/pnl/daily")
async def get_daily_pnl(
    days: int = Query(30, ge=1, le=365),
    current_user: TokenData = Depends(get_current_user),
):
    """Get daily P&L from stored trades."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    daily: dict[str, dict] = defaultdict(lambda: {"date": "", "pnl": 0.0, "trades": 0})

    for trade in await _load_trade_docs():
        timestamp = _parse_timestamp(trade.get("timestamp"))
        if not timestamp or timestamp < since:
            continue
        day = timestamp.date().isoformat()
        daily[day]["date"] = day
        daily[day]["pnl"] += float(trade.get("pnl", 0) or 0)
        daily[day]["trades"] += 1

    return {
        "daily_pnl": [
            {"date": day, "pnl": round(data["pnl"], 2), "trades": data["trades"]}
            for day, data in sorted(daily.items(), reverse=True)
        ]
    }


__all__ = ["router"]
