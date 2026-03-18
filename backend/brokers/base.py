"""Base broker adapter interface — all broker implementations inherit from this."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


@dataclass
class BrokerOrder:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    broker_order_id: str = ""
    status: str = "pending"
    filled_price: float = 0.0
    filled_quantity: float = 0.0
    error: str = ""


@dataclass
class BrokerPosition:
    symbol: str
    quantity: float
    avg_entry: float
    current_price: float
    market_value: float
    unrealized_pnl: float


@dataclass
class BrokerAccountInfo:
    balance: float
    buying_power: float
    equity: float
    currency: str = "USD"


class BrokerRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class BrokerRiskWarning:
    level: BrokerRiskLevel
    message: str


@dataclass
class BrokerInfo:
    """Static metadata about a supported broker."""
    id: str
    name: str
    description: str
    supported: bool = False          # True if adapter is fully implemented
    auth_fields: list = field(default_factory=list)  # e.g. ["api_key", "api_secret"]
    risk_warning: Optional[BrokerRiskWarning] = None
    docs_url: str = ""


class BrokerAdapter(ABC):
    """Abstract base class for all broker adapters."""

    broker_id: str = ""

    @abstractmethod
    async def connect(self, credentials: dict) -> bool:
        """Authenticate with the broker. Returns True on success."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up broker connection."""

    @abstractmethod
    async def get_account(self) -> BrokerAccountInfo:
        """Retrieve account balance and buying power."""

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]:
        """Retrieve all open positions."""

    @abstractmethod
    async def place_order(self, order: BrokerOrder) -> BrokerOrder:
        """Submit an order. Returns the order with updated status/ID."""

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel a pending order. Returns True on success."""

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> BrokerOrder:
        """Check the status of an existing order."""

    @abstractmethod
    async def get_quote(self, symbol: str) -> float:
        """Get the latest quote price for a symbol."""
