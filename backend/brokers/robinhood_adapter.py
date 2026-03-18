"""Robinhood adapter — uses robin_stocks library for browser-like session auth."""
import logging
from .base import BrokerAdapter, BrokerOrder, BrokerPosition, BrokerAccountInfo

logger = logging.getLogger("SentinelPulse")


class RobinhoodAdapter(BrokerAdapter):
    broker_id = "robinhood"

    def _login(self):
        import robin_stocks.robinhood as r
        username = self.config.get("username", "")
        password = self.config.get("password", "")
        mfa = self.config.get("mfa_code", "")
        if mfa:
            r.login(username, password, mfa_code=mfa)
        else:
            r.login(username, password)
        return r

    async def check_connection(self) -> bool:
        try:
            r = self._login()
            profile = r.load_account_profile()
            self.connected = bool(profile and profile.get("url"))
            return self.connected
        except ImportError:
            logger.error("robin_stocks not installed")
            return False
        except Exception as e:
            logger.error(f"Robinhood connection error: {e}")
            return False

    async def get_account(self) -> BrokerAccountInfo:
        import robin_stocks.robinhood as r
        profile = r.load_account_profile()
        portfolio = r.load_portfolio_profile()
        return BrokerAccountInfo(
            balance=float(profile.get("cash", 0)),
            buying_power=float(profile.get("buying_power", 0)),
            equity=float(portfolio.get("equity", 0)),
        )

    async def get_positions(self) -> list[BrokerPosition]:
        import robin_stocks.robinhood as r
        holdings = r.build_holdings()
        return [
            BrokerPosition(
                symbol=sym,
                quantity=float(h.get("quantity", 0)),
                avg_entry=float(h.get("average_buy_price", 0)),
                current_price=float(h.get("price", 0)),
                market_value=float(h.get("equity", 0)),
                unrealized_pnl=float(h.get("equity_change", 0)),
            )
            for sym, h in holdings.items()
        ]

    async def place_order(self, order: BrokerOrder) -> BrokerOrder:
        try:
            import robin_stocks.robinhood as r
            if order.order_type.value == "MARKET":
                if order.side.value == "BUY":
                    result = r.order_buy_market(order.symbol, order.quantity)
                else:
                    result = r.order_sell_market(order.symbol, order.quantity)
            else:
                price = order.limit_price or order.stop_price or 0
                if order.side.value == "BUY":
                    result = r.order_buy_limit(order.symbol, order.quantity, price)
                else:
                    result = r.order_sell_limit(order.symbol, order.quantity, price)

            if result and "id" in result:
                order.broker_order_id = result["id"]
                order.status = "submitted"
            else:
                order.status = "rejected"
                order.error = str(result)
        except Exception as e:
            order.status = "rejected"
            order.error = str(e)
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            import robin_stocks.robinhood as r
            r.cancel_stock_order(broker_order_id)
            return True
        except Exception:
            return False

    async def get_quote(self, symbol: str) -> float:
        import robin_stocks.robinhood as r
        quotes = r.get_latest_price(symbol)
        return float(quotes[0]) if quotes else 0.0
