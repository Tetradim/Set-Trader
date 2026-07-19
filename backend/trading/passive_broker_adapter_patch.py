"""Install passive-order capabilities on production broker adapters.

The base broker interface predates long-lived resting orders. This compatibility
patch adds two optional methods used by passive range scalping without forcing
experimental adapters to claim support they do not yet have:

``get_order_status(order_id)``
    Return cumulative broker fill evidence for one order.

``get_quote_snapshot(symbol)``
    Return bid, ask, last, and a broker timestamp when available.
"""

from __future__ import annotations

from datetime import datetime, timezone

from brokers.alpaca_adapter import AlpacaAdapter
from brokers.tradier_adapter import API_BASE, TradierAdapter
from brokers.base import BrokerOrder, OrderSide, OrderType


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _alpaca_get_order_status(self: AlpacaAdapter, broker_order_id: str) -> BrokerOrder | None:
    if not broker_order_id:
        return None
    session = await self._get_session()
    async with session.get(
        f"{self._base_url()}/v2/orders/{broker_order_id}",
        headers=self._headers(),
    ) as response:
        if response.status != 200:
            return None
        data = await response.json()
    order = BrokerOrder(
        symbol=str(data.get("symbol") or "").upper(),
        side=OrderSide(str(data.get("side") or "BUY").upper()),
        order_type=OrderType(str(data.get("type") or "LIMIT").upper()),
        quantity=float(data.get("qty") or 0),
        limit_price=float(data.get("limit_price") or 0) or None,
        broker_order_id=str(data.get("id") or broker_order_id),
    )
    return self._apply_order_payload(order, data)


async def _alpaca_get_quote_snapshot(self: AlpacaAdapter, symbol: str) -> dict:
    session = await self._get_session()
    async with session.get(
        f"{self._base_url()}/v2/stocks/{symbol}/quotes/latest",
        headers=self._headers(),
    ) as response:
        data = await response.json()
    quote = data.get("quote") or {}
    bid = float(quote.get("bp") or 0)
    ask = float(quote.get("ap") or 0)
    return {
        "bid": bid,
        "ask": ask,
        "last": ask or bid,
        "bid_size": float(quote.get("bs") or 0),
        "ask_size": float(quote.get("as") or 0),
        "timestamp": str(quote.get("t") or _utc_iso()),
        "source": "alpaca",
    }


async def _tradier_get_order_status(self: TradierAdapter, broker_order_id: str) -> BrokerOrder | None:
    if not broker_order_id:
        return None
    session = await self._get_session()
    async with session.get(
        f"{API_BASE}/accounts/{self._acct()}/orders/{broker_order_id}",
        headers=self._headers(),
    ) as response:
        if response.status != 200:
            return None
        data = await response.json()
    payload = data.get("order") or {}
    status = str(payload.get("status") or "")
    side = str(payload.get("side") or "buy").split("_")[-1].upper()
    order_type = str(payload.get("type") or "limit").upper()
    quantity = float(payload.get("quantity") or 0)
    remaining = float(payload.get("remaining_quantity") or 0)
    filled_quantity = float(
        payload.get("exec_quantity")
        or payload.get("filled_quantity")
        or max(0.0, quantity - remaining)
    )
    filled_price = float(payload.get("avg_fill_price") or payload.get("last_fill_price") or 0)
    return BrokerOrder(
        symbol=str(payload.get("symbol") or "").upper(),
        side=OrderSide(side),
        order_type=OrderType(order_type),
        quantity=quantity,
        limit_price=float(payload.get("price") or 0) or None,
        broker_order_id=str(payload.get("id") or broker_order_id),
        status=status,
        filled_price=filled_price,
        filled_quantity=filled_quantity,
        error=str(payload.get("reason_description") or ""),
    )


async def _tradier_get_quote_snapshot(self: TradierAdapter, symbol: str) -> dict:
    session = await self._get_session()
    async with session.get(
        f"{API_BASE}/markets/quotes",
        headers=self._headers(),
        params={"symbols": symbol},
    ) as response:
        data = await response.json()
    quote = (data.get("quotes") or {}).get("quote") or {}
    if isinstance(quote, list):
        quote = quote[0] if quote else {}
    return {
        "bid": float(quote.get("bid") or 0),
        "ask": float(quote.get("ask") or 0),
        "last": float(quote.get("last") or 0),
        "bid_size": float(quote.get("bidsize") or 0),
        "ask_size": float(quote.get("asksize") or 0),
        "timestamp": str(quote.get("trade_date") or _utc_iso()),
        "source": "tradier",
    }


AlpacaAdapter.get_order_status = _alpaca_get_order_status
AlpacaAdapter.get_quote_snapshot = _alpaca_get_quote_snapshot
TradierAdapter.get_order_status = _tradier_get_order_status
TradierAdapter.get_quote_snapshot = _tradier_get_quote_snapshot
