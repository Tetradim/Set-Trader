"""Tradier broker adapter — developer-friendly REST API."""
import asyncio
import logging
import math
from .base import BrokerAdapter, BrokerOrder, BrokerPosition, BrokerAccountInfo

logger = logging.getLogger("SentinelPulse")
API_BASE = "https://api.tradier.com/v1"
_TERMINAL = {"filled", "canceled", "cancelled", "expired", "rejected"}


class TradierAdapter(BrokerAdapter):
    broker_id = "tradier"

    def _headers(self):
        return {"Authorization": f"Bearer {self.config.get('access_token', '')}", "Accept": "application/json"}

    def _acct(self):
        return self.config.get("account_id", "")

    def _apply_order(self, order: BrokerOrder, payload: dict) -> BrokerOrder:
        data = payload.get("order", payload) if isinstance(payload, dict) else {}
        order.broker_order_id = str(data.get("id") or order.broker_order_id or "")
        raw_status = str(data.get("status") or order.status or "pending").lower()
        order.status = "pending" if raw_status in {"submitted", "open", "pending"} else raw_status
        for key in ("avg_fill_price", "average_fill_price", "last_fill_price"):
            try:
                value = float(data.get(key) or 0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                order.filled_price = value
                break
        for key in ("exec_quantity", "filled_quantity", "last_fill_quantity"):
            try:
                value = float(data.get(key) or 0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                order.filled_quantity = value
                break
        return order

    async def _poll_order(self, order: BrokerOrder, *, attempts: int, interval_seconds: float = 0.5) -> BrokerOrder:
        if not order.broker_order_id:
            return order
        session = await self._get_session()
        for attempt in range(max(1, attempts)):
            async with session.get(
                f"{API_BASE}/accounts/{self._acct()}/orders/{order.broker_order_id}",
                headers=self._headers(),
            ) as resp:
                if resp.status == 200:
                    self._apply_order(order, await resp.json())
                    if str(order.status or "").lower() in _TERMINAL:
                        break
            if attempt < attempts - 1:
                await asyncio.sleep(max(0.05, interval_seconds))
        return order

    async def _cancel_after_timeout(self, order: BrokerOrder) -> BrokerOrder:
        timeout = int(order.timeout_seconds or 0)
        if timeout <= 0 or not order.broker_order_id:
            return order
        await self._poll_order(order, attempts=max(1, int(math.ceil(timeout / 0.5))))
        if str(order.status or "").lower() in _TERMINAL:
            return order
        cancelled = await self.cancel_order(order.broker_order_id)
        await self._poll_order(order, attempts=3, interval_seconds=0.25)
        if cancelled and str(order.status or "").lower() not in _TERMINAL:
            order.status = "canceled"
        return order

    async def check_connection(self) -> bool:
        try:
            session = await self._get_session()
            async with session.get(f"{API_BASE}/user/profile", headers=self._headers()) as resp:
                self.connected = resp.status == 200
                return self.connected
        except Exception as e:
            logger.error(f"Tradier connection error: {e}")
        return False

    async def get_account(self) -> BrokerAccountInfo:
        session = await self._get_session()
        async with session.get(f"{API_BASE}/accounts/{self._acct()}/balances", headers=self._headers()) as resp:
            data = await resp.json()
            bal = data.get("balances", {})
            return BrokerAccountInfo(
                balance=float(bal.get("total_cash", 0)),
                buying_power=float(bal.get("stock_buying_power", bal.get("buying_power", 0))),
                equity=float(bal.get("total_equity", 0)),
            )

    async def get_positions(self) -> list[BrokerPosition]:
        session = await self._get_session()
        async with session.get(f"{API_BASE}/accounts/{self._acct()}/positions", headers=self._headers()) as resp:
            data = await resp.json()
            positions = data.get("positions", {}).get("position", [])
            if isinstance(positions, dict):
                positions = [positions]
            return [
                BrokerPosition(
                    symbol=p.get("symbol", ""),
                    quantity=float(p.get("quantity", 0)),
                    avg_entry=float(p.get("cost_basis", 0)) / max(float(p.get("quantity", 1)), 1),
                    current_price=0,
                    market_value=float(p.get("cost_basis", 0)),
                    unrealized_pnl=0,
                )
                for p in positions
            ]

    async def place_order(self, order: BrokerOrder) -> BrokerOrder:
        session = await self._get_session()
        payload = {
            "class": "equity",
            "symbol": order.symbol,
            "side": order.side.value.lower(),
            "quantity": str(int(order.quantity)),
            "type": order.order_type.value.lower(),
            "duration": str(order.time_in_force or "day").lower(),
        }
        if order.limit_price:
            payload["price"] = str(order.limit_price)
        if order.stop_price:
            payload["stop"] = str(order.stop_price)
        async with session.post(
            f"{API_BASE}/accounts/{self._acct()}/orders",
            headers=self._headers(),
            data=payload,
        ) as resp:
            data = await resp.json()
            if resp.status in (200, 201):
                self._apply_order(order, data)
                if not order.status or order.status == "submitted":
                    order.status = "pending"
                if order.timeout_seconds:
                    await self._cancel_after_timeout(order)
            else:
                order.status = "rejected"
                order.error = str(data.get("error", data))
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        session = await self._get_session()
        async with session.delete(
            f"{API_BASE}/accounts/{self._acct()}/orders/{broker_order_id}",
            headers=self._headers(),
        ) as resp:
            return resp.status == 200

    async def get_quote(self, symbol: str) -> float:
        session = await self._get_session()
        async with session.get(
            f"{API_BASE}/markets/quotes",
            headers=self._headers(),
            params={"symbols": symbol},
        ) as resp:
            data = await resp.json()
            q = data.get("quotes", {}).get("quote", {})
            return float(q.get("last", 0))
