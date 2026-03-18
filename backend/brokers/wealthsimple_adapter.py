"""Wealthsimple Trade adapter — Canadian broker, unofficial API."""
import logging
from .base import BrokerAdapter, BrokerOrder, BrokerPosition, BrokerAccountInfo

logger = logging.getLogger("SentinelPulse")
WS_BASE = "https://trade-service.wealthsimple.com"


class WealthsimpleAdapter(BrokerAdapter):
    broker_id = "wealthsimple"

    def __init__(self, config: dict):
        super().__init__(config)
        self._access_token = ""
        self._account_id = ""

    def _headers(self):
        return {"Authorization": self._access_token,
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}

    async def check_connection(self) -> bool:
        try:
            session = await self._get_session()
            auth_data = {"email": self.config.get("ws_email", ""), "password": self.config.get("ws_password", "")}
            otp = self.config.get("ws_otp_code", "")
            if otp:
                auth_data["otp"] = otp
            async with session.post(f"{WS_BASE}/auth/login", json=auth_data,
                                    headers={"Content-Type": "application/json",
                                             "User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status == 200:
                    self._access_token = resp.headers.get("X-Access-Token", "")
                    if self._access_token:
                        self.connected = True
                        # Fetch account ID
                        async with session.get(f"{WS_BASE}/account/list", headers=self._headers()) as acct_resp:
                            data = await acct_resp.json()
                            results = data.get("results", [])
                            if results:
                                self._account_id = results[0].get("id", "")
                        return True
        except Exception as e:
            logger.error(f"Wealthsimple connection error: {e}")
        return False

    async def get_account(self) -> BrokerAccountInfo:
        session = await self._get_session()
        async with session.get(f"{WS_BASE}/account/list", headers=self._headers()) as resp:
            data = await resp.json()
            results = data.get("results", [])
            if results:
                a = results[0]
                bal = a.get("current_balance", {})
                return BrokerAccountInfo(
                    balance=float(bal.get("amount", 0)),
                    buying_power=float(a.get("buying_power", {}).get("amount", 0)),
                    equity=float(bal.get("amount", 0)),
                    currency=bal.get("currency", "CAD"),
                )
        return BrokerAccountInfo(balance=0, buying_power=0, equity=0, currency="CAD")

    async def get_positions(self) -> list[BrokerPosition]:
        session = await self._get_session()
        async with session.get(f"{WS_BASE}/account/positions", headers=self._headers(),
                               params={"account_id": self._account_id}) as resp:
            data = await resp.json()
            return [
                BrokerPosition(
                    symbol=p.get("stock", {}).get("symbol", ""),
                    quantity=float(p.get("quantity", 0)),
                    avg_entry=float(p.get("book_value", {}).get("amount", 0)) / max(float(p.get("quantity", 1)), 1),
                    current_price=float(p.get("quote", {}).get("amount", 0)),
                    market_value=float(p.get("market_value", {}).get("amount", 0)),
                    unrealized_pnl=float(p.get("return", {}).get("amount", 0)),
                )
                for p in data.get("results", [])
            ]

    async def place_order(self, order: BrokerOrder) -> BrokerOrder:
        session = await self._get_session()
        # Wealthsimple uses security IDs, not ticker symbols directly
        # First look up the security
        async with session.get(f"{WS_BASE}/securities", headers=self._headers(),
                               params={"query": order.symbol}) as resp:
            data = await resp.json()
            results = data.get("results", [])
            sec_id = results[0].get("id", "") if results else ""
        if not sec_id:
            order.status = "rejected"
            order.error = f"Security not found for {order.symbol}"
            return order

        payload = {
            "account_id": self._account_id,
            "security_id": sec_id,
            "order_type": order.order_type.value.lower(),
            "order_sub_type": "market" if order.order_type.value == "MARKET" else "limit",
            "time_in_force": "day",
            "side": order.side.value.lower(),
            "quantity": int(order.quantity),
        }
        if order.limit_price:
            payload["limit_price"] = {"amount": order.limit_price, "currency": "CAD"}

        async with session.post(f"{WS_BASE}/orders", headers=self._headers(), json=payload) as resp:
            data = await resp.json()
            if resp.status in (200, 201):
                order.broker_order_id = data.get("order_id", "")
                order.status = "submitted"
            else:
                order.status = "rejected"
                order.error = str(data)
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        session = await self._get_session()
        async with session.delete(f"{WS_BASE}/orders/{broker_order_id}", headers=self._headers()) as resp:
            return resp.status == 200

    async def get_quote(self, symbol: str) -> float:
        session = await self._get_session()
        async with session.get(f"{WS_BASE}/securities", headers=self._headers(),
                               params={"query": symbol}) as resp:
            data = await resp.json()
            results = data.get("results", [])
            if results:
                return float(results[0].get("quote", {}).get("amount", 0))
        return 0.0
