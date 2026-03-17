# BracketBot Terminal - PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application with bracket trading, real-time price feeds, Telegram integration, and Windows executable distribution.

## Architecture
- **Backend**: FastAPI + Motor (async MongoDB) + WebSocket + yfinance + python-telegram-bot
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Radix UI + Zustand + @dnd-kit + Recharts
- **Database**: MongoDB 7
- **Distribution**: PyInstaller (Windows exe), GitHub Actions CI/CD, Docker Compose

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
- [x] Sidebar: order type badges, loss count, entry→target info

### Integrations & Distribution
- [x] Telegram bot commands and trade/restart alerts
- [x] Windows executable build: PowerShell script + GitHub Actions workflow
- [x] Desktop mode: FastAPI serves static frontend (API routes have priority)
- [x] SPA routing fix: static catch-all runs AFTER API router

### Documentation
- [x] README: Account Balance system, API reference, config guide
- [x] WINDOWS_BUILD.md: Build, distribution, and troubleshooting guide

## Prioritized Backlog
### P1
- Alpaca paper trading API integration
- Confirmation dialogs for high-risk actions

### P2
- Input validation pass
- Prometheus + Grafana monitoring

### P3
- Authentication, multi-broker, CSV export

## Next Tasks
1. Confirmation dialogs for high-risk actions
2. Input validation pass
3. Alpaca paper trading API integration
