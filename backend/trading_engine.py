"""Core trading engine: evaluates tickers, places orders, manages positions."""
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo
from collections import deque

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError
from risk_controls import ExposureLimit, RiskControls, RiskCheckResult, OrderRestriction, KillSwitchLevel
from trading.idempotency import OrderIdempotencyMixin
from trading.engine_state import EngineStateMixin
from trading.broker_execution import BrokerExecutionMixin
from trading.order_lifecycle import OrderLifecycleMixin
from trading.ticker_evaluation import TickerEvaluationMixin
from trading.strategy_signals import StrategySignalMixin
from trading.brackets import BracketManagementMixin
from trading.trade_accounting import TradeAccountingMixin

_ET = ZoneInfo("America/New_York")   # US Eastern, DST-aware.


class TradingEngine(
    OrderIdempotencyMixin,
    EngineStateMixin,
    BrokerExecutionMixin,
    OrderLifecycleMixin,
    TickerEvaluationMixin,
    StrategySignalMixin,
    BracketManagementMixin,
    TradeAccountingMixin,
):
    TRADE_COOLDOWN_SECS = 30
    REENTRY_COOLDOWN_SECS = 300
    # Idempotency TTL - how long to remember order IDs to prevent duplicates
    IDEMPOTENCY_TTL_SECONDS = 300  # 5 minutes

    def __init__(self):
        self.running = False
        self.paused = False
        self.simulate_24_7 = False
        self.market_hours_only = True
        # Auto mode switching
        self.live_during_market_hours = False
        self.paper_after_hours = False
        self._last_mode_check: datetime = None
        self._last_market_state: bool = None  # Track market open/close transitions
        
        # Core state
        self._prices: Dict[str, float] = {}
        self._positions: Dict[str, dict] = {}
        self._trailing_highs: Dict[str, float] = {}
        self._last_trade_ts: Dict[str, datetime] = {}
        self._last_exit_ts: Dict[str, datetime] = {}
        self._recent_prices: Dict[str, list] = {}
        self._last_rebracket_ts: Dict[str, datetime] = {}
        self._pending_sells: Dict[str, dict] = {}  # symbol -> {limit_price, qty, entry}
        
        # Opening Bell Mode tracking
        self._opening_bell_highs: Dict[str, float] = {}  # symbol -> opening session high
        self._opening_bell_rebracket_done: Dict[str, str] = {}  # symbol -> date string when rebracket was done
        
        # Risk controls integration
        self.risk_controls = RiskControls()
        self._initialize_risk_defaults()
        
        # Idempotency tracking - in-memory (lost on restart)
        # For production, persist to MongoDB
        self._submitted_order_ids: deque = deque(maxlen=1000)  # symbol -> set of order IDs
        self._order_id_timestamps: Dict[str, datetime] = {}  # order_id -> timestamp
        
        # Safety flags
        self._dry_run_mode: bool = False  # If True, no real orders placed
        
        # Error tracking for backpressure
        self._ticker_errors: Dict[str, int] = {}  # symbol -> error count
        self._ticker_last_error: Dict[str, datetime] = {}  # symbol -> last error timestamp
        self._max_consecutive_errors = 3  # Pause ticker after this many consecutive errors

    def _initialize_risk_defaults(self):
        """Initialize default risk controls."""
        from risk_controls import ExposureLimit
        
        # Global portfolio-level limits
        self.risk_controls.add_exposure_limit(ExposureLimit(
            limit_id="global_portfolio",
            level="portfolio",
            level_id="global",
            max_notional=100000,  # Max $100k portfolio notional
            max_daily_loss=5000,  # Max $5k daily loss
            max_position_size=20000,  # Max $20k per position
            max_orders_per_minute=20,  # Max 20 orders/minute
            soft_limit=80000,  # Warning at 80% of notional
        ))
        
        # Default symbol-level limits (can be overridden per ticker)
        self.risk_controls.add_exposure_limit(ExposureLimit(
            limit_id="default_symbol",
            level="symbol",
            level_id="default",
            max_position_size=10000,  # Max $10k per symbol
        ))
        
        deps.logger.info("Initialized default risk controls")
    
    # === Idempotency Methods ===
    
    
    
    
    
    
    # === Risk Check Methods ===
    
    def check_global_risk(self) -> RiskCheckResult:
        """Check global portfolio risk limits."""
        return self.risk_controls.check_exposure_limit("portfolio", "global")
    
    def check_symbol_risk(self, symbol: str) -> RiskCheckResult:
        """Check symbol-specific risk limits."""
        return self.risk_controls.check_exposure_limit("symbol", symbol)

    def ensure_symbol_exposure_limit(self, symbol: str) -> ExposureLimit:
        """Ensure each traded symbol has its own exposure bucket."""
        symbol = str(symbol or "").upper()
        existing = self.risk_controls.get_exposure_limit("symbol", symbol)
        if existing:
            return existing

        default = self.risk_controls.get_exposure_limit("symbol", "default")
        limit = ExposureLimit(
            limit_id=f"symbol_{symbol}",
            level="symbol",
            level_id=symbol,
            max_notional=default.max_notional if default else 0.0,
            max_daily_loss=default.max_daily_loss if default else 0.0,
            max_position_size=default.max_position_size if default else 0.0,
            max_orders_per_minute=default.max_orders_per_minute if default else 0,
            soft_limit=default.soft_limit if default else 0.0,
            is_enabled=default.is_enabled if default else True,
        )
        self.risk_controls.add_exposure_limit(limit)
        return limit

    def check_projected_global_risk(self, side: str, quantity: float, price: float) -> RiskCheckResult:
        """Check portfolio risk using the proposed order's projected exposure."""
        limit = self.risk_controls.get_exposure_limit("portfolio", "global")
        if not limit or not limit.is_enabled:
            return RiskCheckResult(is_allowed=True)

        side = str(side or "").upper()
        try:
            order_notional = max(0.0, float(quantity or 0) * float(price or 0))
        except (TypeError, ValueError):
            order_notional = 0.0

        notional_delta = order_notional if side == "BUY" else -order_notional
        projected_notional = max(0.0, float(limit.current_notional or 0) + notional_delta)
        if side == "BUY" and limit.max_notional > 0 and projected_notional > limit.max_notional:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=(
                    f"Projected notional limit exceeded: ${projected_notional} "
                    f"> ${limit.max_notional}"
                ),
                rejected_fields={"notional": projected_notional},
            )

        position_delta = float(quantity or 0) if side == "BUY" else -float(quantity or 0)
        projected_position = float(limit.current_position or 0) + position_delta
        if side == "BUY" and limit.max_position_size > 0 and abs(projected_position) > limit.max_position_size:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=(
                    f"Projected position size exceeded: {projected_position} "
                    f"> {limit.max_position_size}"
                ),
                rejected_fields={"position": projected_position},
            )

        if limit.max_daily_loss > 0 and limit.daily_pnl < -limit.max_daily_loss:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=f"Daily loss limit exceeded: ${limit.daily_pnl} < -${limit.max_daily_loss}",
                rejected_fields={"daily_pnl": limit.daily_pnl},
            )

        if limit.max_orders_per_minute > 0 and limit.orders_count >= limit.max_orders_per_minute:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.CANCEL_ALL,
                message=f"Order rate limit exceeded: {limit.orders_count} >= {limit.max_orders_per_minute}/min",
                rejected_fields={"orders_count": limit.orders_count},
            )

        return RiskCheckResult(is_allowed=True)

    def check_projected_symbol_risk(self, symbol: str, side: str, quantity: float, price: float) -> RiskCheckResult:
        """Check symbol risk using the proposed order's projected exposure."""
        limit = self.ensure_symbol_exposure_limit(symbol)
        if not limit or not limit.is_enabled:
            return RiskCheckResult(is_allowed=True)

        side = str(side or "").upper()
        try:
            order_notional = max(0.0, float(quantity or 0) * float(price or 0))
        except (TypeError, ValueError):
            order_notional = 0.0

        notional_delta = order_notional if side == "BUY" else -order_notional
        projected_notional = max(0.0, float(limit.current_notional or 0) + notional_delta)
        if side == "BUY" and limit.max_notional > 0 and projected_notional > limit.max_notional:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=(
                    f"Projected symbol notional limit exceeded: ${projected_notional} "
                    f"> ${limit.max_notional}"
                ),
                rejected_fields={"symbol": symbol, "notional": projected_notional},
            )

        position_delta = float(quantity or 0) if side == "BUY" else -float(quantity or 0)
        projected_position = float(limit.current_position or 0) + position_delta
        if side == "BUY" and limit.max_position_size > 0 and abs(projected_position) > limit.max_position_size:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=(
                    f"Projected symbol position size exceeded: {projected_position} "
                    f"> {limit.max_position_size}"
                ),
                rejected_fields={"symbol": symbol, "position": projected_position},
            )

        if limit.max_daily_loss > 0 and limit.daily_pnl < -limit.max_daily_loss:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.HARD_BLOCK,
                message=f"Symbol daily loss limit exceeded: ${limit.daily_pnl} < -${limit.max_daily_loss}",
                rejected_fields={"symbol": symbol, "daily_pnl": limit.daily_pnl},
            )

        if limit.max_orders_per_minute > 0 and limit.orders_count >= limit.max_orders_per_minute:
            return RiskCheckResult(
                is_allowed=False,
                restriction=OrderRestriction.CANCEL_ALL,
                message=f"Symbol order rate limit exceeded: {limit.orders_count} >= {limit.max_orders_per_minute}/min",
                rejected_fields={"symbol": symbol, "orders_count": limit.orders_count},
            )

        return RiskCheckResult(is_allowed=True)
    
    def is_dry_run(self) -> bool:
        """Check if running in dry-run (no real orders) mode."""
        return self._dry_run_mode
    
    def set_dry_run(self, enabled: bool):
        """Enable or disable dry-run mode."""
        self._dry_run_mode = enabled
        deps.logger.warning(f"Dry-run mode {'ENABLED' if enabled else 'DISABLED'}")
    
    def is_live_trading(self) -> bool:
        """Check if actually trading live (not paper)."""
        return not self.is_paper_trading()
    
    def _log_trading_error(self, context: str, error: Exception, symbol: str = None):
        """Enhanced error logging for trading errors with Telegram alerts."""
        error_msg = f"{context}: {error}"
        if symbol:
            error_msg = f"[{symbol}] {error_msg}"
        
        deps.logger.error(error_msg, exc_info=True)
        
        # Send Telegram alert for critical errors
        if hasattr(deps, 'telegram_service') and deps.telegram_service.running:
            if "Circuit" in str(type(error).__name__) or "Error" in str(type(error).__name__):
                try:
                    import asyncio
                    asyncio.create_task(deps.telegram_service.send_alert(
                        f"Trading Error\n{context}\n{error_msg[:200]}"
                    ))
                except Exception:
                    pass  # Don't fail on logging errors
    
    async def pre_trade_check(self, symbol: str, side: str, quantity: float, 
                              price: float) -> tuple[bool, str]:
        """
        Pre-trade risk gateway check before placing any order.
        
        Returns:
            (is_allowed, reason) - if is_allowed is False, reason explains why
        """
        # Check dry-run mode first
        if self._dry_run_mode:
            return False, "DRY-RUN MODE: No real orders allowed"
        
        # Check global kill switch
        global_switch = self.risk_controls.get_kill_switch("global", "global")
        if global_switch and global_switch.is_active:
            return False, f"GLOBAL KILL SWITCH ACTIVE: {global_switch.reason}"
        
        # Check symbol kill switch
        symbol_switch = self.risk_controls.get_kill_switch("broker", symbol)
        if symbol_switch and symbol_switch.is_active:
            return False, f"SYMBOL {symbol} BLOCKED: {symbol_switch.reason}"
        
        # Check global portfolio risk
        risk_result = self.check_projected_global_risk(side, quantity, price)
        if not risk_result.is_allowed:
            return False, f"RISK REJECTED: {risk_result.message}"
        
        # Check symbol-specific risk
        symbol_risk = self.check_projected_symbol_risk(symbol, side, quantity, price)
        if not symbol_risk.is_allowed:
            return False, f"RISK REJECTED: {symbol_risk.message}"
        
        # Check circuit breakers
        if hasattr(deps, 'broker_resilience'):
            try:
                await deps.broker_resilience.before_call(symbol)
            except CircuitOpenError as e:
                return False, f"CIRCUIT OPEN for {symbol}: {e}"
        
        # All checks passed
        return True, ""
    
    def update_exposure_from_trade(self, symbol: str, side: str, quantity: float, 
                                   price: float, pnl: float = 0):
        """Update exposure tracking after a trade."""
        symbol = str(symbol or "").upper()
        notional = quantity * price
        self.ensure_symbol_exposure_limit(symbol)
        
        if side == "BUY":
            self.risk_controls.update_exposure(
                "portfolio", "global",
                notional_delta=notional,
                position_delta=quantity
            )
            self.risk_controls.update_exposure(
                "symbol", symbol,
                notional_delta=notional,
                position_delta=quantity
            )
        else:  # SELL
            self.risk_controls.update_exposure(
                "portfolio", "global",
                notional_delta=-notional,
                position_delta=-quantity,
                pnl_delta=pnl
            )
            self.risk_controls.update_exposure(
                "symbol", symbol,
                notional_delta=-notional,
                position_delta=-quantity,
                pnl_delta=pnl
            )
        
        # Update order count
        self.risk_controls.update_exposure("portfolio", "global", order_count=1)
    

    def _get_today_str(self) -> str:
        """Get today's date string in US Eastern Time for tracking daily operations."""
        return datetime.now(_ET).strftime("%Y-%m-%d")
