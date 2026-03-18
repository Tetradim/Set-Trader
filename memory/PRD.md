# Sentinel Pulse — PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application with bracket trading, real-time price feeds, Telegram integration, and Windows executable distribution. Expand to support beta tester onboarding, Prometheus monitoring, and multi-broker live trading.

## Architecture
- **Backend**: FastAPI + Motor (async MongoDB) + WebSocket + yfinance + python-telegram-bot
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Radix UI + Zustand + @dnd-kit + Recharts
- **Database**: MongoDB 7
- **Distribution**: PyInstaller (Windows exe), GitHub Actions CI/CD, Docker Compose
- **Broker Layer**: Abstract adapter pattern (`/app/backend/brokers/`) supporting 6 brokers

## What's Been Implemented

### Core Trading Engine
- [x] Bracket orders (buy/sell offsets, % or $ mode, MARKET or LIMIT)
- [x] Stop-loss and trailing stop (% or $ mode)
- [x] Auto Rebracket with Threshold, Spread, Cooldown, Lookback, Buffer
- [x] Risk Controls: auto-stop on max daily loss or consecutive losses
- [x] Compound Profits toggle, Trade cooldown (30s), Wait-1-day toggle
- [x] Entry-price anchoring for percent-mode sells

### Account & Capital Management
- [x] Master Account Balance (total capital)
- [x] Per-ticker Buy Power allocation
- [x] Allocated / Available tracking (real-time, auto-updates on add/delete/change)
- [x] Over-allocation warning banner (red) when Available < 0
- [x] Low balance warning (amber) when Available < 10% of balance
- [x] Budget context in AddTickerDialog and ConfigModal Buy Power input
- [x] Cash Reserve from Take Profit actions

### UI/UX
- [x] Drag-and-drop card reordering (persisted to MongoDB)
- [x] Double-click config modal with 4 tabs: Rules | Risk | Rebracket | Advanced
- [x] Live price chart (Recharts) in ticker cards
- [x] Rich trade history: stat cards, filter pills, expandable details
- [x] Loss log files: .txt per loss by date, viewable in Logs tab
- [x] Sidebar: order type badges, loss count, entry->target info

### Beta Tester Onboarding (NEW - March 2026)
- [x] Mandatory registration modal on first launch (blocks app access)
- [x] Full legal agreement (Signal Forge Laboratory Beta Tester License Agreement v1.0)
- [x] Collects: name, email, phone, last 4 SSN, full address, jurisdiction
- [x] Form validation (required fields, SSN format, agreement acceptance)
- [x] Backend: /api/beta/status, /api/beta/register endpoints
- [x] Stored in MongoDB `beta_registrations` collection

### Prometheus Monitoring (NEW - March 2026)
- [x] GET /api/metrics endpoint in Prometheus text format
- [x] Metrics: engine status, market state, WebSocket clients
- [x] Metrics: account balance, allocated/available capital
- [x] Metrics: ticker count, per-ticker buy power
- [x] Metrics: trade counts (total, by side), per-ticker P&L, total P&L
- [x] Metrics: cash reserve, open positions, unrealized P&L

### Broker Integration Architecture (NEW - March 2026)
- [x] Abstract BrokerAdapter base class (connect, place_order, get_positions, etc.)
- [x] Broker registry with 6 brokers: Robinhood, Schwab, Webull, IBKR, Wealthsimple, Fidelity
- [x] Risk warnings per broker (LOW/MEDIUM/HIGH) with detailed messages
- [x] GET /api/brokers, GET /api/brokers/{id} endpoints
- [x] Frontend Brokers tab with color-coded risk badges, docs links, connect buttons

### Integrations & Distribution
- [x] Telegram bot commands and trade/restart alerts
- [x] Windows executable build: PowerShell script + GitHub Actions workflow
- [x] Desktop mode: FastAPI serves static frontend (API routes have priority)
- [x] SPA routing fix: static catch-all runs AFTER API router

### Documentation
- [x] README: Account Balance system, API reference, config guide
- [x] WINDOWS_BUILD.md: Build, distribution, and troubleshooting guide

## Prioritized Backlog

### P0
- None (current sprint complete)

### P1
- Implement live broker adapters (start with IBKR as lowest risk)
- Separate "Sentinel Pulse Monitor" downloadable package (Prometheus+Grafana)
- Full input validation pass on all configurable inputs

### P2
- Confirmation dialogs for high-risk actions (delete ticker with position, etc.)
- Broker authentication UI with credential storage
- CSV export for trade history

### P3
- OpenTelemetry distributed tracing
- Multi-user authentication
- Fix Docker-based CI/CD workflow (docker-compose.yml broken paths)

## Next Tasks
1. Implement IBKR adapter (first live broker)
2. Build Prometheus+Grafana monitoring package
3. Input validation pass
4. Confirmation dialogs for high-risk actions
