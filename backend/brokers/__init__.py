"""
Sentinel Pulse — Multi-Broker Adapter Layer

Architecture:
  BrokerAdapter (ABC)  <-- common interface
     ├── RobinhoodAdapter
     ├── SchwabAdapter
     ├── WebullAdapter
     ├── IBKRAdapter
     ├── WealthsimpleAdapter
     └── FidelityAdapter

Each adapter implements the same interface so the trading engine
can place orders, query positions, and check balances through a
uniform API regardless of which broker is connected.
"""
from .base import BrokerAdapter, BrokerOrder, BrokerPosition, BrokerAccountInfo, BrokerRiskWarning
from .registry import BROKER_REGISTRY, get_broker_adapter, get_broker_info

__all__ = [
    "BrokerAdapter",
    "BrokerOrder",
    "BrokerPosition",
    "BrokerAccountInfo",
    "BrokerRiskWarning",
    "BROKER_REGISTRY",
    "get_broker_adapter",
    "get_broker_info",
]
