"""Alpaca broker adapter — API-first broker for algorithmic trading."""
import asyncio
import logging
import re
import uuid
from .base import BrokerAdapter, BrokerOpenOrder, BrokerOrder, BrokerPosition, BrokerAccountInfo, OrderSide, OrderType

logger = logging.getLogger("SentinelPulse")
_ORDER_TERMINAL_STATUSES = {"filled", "canceled", "cancelled", "expired", "rejected"}
_CLIENT_ORDER_ID_MAX_LENGTH = 48
_CLIENT_ORDER_ID_UNSAFE_RE = re.compile(r"[^A-Za-z0-9_-]")


class AlpacaAdapter(BrokerAdapter):
    broker_id = "alpaca"

    def _headers(self):
        return {
            "APCA-API-KEY-ID": self.config.get("api_key", ""),
            "APCA-API-SECRET-KEY": self.config.get("api_secret", ""),
        }

    def _base_url(self):
        is_paper = str(self.config.get("paper", "true")).lower() in ("true", "1", "yes")
        return "https://paper-api.alpaca.markets" if is_paper else "https://api.alpaca.markets"

    def _client_order_id_for(self, order: BrokerOrder) -> str:
        raw = str(order.client_order_id or order.idempotency_key or "").strip()
        if not raw:
            return ""

        safe = _CLIENT_ORDER_ID_UNSAFE_RE.sub("-", raw)
        if len(safe) <= _CLIENT_ORDER_ID_MAX_LENGTH:
            return safe

        return f"sp_{uuid.uuid5(uuid.NAMESPACE_DNS, raw)}"

    def _apply_order_payload(self, order: BrokerOrder, data: dict) -> BrokerOrder:
        order.broker_order_id = data.get("id", order.broker_order_id)
        order.client_order_id = data.get("client_order_id", order.client_order_id)
        order.status = data.get("status", order.status)
        try:
            order.filled_price = float(data.get("filled_avg_price") or data.get("filled_price") or order.filled_price or 0)
        except (TypeError, ValueError):
            order.filled_price = 0.0
        try:
            order.filled_quantity = float(data.get("filled_qty") or order.filled_quantity or 0)
        except (TypeError, ValueError):
            order.filled_quantity = 0.0
        return order

    async def _poll_order_until_terminal(self, order: BrokerOrder, *, attempts: int = 6) -> BrokerOrder:
        if not order.broker_order_id:
            return order

        session = await self._get_session()
        for attempt in range(attempts):
            async with session.get(f"{self._base_url()}/v2/orders/{order.broker_order_id}", headers=self._headers()) as resp:
                if resp.status == 200:
                    self._apply_order_payload(order, await resp.json())
                    if str(order.status or "").lower() in _ORDER_TERMINAL_STATUSES:
                        break
            if attempt < attempts - 1:
                await asyncio.sleep(0.5)
        return order

    async def check_connection(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(f"{self._base_url()}/v2/account", headers=self._headers()) as resp:
                self.connected = resp.status == 200
                return self.connected
        except Exception as e:
            logger.error(f"Alpaca connection error: {e}")
            return False

    async def get_account(self) -> BrokerAccountInfo:
        session = await self._get_session()
        async with session.get(f"{self._base_url()}/v2/account", headers=self._headers()) as resp:
            data = await resp.json()
            return BrokerAccountInfo(
                balance=float(data.get("cash", 0)),
                buying_power=float(data.get("buying_power", 0)),
                equity=float(data.get("equity", 0)),
            )

    async def get_positions(self) -> list[BrokerPosition]:
        session = await self._get_session()
        async with session.get(f"{self._base_url()}/v2/positions", headers=self._headers()) as resp:
            data = await resp.json()
            return [
                BrokerPosition(
                    symbol=p["symbol"],
                    quantity=float(p["qty"]),
                    avg_entry=float(p["avg_entry_price"]),
                    current_price=float(p["current_price"]),
                    market_value=float(p["market_value"]),
                    unrealized_pnl=float(p["unrealized_pl"]),
                )
                for p in data
            ]

    async def get_open_orders(self) -> list[BrokerOpenOrder]:
        session = await self._get_session()
        async with session.get(f"{self._base_url()}/v2/orders?status=open&limit=100", headers=self._headers()) as resp:
            data = await resp.json()
            orders = data if isinstance(data, list) else []
            parsed = []
            for item in orders:
                try:
                    side = OrderSide(str(item.get("side", "")).upper())
                    order_type = OrderType(str(item.get("type", "")).upper())
                except ValueError:
                    continue
                try:
                    quantity = float(item.get("qty") or 0)
                except (TypeError, ValueError):
                    quantity = 0.0
                parsed.append(
                    BrokerOpenOrder(
                        symbol=str(item.get("symbol", "")).upper(),
                        side=side,
                        order_type=order_type,
                        quantity=quantity,
                        status=str(item.get("status") or ""),
                        broker_order_id=str(item.get("id") or ""),
                        client_order_id=str(item.get("client_order_id") or ""),
                    )
                )
            return parsed

    async def place_order(self, order: BrokerOrder) -> BrokerOrder:
        session = await self._get_session()
        payload = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": order.side.value.lower(),
            "type": order.order_type.value.lower(),
            "time_in_force": "day",
        }
        client_order_id = self._client_order_id_for(order)
        if client_order_id:
            payload["client_order_id"] = client_order_id
            order.client_order_id = client_order_id
        if order.limit_price and order.order_type in ("LIMIT", "STOP_LIMIT"):
            payload["limit_price"] = str(order.limit_price)
        if order.stop_price and order.order_type in ("STOP", "STOP_LIMIT"):
            payload["stop_price"] = str(order.stop_price)

        async with session.post(f"{self._base_url()}/v2/orders", headers=self._headers(), json=payload) as resp:
            data = await resp.json()
            if resp.status in (200, 201):
                self._apply_order_payload(order, data)
                order_type = getattr(order.order_type, "value", order.order_type)
                if str(order_type).upper() == "MARKET" and str(order.status or "").lower() not in _ORDER_TERMINAL_STATUSES:
                    await self._poll_order_until_terminal(order)
            else:
                order.status = "rejected"
                order.error = data.get("message", f"HTTP {resp.status}")
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        session = await self._get_session()
        async with session.delete(f"{self._base_url()}/v2/orders/{broker_order_id}", headers=self._headers()) as resp:
            return resp.status in (200, 204)

    async def get_quote(self, symbol: str) -> float:
        session = await self._get_session()
        async with session.get(f"{self._base_url()}/v2/stocks/{symbol}/quotes/latest", headers=self._headers()) as resp:
            data = await resp.json()
            return float(data.get("quote", {}).get("ap", 0) or data.get("quote", {}).get("bp", 0))
