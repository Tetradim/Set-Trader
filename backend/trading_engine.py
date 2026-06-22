"""Core trading engine: evaluates tickers, places orders, manages positions."""
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo
from collections import deque

import deps
from schemas import TradeRecord
from resilience import CircuitOpenError
from risk_controls import RiskControls, RiskCheckResult, OrderRestriction, KillSwitchLevel
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
        risk_result = self.check_global_risk()
        if not risk_result.is_allowed:
            return False, f"RISK REJECTED: {risk_result.message}"
        
        # Check symbol-specific risk
        symbol_risk = self.check_symbol_risk(symbol)
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
        notional = quantity * price
        
        if side == "BUY":
            self.risk_controls.update_exposure(
                "portfolio", "global",
                notional_delta=notional,
                position_delta=quantity
            )
            self.risk_controls.update_exposure(
                "symbol", symbol,
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
                position_delta=-quantity,
                pnl_delta=pnl
            )
        
        # Update order count
        self.risk_controls.update_exposure("portfolio", "global", order_count=1)
    

    def _get_today_str(self) -> str:
        """Get today's date string in US Eastern Time for tracking daily operations."""
        return datetime.now(_ET).strftime("%Y-%m-%d")
