"""Portfolio analytics routes."""
from typing import Optional
from fastapi import APIRouter, Query
from datetime import datetime, timedelta
from collections import defaultdict

import deps

router = APIRouter(tags=["Portfolio"])


@router.get("/portfolio/stats")
async def get_portfolio_stats(period: str = Query("month", regex="^(today|week|month|all)$")):
    """Get portfolio performance statistics."""
    now = datetime.utcnow()
    
    # Calculate date range
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    else:
        start_date = datetime(2000, 1, 1)
    
    # Get all trades in period
    trades = await deps.db.trades.find({
        "timestamp": {"$gte": start_date.isoformat()}
    }).to_list(10000)
    
    # Calculate stats
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) < 0]
    
    total_wins = sum(t.get("pnl", 0) for t in wins)
    total_losses = sum(t.get("pnl", 0) for t in losses)
    
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = total_wins / len(wins) if wins else 0
    avg_loss = total_losses / len(losses) if losses else 0
    profit_factor = abs(total_wins / total_losses) if total_losses != 0 else 0
    
    # Get account balance for return %
    account_balance = 100000  # Default
    settings = await deps.db.settings.find_one({"key": "account_balance"})
    if settings and settings.get("value"):
        account_balance = settings.get("value", 100000)
    
    # Calculate total P&L
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    total_pnl_pct = (total_pnl / account_balance * 100) if account_balance > 0 else 0
    
    # Mock values for sharpe/mdd (would require historical data)
    sharpe_ratio = 1.5
    max_drawdown = -5.2
    
    return {
        "stats": {
            "totalValue": 0,
            "totalPnl": total_pnl,
            "totalPnLPct": total_pnl_pct,
            "winRate": win_rate,
            "avgWin": avg_win,
            "avgLoss": avg_loss,
            "profitFactor": profit_factor,
            "maxDrawdown": max_drawdown,
            "sharpeRatio": sharpe_ratio,
        }
    }


@router.get("/positions/by-broker")
async def get_positions_by_broker():
    """Get positions grouped by broker."""
    # Get all tickers with broker allocations
    tickers = await deps.db.tickers.find({}).to_list(100)
    
    # Get current positions from engine
    positions = deps.engine._positions if hasattr(deps.engine, '_positions') else {}
    
    # Group by broker
    broker_totals = defaultdict(lambda: {"totalValue": 0, "unrealizedPnl": 0, "positions": []})
    
    for ticker in tickers:
        broker_ids = ticker.get("broker_ids", [])
        allocations = ticker.get("broker_allocations", {})
        
        for broker_id in broker_ids:
            allocation = allocations.get(broker_id, 0)
            if allocation > 0:
                pos = positions.get(ticker.get("symbol"))
                value = (pos.get("quantity", 0) * pos.get("current_price", 0)) if pos else 0
                pnl = pos.get("unrealized_pnl", 0) if pos else 0
                
                broker_totals[broker_id]["totalValue"] += value * (allocation / ticker.get("base_power", 1))
                broker_totals[broker_id]["unrealizedPnl"] += pnl * (allocation / ticker.get("base_power", 1))
    
    # Build response
    groups = []
    for broker_id, data in broker_totals.items():
        broker_name = broker_id.replace("_", " ").title()
        groups.append({
            "brokerId": broker_id,
            "brokerName": broker_name,
            "totalValue": data["totalValue"],
            "unrealizedPnl": data["unrealizedPnl"],
            "positions": data["positions"],
        })
    
    # Add combined total
    total_value = sum(g["totalValue"] for g in groups)
    total_pnl = sum(g["unrealizedPnl"] for g in groups)
    
    return {
        "groups": groups,
        "total": {"totalValue": total_value, "unrealizedPnl": total_pnl}
    }


@router.get("/portfolio/daily-returns")
async def get_daily_returns(period: str = Query("month", regex="^(today|week|month|all)$")):
    """Get daily returns for charting."""
    now = datetime.utcnow()
    
    if period == "today":
        days = 1
    elif period == "week":
        days = 7
    elif period == "month":
        days = 30
    else:
        days = 90
    
    start_date = now - timedelta(days=days)
    
    # Get all trades
    trades = await deps.db.trades.find({
        "timestamp": {"$gte": start_date.isoformat()}
    }).to_list(10000)
    
    # Group by date
    daily_pnl = defaultdict(float)
    for trade in trades:
        ts = trade.get("timestamp", "")
        if ts:
            date = ts.split("T")[0]
            daily_pnl[date] += trade.get("pnl", 0)
    
    # Get account balance
    account_balance = 100000
    settings = await deps.db.settings.find_one({"key": "account_balance"})
    if settings and settings.get("value"):
        account_balance = settings.get("value", 100000)
    
    # Build returns array
    returns = []
    for i in range(days):
        date = (now - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
        pnl = daily_pnl.get(date, 0)
        ret = (pnl / account_balance * 100) if account_balance > 0 else 0
        returns.append({"date": date, "return": round(ret, 2)})
    
    return {"returns": returns}


@router.get("/portfolio/export")
async def export_portfolio(format: str = Query("csv", regex="^(csv|json)$"), period: str = Query("month")):
    """Export portfolio data."""
    now = datetime.utcnow()
    
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    else:
        start_date = datetime(2000, 1, 1)
    
    trades = await deps.db.trades.find({
        "timestamp": {"$gte": start_date.isoformat()}
    }).sort("timestamp", -1).to_list(1000)
    
    if format == "csv":
        # Generate CSV
        lines = ["timestamp,symbol,side,price,quantity,pnl,order_type"]
        for t in trades:
            lines.append(
                f"{t.get('timestamp','')},{t.get('symbol','')},{t.get('side','')},"
                f"{t.get('price',0):.2f},{t.get('quantity',0):.4f},"
                f"{t.get('pnl',0):.2f},{t.get('order_type','')}"
            )
        return "\n".join(lines)
    
    return {"trades": trades}


# ---------------------------------------------------------------------------
# Tax Report
# ---------------------------------------------------------------------------

@router.get("/portfolio/tax-report")
async def get_tax_report(year: int = Query(default=None)):
    """Get tax report for a given year."""
    if not year:
        year = datetime.now().year
    
    start_date = datetime(year, 1, 1)
    end_date = datetime(year, 12, 31, 23, 59, 59)
    
    # Get all trades in year
    trades = await deps.db.trades.find({
        "timestamp": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        },
        "side": {"$in": ["SELL", "STOP", "TRAILING_STOP"]}
    }).to_list(10000)
    
    # Calculate realized gains/losses
    realized = {"short_term": 0, "long_term": 0, "total": 0}
    by_symbol = defaultdict(lambda: {"gains": 0, "losses": 0, "count": 0})
    
    for trade in trades:
        pnl = trade.get("pnl", 0)
        symbol = trade.get("symbol", "UNKNOWN")
        
        if pnl >= 0:
            realized["short_term"] += pnl
            by_symbol[symbol]["gains"] += pnl
        else:
            realized["short_term"] += pnl  # losses
            by_symbol[symbol]["losses"] += abs(pnl)
        
        by_symbol[symbol]["count"] += 1
    
    realized["total"] = realized["short_term"] + realized["long_term"]
    
    return {
        "year": year,
        "realized": realized,
        "by_symbol": dict(by_symbol),
        "trade_count": len(trades),
    }
