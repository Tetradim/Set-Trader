# BracketBot Terminal - PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application. Clean up ghost code, dead JS files. Build a full bracket trading bot dashboard with per-stock toggle cards, buy/sell/trailing rules, live price feed, trade log, portfolio overview, Telegram integration, preset strategies, and CI/CD.

## Architecture
- **Backend**: FastAPI (Python 3.11) + Motor (async MongoDB) + WebSocket + yfinance + python-telegram-bot
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Radix UI + Lucide + Zustand + Framer Motion
- **Database**: MongoDB 7
- **Infrastructure**: Docker Compose (dev + prod), GitHub Actions CI/CD, Makefile

## What's Been Implemented

### 2026-03-16 - MVP
- [x] Full backend rewrite with trading engine, WebSocket, REST API, MongoDB
- [x] Ghost code cleanup (15+ dead files removed), JSX -> TSX conversion
- [x] Dark theme dashboard, 5 tabs, ticker cards, preset strategies, command palette
- [x] Docker Compose, Makefile, GitHub Actions CI/CD, README

### 2026-03-16 - Positions Tab Fix
- [x] Fixed crash from missing fields in WebSocket position data + ErrorBoundary

### 2026-03-16 - Telegram Integration
- [x] Full TelegramService with /pause, /resume, /start, /stop, /status, /portfolio, /new, /cancel, /cancelall, /history, /help
- [x] Restart/offline alerts, trade execution alerts
- [x] Multi-user chat ID support, Settings UI with connection status + test alert

### 2026-03-16 - Take Profit + Offset Fix + Custom Steps
- [x] Take Profit button per ticker (confirms, zeros P&L, moves to cash reserve)
- [x] Cash Reserve tracking (ledger + total) shown in header when > 0
- [x] Buy/Stop Offset always negative: locked dash prefix, user types magnitude only
- [x] Custom stepper arrows replacing browser default spinners on all number inputs
- [x] Settings tab: separate Increase Step and Decrease Step inputs (e.g. +0.05 / -0.10)
- [x] Steps persist in MongoDB and sync via WebSocket
- [x] Testing: 49/49 backend, 95% frontend pass

### 2026-03-16 - Decimal Input Bug Fix (P0)
- [x] Fixed: Users could not type decimal points (.) in number inputs
- [x] Root cause: premature parseFloat() stripping trailing decimals
- [x] Implemented useDecimalInput hook with local string state, regex validation, parse on blur
- [x] Fixed OffsetInput (Buy/Sell/Stop), SteppedInput (Buy Power, Avg Period, Trail %), SettingsTab step inputs
- [x] All inputs now use type="text" + inputMode="decimal"
- [x] Testing: 7/7 decimal input tests passed (100%)

### 2026-03-16 - Trade Dedup + Condensed Display
- [x] Backend: Added 30-second per-symbol trade cooldown to prevent rapid-fire duplicate trades
- [x] Frontend Sidebar: Grouped consecutive same-symbol/side trades into expandable single lines (e.g., "B NVDA x9 $180.14")
- [x] Frontend History Tab: Collapsible grouped rows with count badge, avg price, total qty, net P&L
- [x] Testing: 10/10 backend tests, 90% frontend (WebSocket intermittent in test env)

### 2026-03-16 - Trailing Stop Percent/Dollar Mode
- [x] Added `trailing_percent_mode` field to ticker schema (backend + frontend)
- [x] Trailing stop now supports both percent (trail by X%) and dollar (trail by $X) modes
- [x] Min value 0.01 for both modes
- [x] Backend: `high - $value` for dollar mode, `high * (1 - %/100)` for percent mode
- [x] Frontend: "Use %" toggle + dynamic "Trail %" / "Trail $" label
- [x] Backward compatible: existing tickers default to percent mode

### 2026-03-16 - Live Price Chart + Preset Strategy Toggle
- [x] Live chart: checkbox next to ticker name toggles embedded Recharts LineChart
- [x] Card expands to col-span-2 when chart enabled, pushing other cards below
- [x] Chart shows rolling price history (~120 pts) + trailing stop dashed line (amber)
- [x] Price data accumulated from WebSocket PRICE_UPDATE in Zustand store
- [x] Preset strategy toggle: clicking active preset restores custom_backup from MongoDB
- [x] Custom config saved before applying preset, restored on deactivation
- [x] Testing: 8/8 backend + 100% frontend

## Prioritized Backlog
### P1
- Live broker connection (Alpaca paper trading)
- Confirmation dialogs for high-risk actions
### P2
- Prometheus + Grafana monitoring
- Live trailing stop chart per ticker
### P3
- Authentication system, multi-broker support, CSV export

## Next Tasks
1. Confirmation dialogs for high-risk/volatile stock actions
2. Live trailing stop chart using Recharts
3. Alpaca paper trading API integration
