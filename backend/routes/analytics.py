"""Analytics API routes.

Provides endpoints for portfolio analytics and attribution.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth import get_current_user, TokenData


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


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


class AttributionData(BaseModel):
    strategy: str
    pnl: float
    allocation: float


class RegimeData(BaseModel):
    regime: str
    count: int
    win_rate: float


@router.get("/portfolio", response_model=PortfolioMetrics)
async def get_portfolio_metrics(
    timeframe: str = Query("1d"),
    current_user: TokenData = Depends(get_current_user)
):
    """Get portfolio metrics."""
    # In production, these would be calculated from actual data
    return PortfolioMetrics(
        total_value=250000,
        total_pnl=15420.50,
        daily_pnl=1234.56,
        total_return=6.57,
        sharpe_ratio=1.85,
        max_drawdown=8.5,
        win_rate=0.68,
        avg_win=450,
        avg_loss=180,
        turnover=0.15,
        trade_count=156
    )


@router.get("/attribution")
async def get_attribution(
    current_user: TokenData = Depends(get_current_user)
):
    """Get P&L attribution by strategy."""
    return {
        "attribution": [
            {"strategy": "Momentum", "pnl": 8500, "allocation": 0.4},
            {"strategy": "Mean Reversion", "pnl": 4200, "allocation": 0.3},
            {"strategy": "Breakout", "pnl": 2100, "allocation": 0.2},
            {"strategy": "Earnings", "pnl": -380, "allocation": 0.1}
        ]
    }


@router.get("/regimes")
async def get_regimes(
    current_user: TokenData = Depends(get_current_user)
):
    """Get regime analysis."""
    return {
        "regimes": [
            {"regime": "trending_up", "count": 45, "win_rate": 0.75},
            {"regime": "trending_down", "count": 32, "win_rate": 0.55},
            {"regime": "range_bound", "count": 56, "win_rate": 0.62},
            {"regime": "volatile", "count": 23, "win_rate": 0.48}
        ]
    }


@router.get("/pnl/daily")
async def get_daily_pnl(
    days: int = Query(30),
    current_user: TokenData = Depends(get_current_user)
):
    """Get daily P&L for charting."""
    return {
        "daily_pnl": [
            {"date": "2024-01-30", "pnl": 234.50, "trades": 5},
            {"date": "2024-01-29", "pnl": -123.00, "trades": 3},
            {"date": "2024-01-28", "pnl": 567.80, "trades": 7},
            {"date": "2024-01-27", "pnl": 890.25, "trades": 6},
            {"date": "2024-01-26", "pnl": -234.00, "trades": 4}
        ]
    }


__all__ = ["router"]