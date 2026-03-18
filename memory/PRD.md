# Sentinel Pulse — PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application with bracket trading, real-time price feeds, Telegram integration, and Windows executable distribution. Expand to support beta tester onboarding, Prometheus monitoring, multi-broker live trading, feedback system, email notifications, and distributed tracing.

## Architecture
- **Backend**: FastAPI + Motor (async MongoDB) + WebSocket + yfinance + python-telegram-bot + OpenTelemetry
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Radix UI + Zustand + @dnd-kit + Recharts
- **Database**: MongoDB 7
- **Distribution**: PyInstaller (Windows exe), GitHub Actions CI/CD, Docker Compose
- **Broker Layer**: Abstract adapter pattern (`/app/backend/brokers/`) supporting 6 brokers
- **Email**: SMTP service (`/app/backend/email_service.py`) for registration + feedback notifications
- **Tracing**: OpenTelemetry (`/app/backend/telemetry.py`) with in-memory span store + optional OTLP export

## What's Been Implemented

### Core Trading Engine
- [x] Bracket orders (buy/sell offsets, % or $ mode, MARKET or LIMIT)
- [x] Stop-loss and trailing stop (% or $ mode)
- [x] Auto Rebracket with Threshold, Spread, Cooldown, Lookback, Buffer
- [x] Risk Controls: auto-stop on max daily loss or consecutive losses
- [x] Compound Profits toggle, Trade cooldown (30s), Wait-1-day toggle

### Account & Capital Management
- [x] Master Account Balance (total capital) with validation ($0 - $100M)
- [x] Per-ticker Buy Power allocation with clamped bounds
- [x] Over-allocation and low balance warnings

### UI/UX
- [x] Drag-and-drop card reordering
- [x] Double-click config modal with 4 tabs
- [x] Live price chart, rich trade history, loss log files

### Beta Tester Onboarding
- [x] Registration modal (DISABLED until further notice)
- [x] Registration details emailed via SMTP

### Feedback & Bug Report System
- [x] 4 report types with user identification and app version
- [x] Email rate limited to 2 per hour (flood prevention)

### Email Service
- [x] SMTP-based with rate limiting (2/hr)
- [x] Placeholder credentials (emails NOT sent until configured)

### Prometheus Monitoring
- [x] GET /api/metrics with 15+ metric types

### Broker Integration
- [x] 6 brokers with risk warnings, test connection (full credential validation)

### OpenTelemetry Distributed Tracing (March 2026)
- [x] Auto-instrumentation: FastAPI HTTP and MongoDB queries
- [x] Custom spans: trade.execute (with full trade attributes), ticker.evaluate, ticker.rebracket
- [x] In-memory span store (500 spans) for /api/traces endpoint
- [x] Optional OTLP export via OTEL_EXPORTER_OTLP_ENDPOINT env var
- [x] Frontend Traces tab with stat cards, name filter, expandable span details
- [x] Loss events annotated on trade spans

### Input Validation & Confirmation Dialogs (March 2026)
- [x] Backend: Numeric field clamping on UPDATE_TICKER (base_power, offsets, risk controls, rebracket params)
- [x] Backend: Account balance validation ($0 - $100M)
- [x] Frontend: Enhanced delete confirmation showing position details when open position exists
- [x] Frontend: AddTickerDialog validates symbol format, length, buy power range

## Prioritized Backlog

### P1
- Implement live broker adapters (start with IBKR)
- Configure SMTP credentials for email delivery
- Separate "Sentinel Pulse Monitor" downloadable package (Prometheus+Grafana)

### P2
- CSV export for trade history
- Broker authentication UI with credential storage

### P3
- Multi-user authentication
- Fix Docker CI/CD workflow

## Next Tasks
1. Configure SMTP credentials (user to provide)
2. Implement IBKR adapter (first live broker)
3. Build Prometheus+Grafana monitoring package
