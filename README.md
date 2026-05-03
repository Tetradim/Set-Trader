# Sentinel Pulse

**Automated bracket-trading bot — multi-broker, multi-market, production-grade dark-mode dashboard.**

Trade the same ticker across multiple broker accounts simultaneously with independent buy-power allocation per broker. Features bracket orders, trailing stops, opening-bell risk rules, partial fills, auto-rebracket, per-broker circuit breakers and token-bucket rate limiting, international market support (7 exchanges), a **pluggable Python signal-strategy system** with hot-reload, structured audit logs, Telegram alerts, OpenTelemetry tracing, **Demo Mode (runs without MongoDB)**, and a Windows `.exe` installer.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Quick Start](#quick-start)
3. [Feature Overview](#feature-overview)
4. [Pluggable Strategy System](#pluggable-strategy-system)
5. [Edge Integration](#edge-integration)
6. [MACD-V Strategy](#macd-v-strategy)
7. [File Map — Backend](#file-map--backend)
8. [File Map — Frontend](#file-map--frontend)
9. [API Reference](#api-reference)
10. [Database Schema](#database-schema)
11. [Environment Variables](#environment-variables)
12. [Broker Catalogue](#broker-catalogue)
13. [International Markets](#international-markets)
14. [Resilience Architecture](#resilience-architecture)
15. [Roadmap: Planned Upgrades & Enhancements](#roadmap-planned-upgrades--enhancements)

---

## Architecture

```
                      ┌─────────────────────────────────┐
                      │   React + Vite  (Port 3000)     │
                      │   TypeScript · Tailwind · Zustand│
                      └──────────────┬──────────────────┘
                                     │  WebSocket + REST
                      ┌──────────────▼──────────────────┐
                      │   FastAPI Server  (Port 8002)   │
                      │   Motor · yfinance · Telegram   │
                      └───┬──────┬──────┬──────┬────────┘
                          │      │      │      │
                    ┌─────▼─┐ ┌──▼──┐ ┌▼────┐ ┌▼──────────┐
                    │MongoDB│ │yfi- │ │Tele-│ │9 Broker   │
                    │       │ │nance│ │gram │ │Adapters   │
                    └───────┘ └─────┘ └─────┘ └───────────┘
```

| Layer       | Stack                                                                           |
|-------------|---------------------------------------------------------------------------------|
| Frontend    | React 18, TypeScript, Vite, Tailwind CSS, Radix UI (Shadcn), Zustand, @dnd-kit, Recharts, Framer Motion |
| Backend     | FastAPI, Motor (async MongoDB), WebSocket, yfinance, python-telegram-bot, aiolimiter |
| Database    | MongoDB 7                                                                       |
| Monitoring  | OpenTelemetry (tracing + spans), Prometheus-compatible `/api/metrics`           |
| Brokers     | 9-broker adapter layer (aiohttp session pooling, per-broker resilience)         |
| Packaging   | PyInstaller (Windows `.exe`), Inno Setup installer, GitHub Actions CI/CD        |

---

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8002

# Frontend
cd frontend
yarn install
yarn dev
```

Dashboard: `http://localhost:3000` — WebSocket connects automatically on load.

### Demo Mode (No MongoDB Required)

Run without MongoDB for testing or demo purposes:

```bash
cd backend
export DEMO_MODE=true
export PORT=8002
uvicorn server:app --host 0.0.0.0 --port 8002
```

- **Default tickers** seeded automatically: SPY, QQQ, AAPL, NVDA
- **In-memory storage** — data not persisted
- **Paper trading** enforced
- **WebSocket** works fully

---

## Feature Overview

### Bracket Trading Engine
Each enabled ticker is evaluated on a 5-second loop:
- **Buy** when price ≤ buy target (% or $ from moving average)
- **Sell** when price ≥ sell target (% or $ from entry)
- **Stop-loss** when price ≤ stop target
- **Trailing stop** — tracks session high, sells if price drops by configured %/$
- All offsets configurable as `MARKET` or `LIMIT` orders

### Multi-Broker Execution
Assign any ticker to multiple brokers simultaneously. Each broker gets an independent buy-power slice. Orders fire in parallel via `asyncio.gather`. Broker failure on one doesn't affect others.

### Time-Based Risk Rules (Opening Bell)
During the first 30 minutes after each market's open:
- **Opening Bell Mode** — overrides normal sell rules with a forced trailing stop (tracks session high, sells on dip)
- **Halve Stop Loss** — tightens stop-loss distance to 50% to protect against opening volatility
- **Lock Trailing Stop** — freezes trailing stop evaluation for the opening window
- After 30 min, brackets auto-rebracket to the new price level (once per day)

These rules use each ticker's **specific market's open time**, not hard-coded US hours.

### Partial Fills (Scale In / Scale Out)
Split buys and sells into multiple legs at different price levels:
- `buy_legs` — each leg specifies `alloc_pct`, `offset`, `is_percent`
- `sell_legs` — same structure, triggers from entry price
- Stop-loss still protects the full remaining position

### Auto Rebracket
When price drifts beyond `rebracket_threshold` from the current bracket, automatically shifts buy/sell brackets to track the price. Configurable cooldown, lookback, buffer, and spread.

### Per-Broker Resilience (Rate Limiting + Circuit Breaker)
Every broker API call passes through `resilience.py`:
- **Token Bucket** — `AsyncLimiter(burst, burst/max_rps)` — proper burst + sustained RPS
- **Circuit Breaker** — CLOSED → OPEN → HALF_OPEN → CLOSED state machine
- Conservative defaults for Robinhood/Webull (2 RPS, 120s recovery)
- Telegram alert + WebSocket broadcast on circuit state change
- Manual reset via `POST /api/circuit/{broker_id}/reset`

### International Markets (7 Exchanges)
Add tickers for any of: US, HK (HKEX), AU (ASX), UK (LSE), CA (TSX), CN_SS (Shanghai SSE), CN_SZ (Shenzhen SZSE). Auto-detected from symbol suffix (`.HK`, `.AX`, `.L`, `.TO`, `.SS`, `.SZ`). Each market has:
- Correct trading hours and lunch-break windows
- Per-market opening bell mode using the exchange's own open time
- Live FX rates from yfinance, with persistent USD/Native currency toggle

### Auto Trading Mode Switching
- **Live @ Open** — auto-switches from paper → live when US market opens
- **Paper @ Close** — auto-switches from live → paper when US market closes
- Only triggers on state transitions, not continuously

### Capital Management
Set a total account balance. Dashboard header tracks: Allocated, Available, Total P&L, Cash Reserve. Over-allocation warning shown on the Add Stock dialog and ticker cards.

### Audit Logs
Every significant action is recorded: setting changes, ticker CRUD, broker API calls, rate limit hits, circuit state changes. Queryable via `GET /api/audit-logs` with filters for event type, symbol, broker, and success flag.

### Telegram Alerts
- Trade alerts (symbol, side, price, P&L, broker results)
- Auto-stop notifications
- Rebracket events
- Circuit breaker open/close events

### Pluggable Signal Strategies
Drop-in Python files that generate BUY / SELL / HOLD signals. Strategies run before bracket logic and can override it completely. Hot-reload from disk without restarting the server. Full details in the [Pluggable Strategy System](#pluggable-strategy-system) section.

---

## Pluggable Strategy System

Sentinel Pulse ships with a bracket-based engine (the default) **and** a pluggable signal-strategy layer that sits on top of it. You write a plain Python class, drop the file in one folder, click Reload — it immediately appears in the ConfigModal and can be activated per-ticker.

### How it fits into the engine

```
evaluate_ticker()
    │
    ├─ Market hours gate  (DST-aware per exchange)
    ├─ Cooldown check     (30s between trades)
    ├─ Price fetch        (broker feed or yfinance)
    │
    ├─ SIGNAL STRATEGY? ──── strategy registered AND ticker.strategy == name
    │       │
    │       ├─ generate_signals() → Signal(action="BUY")  → execute buy  → return
    │       ├─ generate_signals() → Signal(action="SELL") → execute sell → return
    │       ├─ generate_signals() → Signal(action="HOLD") → skip cycle  → return
    │       └─ generate_signals() → None                  → fall through ↓
    │
    └─ BRACKET LOGIC  (buy_offset / sell_offset / stop / trailing / partial fills)
```

A strategy that returns `None` cleanly defers to the normal bracket rules — useful when your signal has no conviction on a given bar.

---

### Language

**Python 3.9+** (same as the rest of the backend). No build step. No restart required after saving a file.

Third-party libraries your strategy may freely use:
- `pandas` — history DataFrames (already installed)
- `ta` — pure-Python technical indicators (already installed): RSI, MACD, Bollinger, ATR, and 30+ more
- `numpy` — numerical operations (already installed via pandas)
- Any other pure-Python library you `pip install` into the backend environment

The only constraint: `generate_signals()` must be an `async` function and must return either a `Signal` instance or `None`.

---

### File locations

```
backend/
└── strategies/
    ├── base.py              ← BaseStrategy, Signal, StrategyMetadata, StrategyConfigModel
    ├── loader.py            ← registry, load_all_strategies(), reload_strategies()
    ├── presets/
    │   └── __init__.py      ← conservative_1y, aggressive_monthly, swing_trader (bracket templates)
    └── custom/              ← ← ← YOUR FILES GO HERE
        ├── __init__.py
        ├── macd.py            (MACD crossover)
        ├── rsi.py             (RSI mean reversion)
        ├── bollinger.py       (Bollinger Bands)
        ├── sma_crossover.py   (SMA golden/death cross)
        ├── macdv.py           (MACD-V ATR-normalized)
        ├── multi_indicator.py (RSI+MACD example template)
        └── my_strategy.py     (your custom strategy)
```

**Rule:** put your `.py` file anywhere inside `backend/strategies/custom/`. The loader scans that directory automatically. Subdirectories are ignored — flat files only.

---

### Minimal working example

Create `backend/strategies/custom/my_strategy.py`:

```python
from strategies.base import BaseStrategy, Signal, StrategyMetadata

class MyStrategy(BaseStrategy):

    metadata = StrategyMetadata(
        name="My Strategy",          # display name in the UI
        version="1.0.0",
        description="Buy when price crosses above its 20-day SMA.",
        author="Your Name",
        tags=["trend", "sma"],
        risk_level="LOW",            # LOW | MEDIUM | HIGH
    )

    async def generate_signals(
        self,
        ticker_doc,       # full MongoDB ticker document
        current_price,    # latest price in native market currency
        market_data,      # {"history": pd.DataFrame|None, "fx_rate": float, "current_price": float}
        market_status,    # from markets.MarketConfig.to_dict()
        broker_allocations,  # {broker_id: float}
        params,           # merged default_params + per-ticker strategy_config overrides
    ):
        df = market_data.get("history")
        if df is None or len(df) < 20:
            return None   # not enough data — fall through to bracket logic

        sma20 = df["close"].rolling(20).mean().iloc[-1]
        prev  = df["close"].iloc[-2]

        if prev < sma20 and current_price >= sma20:
            return Signal(action="BUY", confidence=0.75, reason=f"Price crossed above SMA20 ({sma20:.2f})")

        if current_price < sma20 * 0.98:   # 2% below SMA — exit
            return Signal(action="SELL", confidence=0.80, reason="Price fell 2% below SMA20")

        return None   # no signal this bar
```

That is the complete file. Save it, click **Reload** in the Advanced tab (or `POST /api/strategies/reload`), and `"My Strategy"` appears in the Signal Strategies section ready to activate.

---

### Adding tuneable parameters

Parameters are defined as a **Pydantic model** that subclasses `StrategyConfigModel`. Every field automatically becomes a number/boolean input in the ConfigModal — labels come from the `title=` annotation, constraints from `ge=`/`le=`.

```python
from pydantic import Field
from strategies.base import BaseStrategy, Signal, StrategyMetadata, StrategyConfigModel

class MyParams(StrategyConfigModel):
    sma_period:   int   = Field(20,   ge=5,  le=200, title="SMA Period")
    exit_pct:     float = Field(2.0,  ge=0.5, le=10, title="Exit % below SMA")
    min_confidence: float = Field(0.70, ge=0.5, le=1.0, title="Min Confidence")

class MySMAStrategy(BaseStrategy):

    metadata = StrategyMetadata(
        name="SMA Crossover",
        version="1.1.0",
        description="Buys on SMA crossover, exits when price falls below SMA by exit_pct.",
        author="Your Name",
        tags=["trend"],
        risk_level="LOW",
    )

    params_model   = MyParams
    default_params = MyParams().model_dump()

    async def generate_signals(self, ticker_doc, current_price, market_data,
                               market_status, broker_allocations, params):
        df = market_data.get("history")
        if df is None or len(df) < params["sma_period"]:
            return None

        sma  = df["close"].rolling(params["sma_period"]).mean().iloc[-1]
        prev = df["close"].iloc[-2]

        if prev < sma and current_price >= sma:
            return Signal(action="BUY", confidence=params["min_confidence"],
                          reason=f"Crossed above SMA{params['sma_period']} ({sma:.2f})")

        exit_level = sma * (1 - params["exit_pct"] / 100)
        if current_price < exit_level:
            return Signal(action="SELL", confidence=0.85,
                          reason=f"Below SMA exit level ({exit_level:.2f})")

        return None
```

The `params` dict passed to `generate_signals` merges `default_params` with any per-ticker overrides the user set in the ConfigModal form — so two tickers can run the same strategy with different `sma_period` values.

---

### Signal reference

| `action` | When to use | Engine behaviour |
|----------|------------|-----------------|
| `"BUY"` | Open a long position | Executes a MARKET BUY at current price with `base_power` allocation |
| `"SELL"` | Close the current position | Executes a MARKET SELL for the full held quantity |
| `"STOP_LOSS"` | Emergency exit | Same execution as SELL; recorded as `STOP` side in trade history |
| `"HOLD"` | You have a view but don't want any action | Skips the entire bracket logic for this cycle |
| `None` (return) | No conviction this bar | Falls through to the normal bracket/trailing/stop rules |

`confidence` (0.0 – 1.0) is stored in the trade record's `reason` string for audit and history review. It does not currently filter execution — use it in your own logic if you want a minimum threshold.

---

### Using technical indicators (`ta` library)

```python
# RSI
from ta.momentum import RSIIndicator
rsi = RSIIndicator(close=df["close"], window=14).rsi().iloc[-1]

# MACD
from ta.trend import MACD
macd = MACD(close=df["close"], window_fast=12, window_slow=26, window_sign=9)
crossover = macd.macd_diff().iloc[-1]   # positive = bull, negative = bear

# Bollinger Bands
from ta.volatility import BollingerBands
bb = BollingerBands(close=df["close"], window=20, window_dev=2)
upper = bb.bollinger_hband().iloc[-1]
lower = bb.bollinger_lband().iloc[-1]

# ATR (average true range)
from ta.volatility import AverageTrueRange
atr = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14)
atr_val = atr.average_true_range().iloc[-1]
```

The `market_data["history"]` DataFrame has columns: `open`, `high`, `low`, `close`, `volume` (all lowercase). Index is a `DatetimeTzAware` series from yfinance.

---

### Optional lifecycle hooks

```python
class MyStrategy(BaseStrategy):

    async def on_load(self) -> None:
        """Called once when the strategy is registered at startup or reload."""
        # Pre-compute anything expensive here, or load a model from disk.
        pass

    async def validate_ticker(self, ticker_doc: dict) -> bool:
        """Return False to skip this strategy for a specific ticker.
        E.g., reject tickers with less than $500 buy power."""
        return ticker_doc.get("base_power", 0) >= 500
```

---

### Reload workflow

1. **Drop the file** → `backend/strategies/custom/my_strategy.py`
2. The **file watcher** (watchdog) detects the change and reloads automatically within a few seconds.
3. Or trigger manually:
   - **UI**: ConfigModal → Advanced tab → Signal Strategies → **Reload** button
   - **API**: `POST /api/strategies/reload`
   - **Telegram**: (if configured) `/reload_strategies` command
4. The WebSocket broadcasts `{"type": "STRATEGIES_RELOADED", "strategies": [...]}` to all connected clients.
5. The strategy is available immediately — no server restart needed.

If your file has a Python syntax error, the loader catches and logs it without crashing. Fix the file and reload again.

---

### Strategy file checklist

```
✅  File location:    backend/strategies/custom/your_name.py
✅  Language:         Python 3.9+
✅  Class inherits:   BaseStrategy (from strategies.base)
✅  metadata defined: StrategyMetadata(name=...) as a class variable
✅  Method defined:   async def generate_signals(...) -> Optional[Signal]
✅  Returns:          Signal(...) or None  — never raises unhandled exceptions
✅  Params (optional): subclass StrategyConfigModel, set params_model + default_params
✅  No __init__ needed unless you want custom setup (use on_load() instead)
```

---

## Edge Integration

Sentinel Pulse integrates with **sentinel-edge** for bidirectional communication. Edge can poll Pulse for decisions, and Pulse sends real-time trade and position updates to Edge.

### How It Works

```
Edge (Trading Bot)                          Pulse (Signal Engine)
     │                                            │
     │──── GET /api/tickers ────►                 │ (returns ticker list)
     │                                            │
     │──── GET /api/positions/{symbol} ───►        │ (returns position + P&L)
     │                                            │
     │──── POST /api/tickers/{symbol}/decision ──► │ (buy/sell/stop/emergency)
     │                                            │
     │◄─── 200 OK ─────────────────────────────────│ (signal accepted)
     │                                            │
     │                                            │ (after fill)
     │◄─── ORDER_FILLED command ───────────────────│ (MongoDB insert)
     │                                            │
     │                                            │ (heartbeat)
     │◄─── PULSE_STATUS command ────────────────────│ (paper/live mode)
```

### MongoDB Commands (Pulse → Edge)

Pulse inserts commands to the `commands` collection in MongoDB:

| Command | Description |
|---------|-------------|
| `ORDER_FILLED` | Trade executed notification |
| `POSITION_UPDATE` | Real-time P&L update |
| `ACCOUNT_UPDATE` | Account metrics |
| `PULSE_STATUS` | Heartbeat (trading mode, market state) |
| `BROKER_STATUS` | Broker connectivity |
| `AUTO_STOP_TRIGGERED` | Auto-stop fired |

### REST Endpoints (Edge → Pulse)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tickers` | GET | List all configured tickers |
| `/api/tickers/{symbol}/decision` | POST | Submit buy/sell/stop decision |
| `/api/tickers/{symbol}/trailing` | POST | Enable trailing stop |
| `/api/positions/{symbol}` | GET | Get position with P&L & drawdown |
| `/api/account/status` | GET | Account balance and positions |
| `/api/signals/evaluate` | POST | Signal strength scoring |
| `/api/health` | GET | Pulse health status |

### Signal Evaluation Endpoint

The `/api/signals/evaluate` endpoint calculates Edge-style signal strength:

```json
POST /api/signals/evaluate
{
  "symbol": "TSLA",
  "price": 250.00,
  "orb_high": 252.00,
  "orb_low": 248.00,
  "volume": 15000000,
  "atr": 5.50,
  "price_change_pct": 1.2
}

Response:
{
  "symbol": "TSLA",
  "direction": "bullish",
  "strength": 4.5,
  "volume_ratio": 1.8,
  "volume_zscore": 2.3
}
```

### Configuration

Enable Edge integration in `.env`:

```bash
EDGE_ENABLED=true
EDGE_API_KEY=your_api_key  # optional
MONGO_URL=mongodb://localhost:27017
DB_NAME=sentinel_pulse
```

### Files

| File | Purpose |
|------|---------|
| `shared/commands.py` | Command schemas (ORDER_FILLED, POSITION_UPDATE, etc.) |
| `shared/mongo_client.py` | EdgeMongoClient for sending commands to Edge |
| `shared/commands_utils.py` | Command builders and serializers |
| `shared/edge_integration.py` | Edge integration helpers |
| `routes/edge.py` | REST endpoints for Edge communication |

---

## MACD-V Strategy

Sentinel Pulse includes a built-in **MACD-V** signal strategy based on the StockCharts.com formula.

### What is MACD-V?

MACD-V normalizes the standard MACD by dividing by ATR (Average True Range), creating universal momentum readings that work consistently across all price levels. This solves the problem where traditional MACD values vary significantly between high-priced and low-priced stocks.

### Formula

```
MACD-V = [(12-period EMA - 26-period EMA) / ATR(26)] × 100
Signal Line = 9-period EMA of MACD-V
```

### Trading Signals

Based on StockCharts ChartSchool interpretation:

| MACD-V Value | Signal Line | Market State |
|-------------|-------------|--------------|
| < -150 | Either | **Risk** (Oversold) |
| -150 to 50 | Above | **Rebounding** |
| 50 to 150 | Above | **Rallying** |
| > 150 | Above | **Risk** (Overbought) |
| > -50 | Below | **Retracing** |
| -150 to -50 | Below | **Reversing** |

### Configuration Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `macd_fast` | 12 | 5-50 | Fast EMA period |
| `macd_slow` | 26 | 10-100 | Slow EMA period |
| `macd_signal` | 9 | 3-30 | Signal line EMA period |
| `atr_period` | 26 | 5-50 | ATR period for normalization |
| `oversold_threshold` | -150 | -300-0 | Oversold level |
| `rebounding_threshold` | 50 | -100-100 | Rebounding level |
| `rallying_threshold` | 150 | 50-300 | Rallying level |
| `overbought_threshold` | 150 | 50-500 | Overbought level |
| `min_confidence` | 0.65 | 0.50-1.0 | Minimum confidence to trade |
| `enable_reversals` | true | - | Enable reversal signals |
| `enable_retraces` | true | - | Enable retracement signals |

### Usage

1. Add a ticker in the dashboard
2. Open the ticker config modal
3. Go to the **Advanced** tab
4. Enable **MACD-V (Volume-Weighted MACD)** signal strategy
5. Configure parameters as needed
6. The strategy will generate BUY/SELL/HOLD signals based on MACD-V interpretation

### Available Indicators

The strategy system supports these technical indicators (via `ta` library):

- **RSI** - Relative Strength Index
- **MACD** - Moving Average Convergence Divergence  
- **Bollinger Bands** - Volatility bands
- **ATR** - Average True Range
- **Stochastic** - Stochastic oscillator
- **Williams %R** - Williams Percent Range
- **CCI** - Commodity Channel Index
- **And 30+ more** - See `ta` library documentation

---

## File Map — Backend

Use this map to quickly locate the code behind any feature.

### Entry Point & Infrastructure

| File | What lives here |
|------|----------------|
| `server.py` | FastAPI app, `lifespan()` startup (index creation, broker init, resilience init, background task launch), `trading_loop()` (5s tick, per-ticker market gate), `price_broadcast_loop()` (2s WebSocket push), router registration |
| `deps.py` | Shared singletons populated at startup: `db`, `engine`, `ws_manager`, `telegram_service`, `price_service`, `broker_mgr`, `tracer`, `logger`. Import this in any module that needs shared state. |
| `schemas.py` | All Pydantic models: `TickerConfig` (full ticker doc), `TickerCreate`, `TickerUpdate`, `TradeRecord`, `Position`, `TelegramConfig`, `SettingsUpdate`, `BetaRegistration`, `FeedbackReport`, `PresetStrategy`, `BrokerTestRequest` |

### Core Trading Logic

| File | What lives here |
|------|----------------|
| `trading_engine.py` | `TradingEngine` class — the heart of the bot. Key methods: `evaluate_ticker()` (signal-strategy routing first, then buy/sell/stop/trailing bracket logic), `_run_strategy_signal()` (calls registered strategy, maps BUY/SELL/HOLD to execution code), `_evaluate_partial_fills()` (scale in/out), `_auto_rebracket()`, `_is_opening_window()` / `_is_past_opening_window()` (DST-aware per market), `_is_ticker_market_open()` (per-ticker market hours + lunch-break guard in simulate mode), `_get_market()`, `check_auto_mode_switch()` (Live@Open / Paper@Close), `manual_sell()`, `cancel_pending_sell()`, `_record_trade()`, `_check_auto_stop()`, `_update_profit()`, `update_high_water_mark()` (tracks position highs), `get_drawdown_pct()` (calculates drawdown from high water mark) |
| `strategies/__init__.py` | Package root — re-exports `PRESET_STRATEGIES`, `STRATEGY_REGISTRY`, `BaseStrategy`, `Signal`, `StrategyMetadata`, `StrategyConfigModel`, `load_all_strategies`, `reload_strategies`. All existing `from strategies import PRESET_STRATEGIES` imports work unchanged. |
| `strategies/base.py` | Core abstractions: `BaseStrategy` (ABC), `Signal` (dataclass: action, confidence, reason, params), `StrategyMetadata` (name, version, description, risk_level, supported_markets), `StrategyConfigModel` (Pydantic v2 base — subclass to define typed params whose JSON schema drives the UI form) |
| `strategies/loader.py` | `STRATEGY_REGISTRY` singleton dict, `load_all_strategies()` (scans presets/ and custom/), `reload_strategies()` (hot-reload + WebSocket broadcast), `start_strategy_watcher()` (watchdog file watcher — thread-safe asyncio dispatch), `_load_from_dir()` |
| `strategies/presets/__init__.py` | `PRESET_STRATEGIES` dict: `conservative_1y`, `aggressive_monthly`, `swing_trader` — bracket config templates used by `APPLY_STRATEGY` |
| `strategies/custom/` | **Drop your custom strategy files here.** Built-in strategies: `macd.py` (MACD crossover), `rsi.py` (RSI mean reversion), `bollinger.py` (Bollinger Bands), `sma_crossover.py` (SMA golden/death cross), `macdv.py` (ATR-normalized), `multi_indicator.py` (RSI+MACD example). Any `.py` file with a `BaseStrategy` subclass is auto-loaded. |

### Broker Layer

| File | What lives here |
|------|----------------|
| `broker_manager.py` | `BrokerConnectionManager` — connects/disconnects brokers, stores encrypted credentials in MongoDB, `place_orders_for_ticker()` (parallel multi-broker order placement with failover alerts), `_place_single()` (calls `broker_resilience.before_call()` → places order → records success/failure) |
| `resilience.py` | `BrokerResilience` singleton (`broker_resilience`). Per-broker: `AsyncLimiter` token bucket, circuit breaker state machine (`CircuitBreakerState`), `before_call()`, `record_success()`, `record_failure()`, `reset_circuit()`, `get_status()`. `CircuitOpenError` exception. `BrokerResilienceConfig` with broker-type defaults (Robinhood: 2 RPS, Alpaca: 20 RPS, etc.) |
| `brokers/__init__.py` | Package re-exports: `BrokerAdapter`, `BrokerOrder`, `BROKER_REGISTRY`, `get_broker_adapter`, `get_broker_info` |
| `brokers/base.py` | `BrokerAdapter` ABC (abstract base class): `check_connection()`, `place_order()`, `get_positions()`, `get_account_info()`. `BrokerOrder`, `BrokerPosition`, `BrokerAccountInfo` dataclasses. `BrokerInfo`, `BrokerRiskWarning`, `BrokerRiskLevel` enum. |
| `brokers/registry.py` | `BROKER_REGISTRY` dict (all 9 brokers ordered LOW → HIGH risk). `get_broker_info()`. `get_broker_adapter()` factory function — instantiates the correct adapter class by broker ID. |
| `brokers/alpaca_adapter.py` | Alpaca — official REST + WebSocket API, paper and live trading |
| `brokers/ibkr_adapter.py` | Interactive Brokers — TWS/Gateway REST |
| `brokers/tda_adapter.py` | TD Ameritrade / Charles Schwab — OAuth REST |
| `brokers/thinkorswim_adapter.py` | Thinkorswim — Schwab OAuth (same API as TDA) |
| `brokers/tradier_adapter.py` | Tradier — official developer-friendly REST |
| `brokers/tradestation_adapter.py` | TradeStation — OAuth REST |
| `brokers/robinhood_adapter.py` | Robinhood — `robin_stocks` session auth (HIGH risk) |
| `brokers/webull_adapter.py` | Webull — unofficial reverse-engineered API (HIGH risk) |
| `brokers/wealthsimple_adapter.py` | Wealthsimple Trade — unofficial (Canadian, HIGH risk) |

### Prices & Markets

| File | What lives here |
|------|----------------|
| `price_service.py` | `PriceService` singleton. `get_price()` — tries broker feed first, falls back to yfinance, then cache drift. `get_avg_price()` — moving average. `get_ohlcv()` — full OHLCV DataFrame for strategy history. `get_enriched_market_data()` — builds the `market_data` dict injected into `generate_signals()`. `get_fx_rates()` — all foreign currency→USD rates (5-min cache). `update_broker_price()` — live broker WebSocket price update. Also provides volume z-score analysis: `get_volume_zscore()`, `get_volume_ratio()`, `get_signal_strength()` for Edge-style signal scoring. |
| `markets.py` | `MarketConfig` dataclass with `is_open_now()`, `is_opening_window()`, `is_past_opening_window()`, `status()`, `hours_display()`, `to_dict()`. `MARKETS` dict: `US`, `HK`, `AU`, `UK`, `CA`, `CN_SS`, `CN_SZ`. `detect_market_from_symbol()` — auto-detects market from suffix (`.HK`, `.AX`, `.L`, `.TO`, `.SS`, `.SZ`). `SUFFIX_TO_MARKET` lookup. |

### Edge Integration

| File | What lives here |
|------|----------------|
| `shared/commands.py` | Command schemas for Edge communication: `ORDER_FILLED`, `POSITION_UPDATE`, `ACCOUNT_UPDATE`, `PULSE_STATUS`, `BROKER_STATUS`, `AUTO_STOP_TRIGGERED` |
| `shared/mongo_client.py` | `EdgeMongoClient` — MongoDB client for sending commands to Edge's `commands` collection |
| `shared/commands_utils.py` | Command builders and serializers for structured command payloads |
| `shared/edge_integration.py` | Edge integration helpers: heartbeat (PULSE_STATUS), position updates, account sync |

### Services

| File | What lives here |
|------|----------------|
| `audit_service.py` | `AuditService` singleton (`audit_service`). `AuditEventType` enum (40+ event types). `log()`, `log_setting_change()`, `log_ticker_change()`, `log_trade()`, `log_broker_api()`, `log_rebracket()`, `log_rate_limit()`, `log_circuit_breaker()`, `get_logs()` (MongoDB query with filters). Logs to both MongoDB and console. |
| `telegram_service.py` | `TelegramService` — bot init, `send_trade_alert()`, `send_alert()`, bot commands (`/status`, `/help`, etc.), `reload_from_db()`, start/stop lifecycle |
| `email_service.py` | SMTP email delivery for feedback reports. Rate limited to 2/hour. `send_feedback_email()` |
| `ws_manager.py` | `ConnectionManager` — WebSocket connection pool, `connect()`, `disconnect()`, `broadcast()` (send JSON to all connected clients) |
| `telemetry.py` | OpenTelemetry setup: `setup_telemetry()`, `get_tracer()`. Configures FastAPI auto-instrumentation and optional OTLP export. |

### API Routes

| File | Prefix | What lives here |
|------|--------|----------------|
| `routes/ws.py` | `WS /api/ws` | WebSocket endpoint: sends `INITIAL_STATE` on connect, dispatches inbound messages: `ADD_TICKER` (with market auto-detection), `DELETE_TICKER`, `UPDATE_TICKER`, `START_BOT`, `STOP_BOT`, `APPLY_STRATEGY`, `TAKE_PROFIT` |
| `routes/tickers.py` | `/api/tickers` | `GET` (list), `POST` (create with market auto-detect), `PUT /{symbol}` (update), `DELETE /{symbol}`, `POST /reorder`, `POST /{symbol}/strategy/{preset}`, `GET /strategies`, `POST /{symbol}/take-profit`, `GET /cash-reserve` |
| `routes/trades.py` | `/api/trades` | Trade history with filters (symbol, side, date range), pagination, stat aggregations |
| `routes/brokers.py` | `/api/brokers` | `GET` (list all), `GET /{id}` (broker detail + risk warning), `POST /{id}/test` (full credential validation + live connection test), `POST /{id}/connect`, `POST /{id}/disconnect`, `GET /status` |
| `routes/health.py` | `/api/health` | Engine status, mode, WebSocket clients, market state, MongoDB connection |
| `routes/bot.py` | `/api/bot` | `POST /start`, `POST /stop`, `POST /pause`, `POST /resume`, `GET /status`, Telegram config endpoints |
| `routes/system.py` | `/api` | `GET /audit-logs` (filterable), `GET /audit-logs/event-types`, `GET /rate-limits` (all broker resilience statuses), `GET /rate-limits/{id}`, `POST /rate-limits/{id}` (update config), `POST /circuit/{id}/reset`, `GET /price-sources`, `POST /price-sources/toggle` |
| `routes/markets.py` | `/api` | `GET /markets` (all 7 markets with live status), `GET /markets/{code}`, `GET /fx-rates`, `GET /settings/currency-display`, `POST /settings/currency-display` |
| `routes/strategies.py` | `/api/strategies` | `GET /registry` (all signal strategies with metadata + JSON schema), `GET /registry/{name}`, `GET /presets` (bracket templates), `POST /reload` (hot-reload from disk) |
| `routes/edge.py` | `/api` | Edge integration endpoints: `GET /tickers`, `GET /positions/{symbol}`, `POST /tickers/{symbol}/decision`, `POST /tickers/{symbol}/trailing`, `GET /account/status`, `POST /signals/evaluate` |

### Tests

All tests live in `backend/tests/`. Each file maps to a specific feature:

| Test file | Feature tested |
|-----------|---------------|
| `test_resilience_feature.py` | Token-bucket rate limiting, circuit breaker state machine, `POST /rate-limits`, `POST /circuit/reset` |
| `test_markets_feature.py` | All 7 market configs, FX rates, currency-display preference persistence, market auto-detection |
| `test_brokers_api.py` | Broker listing, credential validation, connection test pipeline |
| `test_account_balance_feature.py` | Account balance, allocated/available calculations, over-allocation warnings |
| `test_opening_bell_feature.py` | Opening Bell Mode, halve-stop-loss, lock-trailing, rebracket after window |
| `test_partial_fills_feature.py` | Scale-in/scale-out legs, stop-loss on partial positions |
| `test_manual_sell_feature.py` | Market sell, limit sell, cancel pending sell |
| `test_rebracket_params.py` | Auto-rebracket trigger, threshold, spread, cooldown, lookback |
| `test_trading_mode_features.py` | Paper/live mode, `simulate_24_7`, `market_hours_only`, Live@Open/Paper@Close auto-switch |
| `test_order_type_feature.py` | MARKET vs LIMIT order types per side |
| `test_trade_metadata_feature.py` | Full trade record metadata (entry, target, avg, value, broker results) |
| `test_trading_cooldown.py` | 30-second cooldown between trades per ticker |
| `test_loss_log_feature.py` | Loss log file generation and retrieval |
| `test_traces_api.py` | `/api/traces` OpenTelemetry span listing |
| `test_chart_preset_features.py` | Preset strategy application and revert |
| `test_reorder_config_modal.py` | Ticker drag-and-drop reorder persistence |
| `test_feedback_broker_test.py` | Feedback submission, broker test pipeline regression |
| `test_beta_brokers_metrics.py` | Beta registration, broker listing, Prometheus metrics |
| `test_refactor_regression.py` | Full regression suite across major refactors |

---

## File Map — Frontend

### Application Shell

| File | What lives here |
|------|----------------|
| `src/main.tsx` | React app entry point, `<App>` mount |
| `src/App.tsx` | Root component: `<Dashboard>` + Sonner toast provider |
| `src/index.css` | Global dark theme CSS variables (`--background`, `--primary`, etc.), glass-morphism utilities, glow animations |

### Top-Level Components

| File | What lives here |
|------|----------------|
| `components/Dashboard.tsx` | Main layout shell: tab bar (Watchlist/Positions/History/Logs/Brokers/Foreign/Traces/Settings), tab content switcher, **FX rate pre-load on mount** (`GET /api/fx-rates` + `GET /api/settings/currency-display`, refreshes every 5 min) |
| `components/Header.tsx` | Top bar: bot name, connection status badge, market-open badge, trading mode badge, account balance / allocated / available / total P&L / cash reserve chips, Add Stock button, Feedback button, Start/Stop bot |
| `components/TickerCard.tsx` | Individual ticker card. Includes: market flag (🇦🇺 🇬🇧 etc.) + symbol, **dual-currency price display** (primary + secondary in muted text), Net P&L with sign, buy/sell targets formatted in the selected currency, buy-power chip in native currency symbol, broker multi-select chips (with failure flash animation), position indicator, live price chart (`LineChart`), drag handle (dnd-kit `useSortable`), enable/disable toggle, configure / take profit / remove actions |
| `components/ConfigModal.tsx` | Full ticker configuration modal with 5 tabs: **Rules** (buy/sell offsets, currency-aware buy power label + FX hint), **Partial Fills** (leg editor for scale in/out), **Risk** (opening bell mode, halve stop, lock trailing, stop-loss, trailing stop, risk controls), **Rebracket** (auto-rebracket params), **Advanced** (preset bracket strategy pills + **signal strategy cards** with Switch toggle, expandable dynamic param forms auto-generated from Pydantic JSON schema, Reload button) |
| `components/AddTickerDialog.tsx` | Add ticker form: symbol input with **auto-detect market from suffix**, market dropdown (7 options), buy-power input with budget context, over-allocation warning |
| `components/TradeLogSidebar.tsx` | Right-side live trade activity feed — shows last N trades in real-time as WebSocket `TRADE` messages arrive |
| `components/CommandPalette.tsx` | Cmd+K (or Ctrl+K) command palette — jump to any tab, quick actions |
| `components/FeedbackDialog.tsx` | Bug/suggestion/complaint form. Submits to `POST /api/feedback`. |
| `components/BetaRegistrationModal.tsx` | Beta tester registration form (currently disabled in routing) |
| `components/ErrorBoundary.tsx` | React error boundary — catches render errors, shows fallback label |

### Tab Panels

| File | Tab | What lives here |
|------|-----|----------------|
| `components/tabs/WatchlistTab.tsx` | Watchlist | Drag-and-drop ticker grid (dnd-kit `SortableContext`), P&L sort (descending), Live @ Open toggle, Paper @ Close toggle, active/inactive sections, config modal trigger |
| `components/tabs/PositionsTab.tsx` | Positions | Open positions table: symbol, qty, avg entry, current price, market value, unrealized P&L, manual sell (market/limit) dialog |
| `components/tabs/HistoryTab.tsx` | History | Trade history with stat cards (total trades, win rate, total P&L), symbol/side/date filters, sortable table, expandable detail rows (full metadata: order type, rule mode, targets, trail details, broker results) |
| `components/tabs/LogsTab.tsx` | Logs | Loss log file browser: date picker → file list → file content viewer |
| `components/tabs/BrokersTab.tsx` | Brokers | Per-broker panels: credential form (dynamic per `auth_fields`), connect/disconnect, risk warning badge, test-connection button, rate limit + circuit breaker config (max RPS, burst, cooldown, failure threshold, recovery timeout), price feed preference toggle |
| `components/tabs/ForeignTab.tsx` | Foreign | International market sub-tabs (HK / AU / UK / CA / CN SSE / CN SZE), live market clock + status (OPEN/CLOSED/LUNCH), FX rate to USD, example tickers, trading notes, pence warning (UK), **USD ↔ Native currency toggle** (persisted to MongoDB), FX rate refresh button |
| `components/tabs/SettingsTab.tsx` | Settings | Account balance input, Telegram bot token + chat IDs, trading mode switches (Live/Paper/24-7/Market-Hours-Only), step increment/decrement size |
| `components/tabs/TracesTab.tsx` | Traces | OpenTelemetry span viewer: stat cards (trade executions, ticker evaluations, HTTP requests), span table with name/kind/status/duration, expandable attributes/events, name filter, refresh |

### Reusable Widgets

| File | What lives here |
|------|----------------|
| `components/ticker-card/ConfigWidgets.tsx` | Shared form primitives used by both `TickerCard` and `ConfigModal`: `SteppedInput` (number field with ±nudge buttons), `OffsetInput` (sign-aware % or $ input with correct color coding), `OrderTypeToggle` (LIMIT/MARKET pill toggle), `ConfigSection` (labelled grid wrapper), `ConfigToggle` (checkbox + label), `useDecimalInput` (hook for controlled decimal text input) |

### State & Utilities

| File | What lives here |
|------|----------------|
| `hooks/useWebSocket.ts` | WebSocket lifecycle: `connect()` with 3s auto-reconnect, `onmessage` dispatcher (handles `INITIAL_STATE`, `PRICE_UPDATE`, `TRADE`, `TICKER_ADDED/UPDATED/DELETED`, `BOT_STATUS`, `MODE_SWITCH`, `BROKER_FAILED`, etc.), `send(action, payload)` helper |
| `stores/useStore.ts` | Zustand global store. State slices: `tickers`, `prices`, `priceHistory` (120-pt ring buffer), `positions`, `profits`, `trades`, `connected`, `running/paused/marketOpen`, `simulate247/liveDuringMarketHours/paperAfterHours`, `accountBalance/allocated/available`, `cashReserve`, `chartEnabled`, `activeTab`, `incrementStep/decrementStep`, `tradingMode`, `failedBrokers` (broker chip flash animation), **`currencyDisplay` ('usd'\|'native')**, **`fxRates`** (Record<currency, usdRate>) |
| `lib/api.ts` | `apiFetch(path, options?)` — wraps `fetch` with `REACT_APP_BACKEND_URL` prefix, `Content-Type: application/json`, JSON error unwrapping |
| `lib/market-utils.ts` | `MARKET_META` (flag, currency, currencySymbol per market code), `detectMarketCode()` (from `ticker.market` or symbol suffix), `getMarketMeta()`, `formatPrice()` (native or USD via FX rates), `formatPriceSecondary()` (opposite currency for dual-currency display) |
| `lib/utils.ts` | `cn(...classes)` — Tailwind class merge utility (clsx + tailwind-merge) |

---

## API Reference

### Trading Engine Control
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Engine status, mode, market state, WS client count |
| POST | `/api/bot/start` | Start the trading engine |
| POST | `/api/bot/stop` | Stop the trading engine |
| POST | `/api/bot/pause` | Pause (stops evaluation, keeps engine running) |
| POST | `/api/bot/resume` | Resume after pause |
| GET | `/api/bot/status` | Running, paused, mode, simulate_24_7 |

### Strategies
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/strategies/registry` | All registered signal strategies with metadata + Pydantic JSON schema |
| GET | `/api/strategies/registry/{name}` | Single strategy detail |
| GET | `/api/strategies/presets` | Bracket-template preset list (backward-compat) |
| POST | `/api/strategies/reload` | Hot-reload all strategies from disk |

### Tickers
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tickers` | All ticker configs |
| POST | `/api/tickers` | Add ticker (auto-detects market from symbol suffix) |
| PUT | `/api/tickers/{symbol}` | Update ticker config fields |
| DELETE | `/api/tickers/{symbol}` | Remove ticker |
| POST | `/api/tickers/reorder` | Persist drag-and-drop sort order |
| POST | `/api/tickers/{symbol}/strategy/{preset}` | Apply preset strategy (or revert to custom) |
| GET | `/api/strategies` | List available preset strategies |
| POST | `/api/tickers/{symbol}/take-profit` | Move realized P&L to cash reserve |
| GET | `/api/cash-reserve` | Cash reserve total + ledger |

### Positions & Trades
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/trades` | Trade history (filterable by symbol, side, date) |
| POST | `/api/positions/{symbol}/sell` | Manual sell (market or limit) |
| GET | `/api/positions/pending-sells` | Pending limit sell orders |
| DELETE | `/api/positions/pending-sells/{symbol}` | Cancel pending limit sell |

### Brokers
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/brokers` | All brokers ordered LOW→HIGH risk |
| GET | `/api/brokers/{id}` | Broker detail + risk warning |
| POST | `/api/brokers/{id}/test` | Full credential validation + live connection test |
| POST | `/api/brokers/{id}/connect` | Connect broker with provided credentials |
| POST | `/api/brokers/{id}/disconnect` | Disconnect broker |
| GET | `/api/brokers/status` | All broker connection statuses |

### Markets & Currency
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/markets` | All 7 markets with live status, local time, hours |
| GET | `/api/markets/{code}` | Single market detail (e.g. `/api/markets/HK`) |
| GET | `/api/fx-rates` | Live FX rates → USD for all foreign markets |
| GET | `/api/settings/currency-display` | Get saved display preference ('usd'\|'native') |
| POST | `/api/settings/currency-display?mode=native` | Save display preference |

### Resilience (Rate Limits + Circuit Breakers)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/rate-limits` | All broker resilience statuses (circuit state, failures, config) |
| GET | `/api/rate-limits/{broker_id}` | Single broker resilience status |
| POST | `/api/rate-limits/{broker_id}` | Update token-bucket + circuit-breaker config |
| POST | `/api/circuit/{broker_id}/reset` | Manually reset tripped circuit breaker to CLOSED |

### Audit & System
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/audit-logs` | Audit logs (filter: event_type, symbol, broker_id, success, limit) |
| GET | `/api/audit-logs/event-types` | All available AuditEventType values |
| GET | `/api/price-sources` | Current price data source per symbol |
| POST | `/api/price-sources/toggle?prefer_broker=true` | Switch between broker feeds and yfinance |
| GET | `/api/metrics` | Prometheus-scrapeable metrics (15+ metrics) |
| GET | `/api/traces` | OpenTelemetry spans (filterable, paginated) |

### Settings, Logs & Feedback
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings` | All settings |
| POST | `/api/settings` | Update account balance, Telegram, trading mode |
| GET | `/api/logs/loss/dates` | Dates that have loss log files |
| GET | `/api/logs/loss/files/{date}` | Loss log filenames for a date |
| GET | `/api/logs/loss/file/{date}/{filename}` | Raw text of a loss log file |
| POST | `/api/feedback` | Submit bug report / suggestion / complaint |

### WebSocket Messages (Inbound — Client → Server)
| `action` | Payload | Description |
|----------|---------|-------------|
| `ADD_TICKER` | `{symbol, base_power, market?}` | Add new ticker (market auto-detected from suffix) |
| `DELETE_TICKER` | `{symbol}` | Remove ticker |
| `UPDATE_TICKER` | `{symbol, ...fields}` | Update any ticker fields |
| `START_BOT` | — | Start trading engine |
| `STOP_BOT` | — | Stop trading engine |
| `APPLY_STRATEGY` | `{symbol, preset}` | Apply preset (or toggle back to custom) |
| `TAKE_PROFIT` | `{symbol}` | Move P&L to cash reserve |

### WebSocket Messages (Outbound — Server → Client)
| `type` | Description |
|--------|-------------|
| `INITIAL_STATE` | Full state dump on connect (tickers, prices, profits, settings) |
| `PRICE_UPDATE` | Every 2s: prices, positions, profits, engine status |
| `TRADE` | Fired on every trade execution |
| `TICKER_ADDED / UPDATED / DELETED` | Ticker change broadcasts |
| `TICKERS_REORDERED` | After drag-and-drop reorder |
| `ACCOUNT_UPDATE` | After base_power change |
| `BOT_STATUS` | Running/paused state change |
| `MODE_SWITCH` | Auto Live↔Paper mode transition |
| `BROKER_FAILED` | Broker order failure with reason and symbol |
| `CIRCUIT_STATE_CHANGE` | Circuit breaker open/closed/half-open |
| `PENDING_SELL` | Limit sell queued |
| `PENDING_SELL_CANCELLED` | Limit sell cancelled |
| `PROFITS_UPDATE` | After take-profit |

---

## Database Schema

### `tickers` collection
```
symbol               string   — ticker symbol (e.g. "AAPL", "BHP.AX")
market               string   — exchange code ("US", "HK", "AU", "UK", "CA", "CN_SS", "CN_SZ")
base_power           float    — total buy power in market's native currency
avg_days             int      — moving average lookback period
buy_offset           float    — buy trigger offset (% or $)
buy_percent          bool     — true = %, false = $
buy_order_type       string   — "limit" | "market"
sell_offset          float    — sell trigger offset
sell_percent         bool
sell_order_type      string
stop_offset          float    — stop-loss offset
stop_percent         bool
stop_order_type      string
trailing_enabled     bool
trailing_percent     float    — trailing stop distance
trailing_percent_mode bool    — true = %, false = $
trailing_order_type  string
partial_fills_enabled bool
buy_legs             array    — [{alloc_pct, offset, is_percent}]
sell_legs            array    — [{alloc_pct, offset, is_percent}]
opening_bell_enabled bool     — force trailing stop during first 30 min
opening_bell_trail_value float
opening_bell_trail_is_percent bool
halve_stop_at_open   bool     — tighten stop-loss 50% at open
lock_trailing_at_open bool    — pause trailing evaluation at open
auto_rebracket       bool
rebracket_threshold  float
rebracket_spread     float
rebracket_cooldown   int      — seconds
rebracket_lookback   int      — price tick count
rebracket_buffer     float
max_daily_loss       float    — 0 = disabled
max_consecutive_losses int    — 0 = disabled
auto_stopped         bool
auto_stop_reason     string
enabled              bool
compound_profits     bool
wait_day_after_buy   bool
broker_ids           array    — ["alpaca", "robinhood"]
broker_allocations   object   — {"alpaca": 100, "robinhood": 50}
sort_order           int
strategy             string   — "custom" | preset name | signal strategy name
strategy_config      object   — per-ticker param overrides for signal strategies (e.g. {"rsi_period": 21})
```

### `trades` collection
```
id                   uuid
symbol               string
side                 string   — "BUY" | "SELL" | "STOP" | "TRAILING_STOP"
price                float
quantity             float
reason               string   — human-readable trigger description
pnl                  float
timestamp            ISO string
order_type           string   — "MARKET" | "LIMIT" | "STOP"
rule_mode            string   — "PERCENT" | "DOLLAR"
entry_price          float
target_price         float
total_value          float
buy_power            float
avg_price            float    — moving average at time of trade
sell_target          float
stop_target          float
trail_high           float
trail_trigger        float
trail_value          float
trail_mode           string
trading_mode         string   — "paper" | "live"
broker_results       array    — [{broker_id, status, order_id, filled_price, error}]
```

### `settings` collection
Documents keyed by `"key"` field:

| key | value | Description |
|-----|-------|-------------|
| `engine_state` | object | running, paused, simulate_24_7, market_hours_only, live_during_market_hours, paper_after_hours |
| `account_balance` | float | Declared total account balance |
| `telegram_config` | object | bot_token, chat_ids |
| `increment_step` | float | UI nudge step for inputs |
| `decrement_step` | float | UI nudge step for inputs |
| `prefer_broker_feeds` | bool | Use broker WebSocket for prices vs yfinance |
| `cash_reserve` | float | Accumulated take-profit cash |
| `brokers_resilience` | object | Per-broker resilience config map |
| `currency_display` | string | "usd" or "native" — price display mode |

### `audit_logs` collection
```
timestamp    ISO string
event_type   string   — AuditEventType value (e.g. "BROKER_CIRCUIT_OPEN", "SETTING_CHANGED")
symbol       string?
broker_id    string?
success      bool
error_message string?
details      object   — event-specific payload
```

### Other Collections
| Collection | Purpose |
|-----------|---------|
| `profits` | `{symbol, total_pnl, trade_count, updated_at}` — cumulative realized P&L per ticker |
| `broker_credentials` | Encrypted broker credentials (XOR + base64, keyed by `CREDENTIAL_KEY` env var) |
| `feedback` | Submitted bug reports and suggestions |
| `beta_registrations` | Beta tester personal data + agreement |
| `cash_ledger` | Append-only log of take-profit events |

---

## Environment Variables

### Backend — `backend/.env`
| Variable | Required | Description |
|----------|----------|-------------|
| `MONGO_URL` | Yes | MongoDB connection string (e.g. `mongodb://localhost:27017`) |
| `DB_NAME` | Yes | Database name |
| `CREDENTIAL_KEY` | No | XOR key for broker credential encryption (defaults to a built-in key) |
| `SMTP_HOST` | No | SMTP server hostname |
| `SMTP_PORT` | No | SMTP port (default 587) |
| `SMTP_USER` | No | SMTP username |
| `SMTP_PASSWORD` | No | SMTP password |
| `SMTP_RECIPIENT` | No | Admin email for feedback/beta notifications |
| `CORS_ORIGINS` | No | Comma-separated allowed origins (default `*`) |
| `PORT` | No | Server port (default `8002`) |
| `DEMO_MODE` | No | Set `true` to run without MongoDB (seeds default tickers) |
| `PULSE_API_URL` | No | Sentinel Edge URL for OTel auto-discovery |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | OTLP collector URL (e.g. Jaeger, Grafana Tempo) |
| `OTEL_CONSOLE_EXPORT` | No | Set `true` to print spans to console |

### Frontend — `frontend/.env`
| Variable | Required | Description |
|----------|----------|-------------|
| `REACT_APP_BACKEND_URL` | Yes | Backend base URL (e.g. `https://your-app.example.com`) |

---

## Broker Catalogue

Brokers are ordered LOW → HIGH risk in the UI and API.

| ID | Name | Risk | Auth Fields | Notes |
|----|------|------|-------------|-------|
| `alpaca` | Alpaca | LOW | `api_key`, `api_secret`, `paper` | Official API, best for automation |
| `ibkr` | Interactive Brokers | LOW | `gateway_url`, `account_id` | Requires TWS/Gateway running locally |
| `tradier` | Tradier | LOW | `access_token`, `account_id` | Clean developer API |
| `tradestation` | TradeStation | LOW | `ts_client_id`, `ts_client_secret`, `ts_refresh_token` | OAuth2 |
| `td_ameritrade` | TD Ameritrade (Schwab) | MEDIUM | `client_id`, `refresh_token` | Migrated to Schwab API |
| `thinkorswim` | Thinkorswim (Schwab) | MEDIUM | `tos_consumer_key`, `tos_refresh_token`, `tos_account_id` | Same API as TDA |
| `robinhood` | Robinhood | HIGH | `username`, `password`, `mfa_code` | Session auth — ban risk |
| `webull` | Webull | HIGH | `username`, `password`, `device_id`, `trade_token` | Unofficial API — ban risk |
| `wealthsimple` | Wealthsimple Trade | HIGH | `ws_email`, `ws_password`, `ws_otp_code` | Canadian broker — unofficial |

**Rate Limiting Defaults (Token Bucket + Circuit Breaker):**

| Broker | Max RPS | Burst | Cooldown | CB Threshold | CB Recovery |
|--------|---------|-------|----------|--------------|-------------|
| robinhood | 2.0 | 5 | 800ms | 3 failures | 120s |
| webull | 3.0 | 6 | 600ms | 3 failures | 120s |
| schwab | 5.0 | 10 | 400ms | 4 failures | 90s |
| ibkr | 10.0 | 20 | 200ms | 5 failures | 45s |
| tradestation | 10.0 | 15 | 200ms | 5 failures | 45s |
| tradier | 15.0 | 25 | 150ms | 5 failures | 30s |
| alpaca | 20.0 | 30 | 100ms | 5 failures | 30s |

Robinhood and Webull also have `skip_during_opening: true` — skipped for the first 15 minutes after market open.

---

## International Markets

Seven exchanges are supported. The engine auto-detects the market from the yfinance symbol suffix.

| Code | Exchange | Timezone | Hours | Currency | yfinance Suffix | Example |
|------|----------|----------|-------|----------|-----------------|---------|
| `US` | NYSE / NASDAQ | ET (UTC-5) | 09:30–16:00 | USD ($) | *(none)* | `AAPL` |
| `HK` | HKEX | HKT (UTC+8) | 09:30–16:00 *(lunch 12–13)* | HKD (HK$) | `.HK` | `0700.HK` |
| `AU` | ASX | AEST (UTC+10) | 10:00–16:00 | AUD (A$) | `.AX` | `BHP.AX` |
| `UK` | LSE | GMT (UTC+0) | 08:00–16:30 | GBP (£)* | `.L` | `BARC.L` |
| `CA` | TSX | ET (UTC-5) | 09:30–16:00 | CAD (C$) | `.TO` | `RY.TO` |
| `CN_SS` | Shanghai SSE | CST (UTC+8) | 09:30–15:00 *(lunch 11:30–13)* | CNY (¥) | `.SS` | `600036.SS` |
| `CN_SZ` | Shenzhen SZSE | CST (UTC+8) | 09:30–15:00 *(lunch 11:30–13)* | CNY (¥) | `.SZ` | `000001.SZ` |

*UK LSE prices from yfinance are returned in pence (GBX), not pounds (GBP). 100 GBX = £1. A warning is shown in the Foreign tab.

**DST note:** All timezone offsets are standard (non-DST). US EDT, UK BST, and AU AEDT seasonal adjustments are not currently auto-applied. ±1 hour inaccuracy during transition weeks.

**Currency display** (toggle in Foreign tab, persisted to MongoDB):
- **USD mode** — all prices multiplied by live FX rate (e.g. AUD/USD = 0.693) before display
- **Native mode** — prices shown as returned by yfinance in the market's local currency

FX rates fetched from yfinance pairs (`AUDUSD=X`, `HKDUSD=X`, etc.), cached 5 minutes, refreshed on the Foreign tab and on Dashboard mount.

---

## Resilience Architecture

Every broker API call is governed by `resilience.py` before execution:

```
broker_manager._place_single()
    │
    └─► broker_resilience.before_call(broker_id)
            │
            ├─ Circuit OPEN? → raise CircuitOpenError (skip broker)
            ├─ Circuit HALF_OPEN? → allow one test call
            └─ Acquire token from AsyncLimiter(burst, burst/max_rps)
                    │ (blocks if bucket empty, releases gradually)
                    └─► adapter.place_order()
                            │
                            ├─ Success → record_success() → half-open may close circuit
                            └─ Failure → record_failure() → may open circuit
                                            │
                                            ├─ Telegram alert: "🔴 CIRCUIT BREAKER OPEN"
                                            ├─ WebSocket: CIRCUIT_STATE_CHANGE
                                            └─ Audit log: BROKER_CIRCUIT_OPEN
```

**Circuit Breaker States:**
- `CLOSED` — normal operation
- `OPEN` — all calls rejected immediately for `recovery_timeout_seconds`
- `HALF_OPEN` — allows `half_open_max_calls` test calls; success closes it, failure reopens it

Manage via API: `GET /api/rate-limits`, `POST /api/rate-limits/{id}` (update config), `POST /api/circuit/{id}/reset` (manual reset).

---

## Production Readiness Matrix

This section tracks the implementation status of all features documented in this README against the current codebase on the `Sentinel-Prod` branch.

### Status Legend

| Status | Description |
|--------|-------------|
| ✅ **Implemented** | Fully functional, tested, and verified |
| 🔵 **Partial** | Core functionality present, needs production hardening |
| 🚧 **Planned** | Architecture in place, full implementation pending |

### Security & Authentication

| Feature | Status | Implementation |
|---------|--------|--------------|
| JWT Authentication | ✅ Implemented | `backend/auth.py` |
| RBAC Roles (trader/risk_officer/admin/viewer) | ✅ Implemented | `backend/auth.py` |
| API Key Management | ✅ Implemented | `backend/routes/auth.py` |
| Session Management | ✅ Implemented | `backend/auth.py` |
| OIDC/SSO Integration | 🔵 Partial | Config ready, requires vault integration for production |
| Secrets Vault | 🔵 Partial | `backend/config.py` with vault stub |

### Risk Controls

| Feature | Status | Implementation |
|---------|--------|--------------|
| Pre-Trade Risk Gateway | ✅ Implemented | `backend/risk_controls.py` |
| Hierarchical Kill Switches | ✅ Implemented | `backend/risk_controls.py` |
| Exposure Limits | ✅ Implemented | `backend/risk_controls.py` |
| Fat-Finger Protection | ✅ Implemented | `backend/risk_controls.py` |
| Symbol Restrictions | ✅ Implemented | `backend/risk_controls.py` |

### Backend API Routes

| Route Module | Status | Notes |
|------------|--------|-------|
| `/api/ws` | ✅ Implemented | WebSocket with message dispatch |
| `/api/tickers` | ✅ Implemented | CRUD operations |
| `/api/trades` | ✅ Implemented | Trade history |
| `/api/brokers` | ✅ Implemented | Broker management |
| `/api/health` | ✅ Implemented | Including environment info |
| `/api/bot` | ✅ Implemented | Bot control |
| `/api/system` | ✅ Implemented | Audit logs, rate limits |
| `/api/markets` | ✅ Implemented | 7 markets, FX rates |
| `/api/strategies` | ✅ Implemented | Strategy registry |
| `/api/edge` | ✅ Implemented | Edge integration |
| `/api/auth` | ✅ Implemented | Login, API keys |
| `/api/risk` | ✅ Implemented | Risk controls |
| `/api/orders` | ✅ Implemented | Order management |
| `/api/reconciliation` | 🔵 Partial | Demo data, needs broker integration |
| `/api/audit` | 🔵 Partial | Demo events, needs full audit pipeline |
| `/api/ops` | 🔵 Partial | Demo data, needs observability integration |
| `/api/analytics` | 🔵 Partial | Demo data, needs live metrics |
| `/api/slo` | 🔵 Partial | SLO definitions, needs Prometheus |

### Frontend Dashboard Tabs

| Tab | Status | Implementation |
|-----|--------|--------------|
| Watchlist | ✅ Implemented | Existing |
| Positions | ✅ Implemented | Existing |
| History | ✅ Implemented | Existing |
| Logs | ✅ Implemented | Existing |
| Brokers | ✅ Implemented | Existing |
| Foreign | ✅ Implemented | 7 exchanges |
| Traces | ✅ Implemented | OpenTelemetry |
| Settings | ✅ Implemented | Existing |
| Risk Center | ✅ Implemented | `RiskCenterTab.tsx` |
| Orders | ✅ Implemented | `OrdersExecutionTab.tsx` |
| Reconciliation | 🔵 Partial | Demo data |
| Compliance & Audit | 🔵 Partial | Demo events |
| Incidents/Ops | 🔵 Partial | Demo data |
| Portfolio Analytics | 🔵 Partial | Demo metrics |
| Admin/IAM | 🔵 Partial | User management UI |
| SLO Dashboard | 🔵 Partial | SLO definitions |

### Environment & Deployment

| Feature | Status | Implementation |
|---------|--------|--------------|
| Environment Config | ✅ Implemented | `backend/config.py` |
| Demo Mode | ✅ Implemented | `DEMO_MODE=true` |
| Docker Support | ✅ Implemented | `docker-compose.yml` |
| Windows Installer | ✅ Implemented | PyInstaller + Inno Setup |
| GitHub Actions CI/CD | ✅ Implemented | `.github/workflows/` |

### SLOs & Alerting

| SLO | Status | Notes |
|-----|-------|-------|
| API Availability | 🔵 Partial | Defined, needs Prometheus metrics |
| API Latency P95 | 🔵 Partial | Defined, needs Prometheus metrics |
| Order Execution Success | 🔵 Partial | Defined, needs order tracking |
| WebSocket Connectivity | 🔵 Partial | Defined, needs metrics |
| Price Feed Latency | 🔵 Partial | Defined, needs metrics |

### Demo vs Production Endpoints

The following endpoints include **demo/sample data** for UI testing and need **live broker/integration integration** for production:

1. **`/api/reconciliation/records`** - Returns demo reconciliation records; needs broker statement sync
2. **`/api/audit/events`** - Includes demo audit events; uses existing audit_service
3. **`/api/ops/services`** - Returns demo service health; needs observability integration
4. **`/api/ops/incidents`** - Returns demo incidents; needs alerting integration
5. **`/api/analytics/*`** - Returns demo analytics; needs real metrics
6. **`/api/slo/*`** - SLO definitions in place; needs metric collection

### Build & Runtime Status

| Component | Status |
|-----------|--------|
| Backend starts | ✅ Verified |
| Frontend builds | ✅ Verified |
| WebSocket connects | ✅ Verified |
| Demo mode runs | ✅ Verified |
| MongoDB integration | ✅ Verified |
| Multi-broker execution | ✅ Verified |
| Paper/live trading | ✅ Verified |
## Roadmap: Planned Upgrades & Enhancements

The following features and improvements are planned for future releases. Priority may shift based on user feedback and market developments.

> **Note:** Items marked with ✅ have been implemented in the current release.

### 1. UI/UX Improvements ✅
- **Theme System**: Dark/light mode toggles, custom accent colors, compact vs. expanded card views
- **Enhanced Charts**: TradingView-powered charts with drawing tools, annotations, and multi-timeframe analysis
- **Widget System**: Drag-and-drop dashboard customization
- **Keyboard Navigation**: Full keyboard shortcuts for power users

### 2. Advanced Portfolio Analytics ✅
- **Multi-Account Views**: Unified portfolio view across all connected brokers
- **Portfolio Comparison**: Side-by-side performance analytics across accounts
- **Tax Reporting**: Realized/unrealized P&L with cost-basis tracking (wash sale warnings)
- **Performance Attribution**: Return decomposition by ticker, strategy, and time period

### 3. Enhanced Notification Systems ✅
- **Email Notifications**: Rich HTML email alerts with charts
- **Mobile Companion**: iOS/Android companion app for monitoring
- **Slack Integration**: Slack channel alerts with actionable buttons
- **Webhook System**: Custom outbound webhooks for automation

### 4. Developer Experience & Extensibility ✅
- **Web-Based Terminal**: In-browser Python REPL for custom scripting
- **Public API**: Documented REST API for third-party integrations
- **SDK**: TypeScript/Python SDKs for building extensions
- **Plugin System**: First-class plugin architecture for custom indicators

### 5. Advanced Risk Management
- **ML Risk Assessment**: Predictive risk scoring per trade
- **Dynamic Circuit Breakers**: AI-adjusted rate limits based on market volatility
- **Predictive Liquidity**: Position sizing based on predicted volume
- **Var/Cvar Limits**: Value-at-risk portfolio limits

### 6. Desktop Integration Enhancements ✅
- **System Tray**: Background operation with tray icon and menu
- **Global Hotkeys**: Trade execution from anywhere (keyboard shortcuts)
- **Native Notifications**: OS-native push notifications
- **Auto-Start**: Launch on system boot

### 7. Security & Compliance ✅
- **SSO/SAML**: Enterprise single sign-on
- **2FA**: Hardware key support (YubiKey)
- **Audit Dashboard**: Real-time compliance and access logging
- **Role-Based Access**: Fine-grained permissions for teams

---

*Sentinel Pulse — Signal Forge Laboratory*
