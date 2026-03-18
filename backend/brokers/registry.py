"""Broker registry — central catalog of all supported brokers and their metadata."""
from .base import BrokerAdapter, BrokerInfo, BrokerRiskWarning, BrokerRiskLevel

# --------------------------------------------------------------------------- #
# Registry of all brokers Sentinel Pulse will support.
# `supported=True` means the adapter is implemented and functional.
# `supported=False` means it is planned but not yet wired up.
# --------------------------------------------------------------------------- #

BROKER_REGISTRY: dict[str, BrokerInfo] = {
    "robinhood": BrokerInfo(
        id="robinhood",
        name="Robinhood",
        description="Commission-free trading platform. Popular for retail traders.",
        supported=False,
        auth_fields=["username", "password", "mfa_code"],
        risk_warning=BrokerRiskWarning(
            level=BrokerRiskLevel.HIGH,
            message=(
                "Robinhood actively monitors for automated trading patterns and may "
                "restrict or permanently ban accounts that appear to use bots. "
                "Use at your own risk."
            ),
        ),
        docs_url="https://robinhood.com/",
    ),
    "schwab": BrokerInfo(
        id="schwab",
        name="Charles Schwab",
        description="Full-service broker with robust API access via Schwab Developer Portal.",
        supported=False,
        auth_fields=["app_key", "app_secret", "refresh_token"],
        risk_warning=BrokerRiskWarning(
            level=BrokerRiskLevel.MEDIUM,
            message=(
                "Schwab permits algorithmic trading through their official API but requires "
                "app registration. High-frequency patterns may trigger review."
            ),
        ),
        docs_url="https://developer.schwab.com/",
    ),
    "webull": BrokerInfo(
        id="webull",
        name="Webull",
        description="Commission-free trading with advanced charting tools.",
        supported=False,
        auth_fields=["email", "password", "trading_pin"],
        risk_warning=BrokerRiskWarning(
            level=BrokerRiskLevel.HIGH,
            message=(
                "Webull does not offer an official public API. Third-party libraries "
                "rely on reverse-engineered endpoints and may break without notice. "
                "Account bans are possible."
            ),
        ),
        docs_url="https://www.webull.com/",
    ),
    "ibkr": BrokerInfo(
        id="ibkr",
        name="Interactive Brokers (IBKR)",
        description="Professional-grade broker with full API support for algorithmic trading.",
        supported=False,
        auth_fields=["host", "port", "client_id"],
        risk_warning=BrokerRiskWarning(
            level=BrokerRiskLevel.LOW,
            message=(
                "IBKR is designed for algorithmic trading and provides robust TWS/Gateway "
                "APIs. Low risk of account restrictions for automated activity."
            ),
        ),
        docs_url="https://interactivebrokers.github.io/",
    ),
    "wealthsimple": BrokerInfo(
        id="wealthsimple",
        name="Wealthsimple Trade",
        description="Canadian commission-free trading platform.",
        supported=False,
        auth_fields=["email", "password", "otp"],
        risk_warning=BrokerRiskWarning(
            level=BrokerRiskLevel.HIGH,
            message=(
                "Wealthsimple does not offer an official trading API. Third-party access "
                "relies on undocumented endpoints. Account restrictions are highly likely "
                "for automated trading."
            ),
        ),
        docs_url="https://www.wealthsimple.com/",
    ),
    "fidelity": BrokerInfo(
        id="fidelity",
        name="Fidelity",
        description="Major US brokerage with no-commission stock and ETF trading.",
        supported=False,
        auth_fields=["username", "password"],
        risk_warning=BrokerRiskWarning(
            level=BrokerRiskLevel.MEDIUM,
            message=(
                "Fidelity does not currently offer a public trading API. Automated "
                "access requires third-party tools and may violate terms of service."
            ),
        ),
        docs_url="https://www.fidelity.com/",
    ),
}


def get_broker_info(broker_id: str) -> BrokerInfo | None:
    """Return static info for a broker by its ID."""
    return BROKER_REGISTRY.get(broker_id)


def get_broker_adapter(broker_id: str, credentials: dict) -> BrokerAdapter | None:
    """
    Factory: instantiate and return the correct adapter for a given broker.
    Returns None if the broker is not yet implemented.
    """
    # Placeholder — as adapters are built, import and return them here.
    # Example:
    # if broker_id == "ibkr":
    #     from .ibkr_adapter import IBKRAdapter
    #     adapter = IBKRAdapter()
    #     return adapter
    return None
