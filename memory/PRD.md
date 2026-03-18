# Sentinel Pulse — PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application with bracket trading, real-time price feeds, Telegram integration, and Windows executable distribution. Expand to support beta tester onboarding, Prometheus monitoring, multi-broker live trading, feedback system, email notifications, and distributed tracing.

## Architecture
- **Backend**: FastAPI + Motor (async MongoDB) + WebSocket + yfinance + python-telegram-bot + OpenTelemetry
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Radix UI + Zustand + @dnd-kit + Recharts
- **Database**: MongoDB 7
- **Broker Layer**: 10-broker adapter architecture (`/app/backend/brokers/`) with aiohttp session pooling
- **Broker Manager**: `/app/backend/broker_manager.py` — manages credentials, connections, parallel order placement, failover
- **Email**: SMTP service (`/app/backend/email_service.py`) with rate limiting (2/hr)
- **Tracing**: OpenTelemetry (`/app/backend/telemetry.py`) with in-memory span store + optional OTLP export

## What's Been Implemented

### Core Trading Engine
- [x] Bracket orders, stop-loss, trailing stop, auto rebracket
- [x] Risk controls, compound profits, trade cooldown
- [x] Master Account Balance with allocation tracking
- [x] **Live/Paper Trading Mode** — unified toggle controls trading behavior

### Live & Paper Trading (March 2026)
- [x] **Paper Mode** (`simulate_24_7 = true`): Market always open, trades logged but NOT sent to brokers
- [x] **Live Mode** (`simulate_24_7 = false`): Real market hours, orders routed through connected broker adapters
- [x] **BrokerConnectionManager**: Credential storage (XOR-encrypted), connection pooling, parallel order placement
- [x] **Broker Failure Handling**: Failed brokers skipped, Telegram alerts sent, WebSocket BROKER_FAILED events broadcast
- [x] **Flashing broker chips**: Frontend animates failed broker chips with red pulse
- [x] **Telegram `/reconnect_brokers`**: Remote command to reconnect all brokers
- [x] Trade records include `trading_mode` (paper/live) and `broker_results` metadata

### Multi-Broker Live Trading (March 2026)
- [x] **BrokerAdapter** ABC with aiohttp session pooling, order validation
- [x] **10 brokers** with full adapter implementations:
  - Alpaca (official API, paper+live) — LOW risk
  - Interactive Brokers IBKR (TWS/Gateway REST) — LOW risk
  - TD Ameritrade / Schwab (OAuth REST) — MEDIUM risk
  - Tradier (REST API) — LOW risk
  - Robinhood (robin_stocks session auth) — HIGH risk
  - TradeStation (OAuth REST) — LOW risk
  - Thinkorswim / Schwab (OAuth REST) — MEDIUM risk
  - Webull (unofficial API) — HIGH risk
  - Wealthsimple (unofficial API) — HIGH risk
  - Fidelity (placeholder, no public API) — MEDIUM risk
- [x] Each adapter: check_connection(), get_account(), get_positions(), place_order(), cancel_order(), get_quote()
- [x] Full credential validation pipeline: required_fields → format_validation → live_connection → account_access
- [x] Frontend Brokers tab with colored accent strips, risk badges, test connection modal
- [x] Factory pattern: get_broker_adapter() returns correct adapter by broker_id

### Frontend
- [x] **Trading Mode indicator** in Header (PAPER/LIVE badge)
- [x] **Trading Mode indicator** in Watchlist (Paper Trading/Live Trading with icon)
- [x] **Trading Mode section** in Settings with toggle and detailed explanation
- [x] **Broker Allocations** per ticker in Settings
- [x] **Multi-broker chips** per ticker card with failure animation support

### Monitoring & Tracing
- [x] Prometheus /api/metrics (15+ metric types)
- [x] OpenTelemetry auto-instrumentation + custom spans
- [x] Frontend Traces tab

### Feedback & Email
- [x] Feedback dialog (bug, error, suggestion, complaint) with email via SMTP
- [x] Rate limiting: 2 emails/hour
- [x] Beta registration with email notification

### API Endpoints (New)
- [x] `GET /api/health` — includes `trading_mode`, `brokers_connected`
- [x] `GET /api/settings` — includes `simulate_24_7`, `trading_mode`
- [x] `GET /api/brokers/status` — live connection status for all brokers
- [x] `POST /api/brokers/reconnect` — reconnect all configured brokers
- [x] `POST /api/brokers/{broker_id}/connect` — connect with credentials

## Key DB Schema
- **`tickers`**: `broker_ids: List[str]`, `broker_allocations: Dict[str, float]`
- **`settings`**: `engine_state` (running, paused, simulate_24_7), `account_balance`, `telegram`
- **`trades`**: `trading_mode` (paper/live), `broker_results` (per-broker execution data)
- **`broker_credentials`**: Encrypted credential storage per broker

## Prioritized Backlog

### P0 (Completed)
- [x] Wire broker adapters into trading engine with live/paper mode
- [x] Broker failure handling (skip, alert, UI flash)
- [x] Unified simulation toggle with persistence
- [x] Telegram /reconnect_brokers command

### P1
- Configure SMTP credentials for email delivery
- Prometheus+Grafana monitoring package
- Refactor server.py (2200+ lines) into modules

### P2
- Auto-bracket optimizer (backtest + volatility-adaptive)
- CSV trade history export

### P3
- Multi-user authentication
- Fix Docker CI/CD workflow
