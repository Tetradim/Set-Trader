# Sentinel Pulse — PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application with bracket trading, real-time price feeds, Telegram integration, and Windows executable distribution. Expand to support beta tester onboarding, Prometheus monitoring, multi-broker live trading, feedback system, and email notifications.

## Architecture
- **Backend**: FastAPI + Motor (async MongoDB) + WebSocket + yfinance + python-telegram-bot
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Radix UI + Zustand + @dnd-kit + Recharts
- **Database**: MongoDB 7
- **Distribution**: PyInstaller (Windows exe), GitHub Actions CI/CD, Docker Compose
- **Broker Layer**: Abstract adapter pattern (`/app/backend/brokers/`) supporting 6 brokers
- **Email**: SMTP service (`/app/backend/email_service.py`) for registration + feedback notifications

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
- [x] Allocated / Available tracking (real-time)
- [x] Over-allocation and low balance warnings
- [x] Cash Reserve from Take Profit actions

### UI/UX
- [x] Drag-and-drop card reordering (persisted to MongoDB)
- [x] Double-click config modal with 4 tabs: Rules | Risk | Rebracket | Advanced
- [x] Live price chart (Recharts) in ticker cards
- [x] Rich trade history with filters and expandable details
- [x] Loss log files viewable in Logs tab

### Beta Tester Onboarding (March 2026)
- [x] Mandatory registration modal (currently DISABLED until further notice)
- [x] Full legal agreement (Signal Forge Laboratory Beta Tester License Agreement v1.0)
- [x] Collects: name, email, phone, last 4 SSN, full address, jurisdiction
- [x] Registration details emailed via SMTP (when configured)

### Feedback & Bug Report System (March 2026)
- [x] Feedback dialog accessible from header bar
- [x] 4 report types: Bug Report, Error Log, Suggestion, Complaint
- [x] Includes user identification, app version, description, optional error log
- [x] Stored in MongoDB `feedback` collection
- [x] Emailed to admin via SMTP using registered user's email as sender/reply-to
- [x] POST /api/feedback endpoint

### Email Service (March 2026)
- [x] SMTP-based email service (/app/backend/email_service.py)
- [x] Sends registration details on beta sign-up
- [x] Sends feedback/bug reports with user ID and app version
- [x] Configured via env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_RECIPIENT
- [x] Currently using placeholder credentials (emails NOT sent until configured)

### Prometheus Monitoring (March 2026)
- [x] GET /api/metrics endpoint in Prometheus text format
- [x] 15+ metric types: engine status, account balance, per-ticker P&L, trade counts, positions

### Broker Integration Architecture (March 2026)
- [x] Abstract BrokerAdapter base class
- [x] Registry of 6 brokers: Robinhood, Schwab, Webull, IBKR, Wealthsimple, Fidelity
- [x] Risk warnings per broker (LOW/MEDIUM/HIGH)
- [x] GET /api/brokers, GET /api/brokers/{id} endpoints
- [x] Frontend Brokers tab with color-coded risk badges

### Broker Test Connection (March 2026)
- [x] POST /api/brokers/{id}/test - full credential validation dry-run
- [x] Validates: required fields present, credential format per broker, adapter availability
- [x] Per-broker format rules (IBKR port numeric, Robinhood MFA 6-digit, Schwab keys 8+ chars, etc.)
- [x] Live connection + account access tests (when adapters are implemented)
- [x] Frontend Test Connection modal with credential inputs and color-coded results

### Integrations & Distribution
- [x] Telegram bot commands and trade/restart alerts
- [x] Windows executable build: PowerShell script + GitHub Actions workflow
- [x] Desktop mode: FastAPI serves static frontend

## Prioritized Backlog

### P1
- Implement live broker adapters (start with IBKR)
- Configure SMTP credentials for email delivery
- Separate "Sentinel Pulse Monitor" downloadable package (Prometheus+Grafana)

### P2
- Full input validation pass
- Confirmation dialogs for high-risk actions
- CSV export for trade history

### P3
- OpenTelemetry distributed tracing
- Multi-user authentication
- Fix Docker CI/CD workflow

## Next Tasks
1. Configure SMTP credentials (user to provide)
2. Implement IBKR adapter (first live broker)
3. Build Prometheus+Grafana monitoring package
