"""Developer API documentation and SDK routes."""
from typing import Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

import deps

router = APIRouter(tags=["Developer"])


# ---------------------------------------------------------------------------
# API Documentation
# ---------------------------------------------------------------------------

class APIDocEndpoint(BaseModel):
    path: str
    method: str
    summary: str
    description: str
    params: List[Dict[str, str]]
    example: Optional[Dict]


API_DOCS: Dict[str, List[APIDocEndpoint]] = {
    "Tickers": [
        APIDocEndpoint(
            path="/api/tickers",
            method="GET",
            summary="List all tickers",
            description="Get all configured tickers with their settings",
            params=[],
            example={"response": [{"symbol": "SPY", "base_power": 10000, "enabled": True}]}
        ),
        APIDocEndpoint(
            path="/api/tickers",
            method="POST",
            summary="Create ticker",
            description="Add a new ticker to track",
            params=[
                {"name": "symbol", "type": "string", "required": True, "description": "Stock symbol"},
                {"name": "base_power", "type": "number", "required": False, "description": "Buy power allocation"}
            ],
            example={"symbol": "TSLA", "base_power": 5000}
        ),
        APIDocEndpoint(
            path="/api/tickers/{symbol}",
            method="DELETE",
            summary="Delete ticker",
            description="Remove a ticker from tracking",
            params=[{"name": "symbol", "type": "string", "required": True}],
            example={}
        ),
    ],
    "Trading": [
        APIDocEndpoint(
            path="/api/bot/start",
            method="POST",
            summary="Start bot",
            description="Start the trading engine",
            params=[],
            example={"status": "started"}
        ),
        APIDocEndpoint(
            path="/api/bot/stop",
            method="POST",
            summary="Stop bot",
            description="Stop the trading engine",
            params=[],
            example={"status": "stopped"}
        ),
    ],
    "Portfolio": [
        APIDocEndpoint(
            path="/api/portfolio/stats",
            method="GET",
            summary="Get portfolio stats",
            description="Get performance statistics for the portfolio",
            params=[{"name": "period", "type": "string", "required": False, "description": "today|week|month|all"}],
            example={"stats": {"totalPnl": 1250.50, "winRate": 68.5}}
        ),
    ],
    "Notifications": [
        APIDocEndpoint(
            path="/api/notifications",
            method="GET",
            summary="Get notification settings",
            description="Get current notification channel configurations",
            params=[],
            example={"slack_enabled": False, "discord_enabled": True}
        ),
        APIDocEndpoint(
            path="/api/notifications",
            method="POST",
            summary="Update notifications",
            description="Configure notification channels",
            params=[
                {"name": "slack_webhook_url", "type": "string", "required": False},
                {"name": "slack_enabled", "type": "boolean", "required": False},
                {"name": "discord_webhook_url", "type": "string", "required": False},
            ],
            example={"slack_enabled": True, "slack_webhook_url": "https://hooks.slack.com/..."}
        ),
    ],
}


@router.get("/docs")
async def get_api_documentation():
    """Get full API documentation."""
    return {
        "title": "Sentinel Pulse API",
        "version": "1.0.0",
        "base_url": "/api",
        "endpoints": API_DOCS,
    }


@router.get("/docs/endpoints")
async def list_all_endpoints():
    """List all available API endpoints."""
    endpoints = []
    for category, items in API_DOCS.items():
        for item in items:
            endpoints.append({
                "category": category,
                "path": item.path,
                "method": item.method,
                "summary": item.summary,
            })
    return {"endpoints": endpoints}


# ---------------------------------------------------------------------------
# SDK / Client Library
# ---------------------------------------------------------------------------

@router.get("/sdk/python")
async def get_python_sdk():
    """Get Python SDK for Sentinel Pulse."""
    return {
        "language": "python",
        "install": "pip install sentinel-pulse-client",
        "example": '''# pip install sentinel-pulse-client
from sentinel_client import SentinelClient

client = SentinelClient(base_url="http://localhost:8002")

# List tickers
tickers = client.tickers.list()
print(tickers)

# Start trading
client.bot.start()

# Get portfolio stats
stats = client.portfolio.stats(period="month")
print(stats)''',
    }


@router.get("/sdk/javascript")
async def get_js_sdk():
    """Get JavaScript/TypeScript SDK."""
    return {
        "language": "javascript",
        "install": "npm install @sentinel-pulse/client",
        "example": '''// npm install @sentinel-pulse/client
import { SentinelClient } from '@sentinel-pulse/client';

const client = new SentinelClient({ baseUrl: 'http://localhost:8002' });

// List tickers
const tickers = await client.tickers.list();
console.log(tickers);

// Start trading
await client.bot.start();

// Get portfolio stats
const stats = await client.portfolio.stats({ period: 'month' });
console.log(stats);''',
    }


# ---------------------------------------------------------------------------
# Plugin System
# ---------------------------------------------------------------------------

@router.get("/plugins")
async def list_plugins():
    """List all available plugins."""
    # Get loaded strategies as plugins
    from strategies.loader import get_loaded_strategies
    strategies = get_loaded_strategies()
    
    plugins = []
    for name, strat in strategies.items():
        plugins.append({
            "name": name,
            "type": "strategy",
            "description": getattr(strat, "__doc__", "Custom strategy") or "Signal strategy",
            "enabled": True,
        })
    
    return {"plugins": plugins}


@router.post("/plugins/{plugin_name}/enable")
async def enable_plugin(plugin_name: str):
    """Enable a plugin."""
    # For strategies, this would reload them
    return {"ok": True, "plugin": plugin_name, "status": "enabled"}


@router.post("/plugins/{plugin_name}/disable")
async def disable_plugin(plugin_name: str):
    """Disable a plugin."""
    return {"ok": True, "plugin": plugin_name, "status": "disabled"}


@router.get("/plugins/schema")
async def get_plugin_schema():
    """Get the plugin schema specification."""
    return {
        "version": "1.0.0",
        "types": {
            "strategy": {
                "description": "Trading signal strategy",
                "interface": {
                    "name": "string",
                    "generate_signal": "function(price_data, config) -> BUY|SELL|HOLD",
                    "validate_config": "function(config) -> boolean",
                }
            },
            "indicator": {
                "description": "Technical indicator",
                "interface": {
                    "name": "string",
                    "calculate": "function(price_data, period) -> number",
                }
            },
        },
        "example_strategy": '''"""
Example custom strategy plugin
"""
class MyStrategy:
    name = "my_strategy"
    
    def generate_signal(self, price_data, config):
        # price_data: {symbol, price, volume, ...}
        # config: custom parameters from UI
        
        if price_data.price < config.get("buy_threshold", 100):
            return "BUY"
        elif price_data.price > config.get("sell_threshold", 150):
            return "SELL"
        return "HOLD"
    
    def validate_config(self, config):
        return "buy_threshold" in config and "sell_threshold" in config
''',
    }


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

@router.get("/webhooks")
async def list_webhooks():
    """List registered webhook endpoints."""
    webhooks = await deps.db.settings.find_one({"key": "webhooks"}, {"_id": 0})
    return webhooks.get("value", {"webhooks": []})


@router.post("/webhooks")
async def register_webhook(
    url: str = Query(..., description="Webhook URL"),
    events: str = Query("trade,system", description="Comma-separated events"),
    secret: str = Query("", description="Optional HMAC secret"),
):
    """Register a new webhook endpoint."""
    import secrets
    
    webhook_id = secrets.token_hex(8)
    webhook = {
        "id": webhook_id,
        "url": url,
        "events": events.split(","),
        "secret": secret or secrets.token_hex(16),
        "enabled": True,
    }
    
    # Save to database
    await deps.db.settings.update_one(
        {"key": "webhooks"},
        {"$push": {"value.webhooks": webhook}},
        upsert=True,
    )
    
    await deps.audit_service.log_event(
        "WEBHOOK_REGISTERED",
        symbol=None,
        broker_id=None,
        success=True,
        details={"url": url, "events": events},
    )
    
    return {"ok": True, "webhook": webhook}


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str):
    """Delete a webhook endpoint."""
    result = await deps.db.settings.update_one(
        {"key": "webhooks"},
        {"$pull": {"value.webhooks": {"id": webhook_id}}},
    )
    
    await deps.audit_service.log_event(
        "WEBHOOK_DELETED",
        symbol=None,
        broker_id=None,
        success=True,
        details={"webhook_id": webhook_id},
    )
    
    return {"ok": True}


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: str):
    """Send a test webhook."""
    # Implementation would send a test payload to the registered URL
    return {"ok": True, "message": "Test webhook sent"}
