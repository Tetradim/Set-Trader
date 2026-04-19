"""Markets API — market status, FX rates, and currency display preference."""
from fastapi import APIRouter, HTTPException, Query

import deps
from markets import MARKETS, detect_market_from_symbol
from audit_service import audit_service

router = APIRouter(tags=["Markets"])


@router.get("/markets")
async def list_markets():
    """List all supported markets with current status, local time, and config."""
    return {"markets": [m.to_dict() for m in MARKETS.values()]}


@router.get("/markets/{code}")
async def get_market(code: str):
    """Get a specific market's info and real-time status."""
    market = MARKETS.get(code.upper())
    if not market:
        raise HTTPException(404, f"Market '{code}' not found. Valid: {list(MARKETS.keys())}")
    return market.to_dict()


@router.get("/fx-rates")
async def get_fx_rates():
    """Get current FX rates (native currency → USD) for all supported foreign markets."""
    rates = await deps.price_service.get_fx_rates()
    return {"rates": rates}


@router.get("/settings/currency-display")
async def get_currency_display():
    """Get the persisted currency display preference ('usd' or 'native')."""
    doc = await deps.db.settings.find_one({"key": "currency_display"}, {"_id": 0})
    mode = doc.get("value", "usd") if doc else "usd"
    return {"mode": mode}


@router.post("/settings/currency-display")
async def set_currency_display(mode: str = Query(..., description="'usd' or 'native'")):
    """Set the currency display preference. Persists across server restarts."""
    if mode not in ("usd", "native"):
        raise HTTPException(400, "mode must be 'usd' or 'native'")
    old_doc = await deps.db.settings.find_one({"key": "currency_display"}, {"_id": 0})
    old_mode = old_doc.get("value", "usd") if old_doc else "usd"
    await deps.db.settings.update_one(
        {"key": "currency_display"},
        {"$set": {"value": mode}},
        upsert=True,
    )
    await audit_service.log_setting_change("currency_display", old_mode, mode)
    return {"mode": mode}
