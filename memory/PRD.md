# BracketBot Terminal - PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application. Clean up ghost code, dead JS files. Build a full bracket trading bot dashboard with per-stock toggle cards, buy/sell/trailing rules, live price feed, trade log, portfolio overview, Telegram integration, preset strategies, and CI/CD.

## Architecture
- **Backend**: FastAPI (Python 3.11) + Motor (async MongoDB) + WebSocket + yfinance + python-telegram-bot
- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Radix UI + Lucide + Zustand + Framer Motion
- **Database**: MongoDB 7
- **Infrastructure**: Docker Compose (dev + prod), GitHub Actions CI/CD, Makefile

## User Personas
1. **Active Trader** - Monitors positions, adjusts bracket rules in real-time
2. **Algorithmic Trading Enthusiast** - Configures strategies, backtests with presets
3. **Multi-Account Manager** - Uses Telegram to control bot remotely across accounts

## Core Requirements (Static)
- Per-stock toggle cards with expandable configuration
- Buy/Sell/Stop-Loss/Trailing-Stop rules per ticker
- Live price feed (~2s updates) via yfinance (free)
- WebSocket real-time communication
- MongoDB persistence for tickers, trades, profits, settings
- Tabbed dashboard: Watchlist, Positions, History, Logs, Settings
- Command palette (Ctrl+K)
- Telegram bot with /pause command and restart/offline alerts
- Preset strategies (Conservative 1Y, Aggressive Monthly, Swing Trader)
- Docker Compose for dev and production
- CI/CD with GitHub Actions

## What's Been Implemented

### 2026-03-16 - MVP
- [x] Full backend rewrite: server.py with trading engine, WebSocket, REST API, MongoDB
- [x] Ghost code cleanup: removed 15+ dead files
- [x] Dark theme dashboard with blues/purples
- [x] 5 tabs: Watchlist, Positions, History, Logs, Settings
- [x] Ticker cards with expandable config
- [x] Preset strategy system, Command palette, Add/Delete ticker
- [x] Docker Compose, Makefile, GitHub Actions CI/CD, README

### 2026-03-16 - Positions Tab Fix
- [x] Fixed crash: added missing market_value/symbol fields in WebSocket position data
- [x] Added ErrorBoundary to prevent full-page crashes

### 2026-03-16 - Telegram Integration
- [x] Full TelegramService with python-telegram-bot polling
- [x] /pause command pauses ALL trading + broadcasts confirmation
- [x] /resume command resumes trading
- [x] Bot restart alert sent to all chat IDs on server startup
- [x] Bot offline alert sent before server shutdown
- [x] Trade execution alerts (BUY, SELL, STOP, TRAILING_STOP)
- [x] 11 Telegram commands: /pause, /resume, /start, /stop, /status, /portfolio, /new, /cancel, /cancelall, /history, /help
- [x] Multi-user support via multiple chat IDs
- [x] Settings UI with connection status, test alert button
- [x] Auto-reconnect on settings save
- [x] Testing: 34/34 backend, 14/14 frontend passed

## Prioritized Backlog

### P1 (High Priority)
- Live broker connection (Alpaca paper trading)
- Confirmation dialogs for high-risk actions

### P2 (Medium Priority)
- Prometheus + Grafana monitoring stack
- OpenTelemetry tracing for trade decisions
- Live trailing stop chart (per-ticker sparkline)

### P3 (Nice to Have)
- Authentication/login system
- Multiple broker API support
- Export trade history to CSV
- Sharpe ratio and max drawdown calculations

## Next Tasks
1. Add confirmation dialogs for high-risk events
2. Implement live trailing stop chart with Recharts
3. Add Prometheus metrics export endpoint
