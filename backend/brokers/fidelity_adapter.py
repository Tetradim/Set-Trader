"""Fidelity adapter — no official API, placeholder with web scraping approach."""
import logging
from .base import BrokerAdapter, BrokerOrder, BrokerPosition, BrokerAccountInfo

logger = logging.getLogger("SentinelPulse")


class FidelityAdapter(BrokerAdapter):
    broker_id = "fidelity"

    async def check_connection(self) -> bool:
        """Fidelity has no public trading API. Third-party access is experimental."""
        logger.warning("Fidelity does not offer a public trading API. Connection requires third-party tools.")
        # In a real implementation, this would attempt browser-based auth
        # or use a library like fidelityx
        self.connected = False
        return False

    async def get_account(self) -> BrokerAccountInfo:
        return BrokerAccountInfo(balance=0, buying_power=0, equity=0)

    async def get_positions(self) -> list[BrokerPosition]:
        return []

    async def place_order(self, order: BrokerOrder) -> BrokerOrder:
        order.status = "rejected"
        order.error = "Fidelity API not available — no public trading API exists."
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        return False

    async def get_quote(self, symbol: str) -> float:
        return 0.0
