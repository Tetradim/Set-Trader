"""Trade history, portfolio, positions, loss logs, and general logs."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

import deps

router = APIRouter()


@router.get("/trades")
async def get_trades(limit: int = Query(50, le=200)):
    docs = await deps.db.trades.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return docs


@router.get("/loss-logs")
async def list_loss_logs():
    log_dir = deps.ROOT_DIR / "trade_logs" / "losses"
    if not log_dir.exists():
        return {"dates": []}
    dates = []
    for d in sorted(log_dir.iterdir(), reverse=True):
        if d.is_dir():
            files = [f.name for f in d.iterdir() if f.suffix == ".txt"]
            dates.append({"date": d.name, "count": len(files), "files": sorted(files, reverse=True)})
    return {"dates": dates}


@router.get("/loss-logs/{date}/{filename}")
async def get_loss_log(date: str, filename: str):
    filepath = deps.ROOT_DIR / "trade_logs" / "losses" / date / filename
    if not filepath.exists() or not filepath.suffix == ".txt":
        raise HTTPException(404, "Log file not found")
    return PlainTextResponse(filepath.read_text())


@router.get("/portfolio")
async def get_portfolio():
    profits_list = await deps.db.profits.find({}, {"_id": 0}).to_list(100)
    total_pnl = sum(p.get("total_pnl", 0) for p in profits_list)
    total_trades = sum(p.get("trade_count", 0) for p in profits_list)

    positions = []
    total_equity = 0
    for sym, pos in deps.engine._positions.items():
        if pos["qty"] > 0:
            cp = deps.engine._prices.get(sym, pos["avg_entry"])
            val = cp * pos["qty"]
            total_equity += val
            positions.append({
                "symbol": sym, "quantity": pos["qty"], "avg_entry": pos["avg_entry"],
                "current_price": cp, "market_value": round(val, 2),
                "unrealized_pnl": round((cp - pos["avg_entry"]) * pos["qty"], 2),
            })

    tickers = await deps.db.tickers.find({}, {"_id": 0}).to_list(100)
    total_buying_power = sum(t.get("base_power", 0) for t in tickers if t.get("enabled"))
    wins = await deps.db.trades.count_documents({"pnl": {"$gt": 0}})
    losses = await deps.db.trades.count_documents({"pnl": {"$lt": 0}})
    win_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0

    return {
        "total_pnl": round(total_pnl, 2), "total_equity": round(total_equity, 2),
        "buying_power": round(total_buying_power, 2), "total_trades": total_trades,
        "win_rate": win_rate, "positions": positions,
        "profits_by_symbol": {p["symbol"]: round(p.get("total_pnl", 0), 2) for p in profits_list},
    }


@router.get("/positions")
async def get_positions():
    positions = []
    for sym, pos in deps.engine._positions.items():
        if pos["qty"] > 0:
            cp = deps.engine._prices.get(sym, pos["avg_entry"])
            positions.append({
                "symbol": sym, "quantity": pos["qty"], "avg_entry": pos["avg_entry"],
                "current_price": cp, "market_value": round(cp * pos["qty"], 2),
                "unrealized_pnl": round((cp - pos["avg_entry"]) * pos["qty"], 2),
            })
    return positions


@router.get("/logs")
async def get_logs(limit: int = Query(100, le=500), level: str = "ALL"):
    docs = await deps.db.logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    if level != "ALL":
        docs = [d for d in docs if d.get("level", "").upper() == level.upper()]
    return docs
