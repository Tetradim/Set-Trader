# Sentinel Pulse — PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application with bracket trading, real-time price feeds, Telegram integration, and Windows executable distribution. Expand to support beta tester onboarding, Prometheus monitoring, multi-broker live trading, feedback system, email notifications, and distributed tracing.

## Architecture
- **Backend**: FastAPI + Motor (async MongoDB) + WebSocket + yfinance + python-telegram-bot + OpenTelemetry
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Radix UI + Zustand + @dnd-kit + Recharts
- **Database**: MongoDB 7
- **Broker Layer**: 10-broker adapter architecture (`/app/backend/brokers/`) with aiohttp session pooling
- **Email**: SMTP service (`/app/backend/email_service.py`) with rate limiting (2/hr)
- **Tracing**: OpenTelemetry (`/app/backend/telemetry.py`) with in-memory span store + optional OTLP export

## What's Been Implemented

### Core Trading Engine
- [x] Bracket orders, stop-loss, trailing stop, auto rebracket
- [x] Risk controls, compound profits, trade cooldown
- [x] Master Account Balance with allocation tracking

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

### Monitoring & Tracing
- [x] Prometheus /api/metrics (15+ metric types)
- [x] OpenTelemetry auto-instrumentation + custom spans
- [x] Frontend Traces tab

### Feedback & Email
- [x] Feedback dialog (bug, error, suggestion, complaint) with email via SMTP
- [x] Rate limiting: 2 emails/hour
- [x] Beta registration with email notification

## Prioritized Backlog

### P1
- Wire broker adapters into the trading engine (replace yfinance with live broker orders)
- Configure SMTP credentials for email delivery
- Prometheus+Grafana monitoring package

### P2
- Auto-bracket optimizer (backtest + volatility-adaptive)
- CSV trade history export

### P3
- Multi-user authentication
- Fix Docker CI/CD workflow
