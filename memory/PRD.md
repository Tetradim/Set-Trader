# BracketBot Terminal - PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application. Clean up ghost code, dead JS files. Build a full bracket trading bot dashboard with per-stock toggle cards, buy/sell/trailing rules, live price feed, trade log, portfolio overview, Telegram integration, preset strategies, and CI/CD.

## Architecture
- **Backend**: FastAPI (Python 3.11) + Motor (async MongoDB) + WebSocket + yfinance + python-telegram-bot
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Radix UI + Lucide + Zustand + Framer Motion + @dnd-kit + Recharts
- **Database**: MongoDB 7
- **Infrastructure**: Docker Compose (dev + prod), GitHub Actions CI/CD, PyInstaller (Windows exe)

## What's Been Implemented

### Core
- [x] Full backend rewrite with trading engine, WebSocket, REST API, MongoDB
- [x] Ghost code cleanup, JSX -> TSX conversion
- [x] Dark theme dashboard, 5 tabs, ticker cards, preset strategies, command palette
- [x] Docker Compose, Makefile, GitHub Actions CI/CD, README

### Account & Capital Management
- [x] Master Account Balance (total capital, e.g. $100,000)
- [x] Per-ticker Buy Power allocation from Account Balance
- [x] Allocated / Available tracking in header (real-time)
- [x] Settings tab: Account Balance input with 3 summary cards
- [x] Cash Reserve from Take Profit actions
- [x] Compound Profits toggle per ticker

### Trading Features
- [x] Bracket orders (buy/sell offsets from moving average, % or $ mode)
- [x] Stop-loss and trailing stop (% or $ mode, MARKET or LIMIT order types)
- [x] Auto Rebracket with Threshold, Spread, Cooldown, Lookback Ticks, Buffer
- [x] Risk Controls: auto-stop on max daily loss or consecutive losses
- [x] Trade cooldown (30s per symbol)
- [x] Wait-1-day-before-selling toggle
- [x] Entry-price anchoring for percent-mode sells

### UI/UX
- [x] Drag-and-drop card reordering (persisted to MongoDB)
- [x] Double-click config modal with 4 tabs: Rules | Risk | Rebracket | Advanced
- [x] Live price chart (Recharts) embedded in ticker cards
- [x] Preset strategy toggle with backup/restore
- [x] Rich trade history: 6 stat cards, filter pills, expandable trade details
- [x] Loss log files: .txt per loss organized by date, viewable in Logs tab
- [x] Sidebar: order type badges, loss count, entry→target info

### Integrations
- [x] Telegram bot: /new, /cancel, /cancelall, /portfolio, /history, /help
- [x] Telegram alerts for trades, restarts, auto-stops

### Packaging
- [x] PyInstaller Windows executable
- [x] GitHub Actions build workflow
- [x] Desktop mode (IS_DESKTOP_MODE)

### Documentation
- [x] README with full Account Balance explanation, architecture, API reference, config guide

## Prioritized Backlog
### P1
- Alpaca paper trading API integration
- Confirmation dialogs for high-risk actions

### P2
- Input validation pass across all fields
- Prometheus + Grafana monitoring

### P3
- Authentication system
- Multi-broker support
- CSV export
- OpenTelemetry tracing

## Next Tasks
1. Confirmation dialogs for high-risk actions (delete ticker with position, stop bot)
2. Input validation pass
3. Alpaca paper trading API integration
