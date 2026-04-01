# Sentinel Pulse - Product Requirements Document

## Original Problem Statement
Build a sophisticated trading bot with bracket-based trading rules, multi-broker support, and advanced risk management features including time-based rules, Windows installer, P&L sorting, auto Live/Paper switching, and robust per-broker rate limiting & circuit breaker architecture.

## Core Features Implemented

### Trading Engine
- **Bracket Trading**: Buy/Sell/Stop rules based on moving average offsets (% or $)
- **Multi-Broker Support**: Alpaca, Robinhood, Interactive Brokers, TD Ameritrade, Tradier, TradeStation, Schwab
- **Paper/Live Trading Modes**: Simulated 24/7 trading and live broker execution
- **Partial Fills (Scale In/Out)**: Buy and sell in multiple legs at different price levels

### Time-Based Risk Management
- **Opening Bell Mode**: Force trailing stop during first 30 mins after market open
  - Separate trail value (% or $) from normal trailing stop
  - Tracks session high, sells if price drops by trail amount
  - Auto-rebrackets to new price level after 30 min window
- **Halve Stop Loss at Open**: Cuts stop-loss distance in half (0.5x) during opening volatility

### Auto Trading Mode Switching
- **Live @ Open**: Auto-switches to live trading when market opens
- **Paper @ Close**: Auto-switches to paper mode when market closes
- Only triggers on market open/close transitions (not continuously)

### Resilience Architecture (DONE - April 2026)
- **Token-Bucket Rate Limiting** via `aiolimiter` (in `resilience.py`)
  - Per-broker configurable: `max_rps`, `burst`, `cooldown_ms`
  - Burst capacity properly wired: `AsyncLimiter(burst, burst/max_rps)`
  - Conservative defaults for high-risk brokers (Robinhood: 2 RPS, Webull: 3 RPS)
- **Circuit Breaker State Machine**: CLOSED → OPEN → HALF_OPEN → CLOSED
  - Per-broker configurable: `failure_threshold`, `failure_window_seconds`, `recovery_timeout_seconds`
  - Telegram alert + WebSocket broadcast on state changes
  - `skip_during_opening` flag: skip high-risk brokers during market opening window
- **`rate_limiter.py` removed** entirely — replaced by `resilience.py`
- **Audit integration**: every failure, circuit trip, and recovery logged to audit_logs
- **API endpoints**: `GET/POST /api/rate-limits/{broker_id}`, `POST /api/circuit/{broker_id}/reset`

### Resilience Config Defaults
| Broker     | max_rps | burst | cooldown | failure_threshold | recovery_timeout |
|------------|---------|-------|----------|-------------------|-----------------|
| robinhood  | 2.0     | 5     | 800ms    | 3                 | 120s            |
| webull     | 3.0     | 6     | 600ms    | 3                 | 120s            |
| alpaca     | 20.0    | 30    | 100ms    | 5                 | 30s             |
| ibkr       | 10.0    | 20    | 200ms    | 5                 | 45s             |
| tradier    | 15.0    | 25    | 150ms    | 5                 | 30s             |
| schwab     | 5.0     | 10    | 400ms    | 4                 | 90s             |

### Position Management
- Manual position sell (market or limit orders)
- Pending limit sell tracking
- Trailing stop with customizable % or $ values
- Compound profits option

### Risk Controls
- Max daily loss limit
- Max consecutive losses limit
- Auto-stop with manual re-enable required

### Auto-Rebracket
- Threshold-based bracket adjustment
- Cooldown period
- Lookback period for recent low detection

### Notifications
- Telegram bot integration for alerts
- Trade notifications with detailed metadata

### Audit Logging
- Structured audit logs for all significant actions (trades, settings, broker API calls, circuit breaker events)
- Filterable via `GET /api/audit-logs`

### Windows Installer
- Inno Setup script for `.exe` installer
- Bundles MongoDB, Python, and UI
- GitHub Actions pipeline for automated builds

## Architecture

```
/app
├── backend/
│   ├── brokers/          # Broker adapters
│   ├── routes/
│   │   ├── system.py     # Audit logs, resilience status endpoints
│   │   └── ...
│   ├── audit_service.py  # Structured audit logging
│   ├── broker_manager.py # Broker connections (_place_single uses broker_resilience)
│   ├── deps.py           # Shared state
│   ├── price_service.py  # Price feeds (broker WS or yfinance fallback)
│   ├── resilience.py     # Token-bucket + circuit breaker (replaces rate_limiter.py)
│   ├── schemas.py        # Pydantic models
│   ├── trading_engine.py # Core engine (imports CircuitOpenError)
│   ├── ws_manager.py
│   └── server.py         # FastAPI app (initializes broker_resilience at startup)
└── frontend/
    └── src/
        ├── components/
        │   ├── ConfigModal.tsx
        │   └── tabs/
        │       ├── BrokersTab.tsx
        │       ├── WatchlistTab.tsx
        │       └── SettingsTab.tsx
        └── stores/
            └── useStore.ts
```

## Database Schema (MongoDB)

### tickers collection
- symbol, base_power, avg_days
- buy_offset, buy_percent, buy_order_type
- sell_offset, sell_percent, sell_order_type
- stop_offset, stop_percent, stop_order_type
- trailing_enabled, trailing_percent, trailing_percent_mode
- partial_fills_enabled, buy_legs, sell_legs
- opening_bell_enabled, opening_bell_trail_value, opening_bell_trail_is_percent
- halve_stop_at_open, lock_trailing_at_open
- auto_rebracket, rebracket_threshold, rebracket_spread, etc.
- broker_ids, broker_allocations

### trades collection
- symbol, side, price, quantity, reason, pnl, timestamp
- order_type, rule_mode, entry_price, target_price
- trail_high, trail_trigger, trail_value, trail_mode
- trading_mode, broker_results

### audit_logs collection
- timestamp, event_type, symbol, broker_id, success, error_message, details

### settings collection
- `engine_state`: running, paused, simulate_24_7, market_hours_only, live/paper auto modes
- `prefer_broker_feeds`: bool
- `brokers_resilience`: per-broker resilience config map

## API Endpoints

- `GET/POST /api/tickers` — Ticker management
- `PUT /api/tickers/{symbol}` — Update ticker config
- `POST /api/positions/{symbol}/sell` — Manual position sell
- `GET /api/positions/pending-sells` — Pending limit sells
- `DELETE /api/positions/pending-sells/{symbol}` — Cancel pending sell
- `GET /api/health` — System health check
- `GET /api/audit-logs` — Audit log query
- `GET/POST /api/rate-limits/{broker_id}` — Resilience config (rate limits + circuit breakers)
- `POST /api/circuit/{broker_id}/reset` — Manually reset circuit breaker
- `GET/POST /api/price-sources` — Price feed toggle (broker feeds vs yfinance)
- `WS /api/ws` — Real-time updates

## Backlog

### P1 (High Priority)
- [ ] Broker Health Dashboard panel (live connection status, latency, circuit state per broker)
- [ ] Alpaca/IBKR WebSocket live price feeds (bypass yfinance)
- [ ] Promotional landing page for Sentinel Pulse beta

### P2 (Medium Priority)
- [ ] "Sell All Positions" emergency liquidation button
- [ ] Volatility-adaptive brackets
- [ ] Multi-bracket laddering

### P3 (Low Priority)
- [ ] Real SMTP credentials for email delivery
- [ ] Prometheus + Grafana monitoring package
- [ ] Auto-bracket optimizer
- [ ] CSV export for trade history
- [ ] Multi-user authentication

## Known Issues
- Telegram uses test token (placeholder)
- Docker-based CI/CD has path issues (bypassed with non-Docker workflow)
