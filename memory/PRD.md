# BracketBot Terminal - PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application. Clean up ghost code, dead JS files. Build a full bracket trading bot dashboard with per-stock toggle cards, buy/sell/trailing rules, live price feed, trade log, portfolio overview, Telegram integration, preset strategies, and CI/CD.

## Architecture
- **Backend**: FastAPI (Python 3.11) + Motor (async MongoDB) + WebSocket + yfinance
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
- Telegram bot token placeholder for multi-user control
- Preset strategies (Conservative 1Y, Aggressive Monthly, Swing Trader)
- Docker Compose for dev and production
- CI/CD with GitHub Actions
- Comprehensive README with architecture diagram, API reference, tables

## What's Been Implemented (2026-03-16)
- [x] Full backend rewrite: server.py with trading engine, WebSocket, REST API, MongoDB
- [x] Ghost code cleanup: removed 15+ dead files (CRA config, old JS entry, desktop build, webpack plugins, duplicate components)
- [x] JSX -> TSX conversion for all components
- [x] Dark theme dashboard with blues/purples (Radix + Lucide + Framer Motion)
- [x] Zustand store with full state management
- [x] WebSocket hook with auto-reconnect
- [x] 5 tabs: Watchlist, Positions, History, Logs, Settings
- [x] Ticker cards with expandable buy/sell/trailing/stop config
- [x] Preset strategy system (3 presets)
- [x] Command palette (Ctrl+K)
- [x] Add/Delete ticker functionality
- [x] Start/Stop/Pause bot controls
- [x] Real stock prices via yfinance (TSLA, AAPL, NVDA seeded)
- [x] Trading engine with bracket buy/sell/trailing stop logic
- [x] Trade log sidebar with real-time updates
- [x] Portfolio overview with P&L, positions, win rate
- [x] Telegram settings page (token + chat IDs)
- [x] Docker Compose (dev + prod)
- [x] Makefile with 10+ commands
- [x] GitHub Actions CI/CD (test + build + release)
- [x] .devcontainer for VS Code
- [x] Comprehensive README.md
- [x] Testing: 28/28 backend tests passed, 95% frontend pass rate

## Prioritized Backlog

### P0 (Critical)
- None remaining for MVP

### P1 (High Priority)
- Telegram bot integration (actual bot polling, not just config storage)
- Live broker connection (Alpaca paper trading)
- Order cancellation via UI and Telegram commands

### P2 (Medium Priority)
- Prometheus + Grafana monitoring stack
- OpenTelemetry tracing for trade decisions
- Live trailing stop chart (per-ticker sparkline)
- Confirmation dialogs for high-risk actions (volatile stocks, high exposure)
- Restart Frontend button with confirmation popup

### P3 (Nice to Have)
- Resource limits monitoring dashboard
- Multiple broker API support (IBKR, Robinhood, etc.)
- Authentication/login system
- Dark/light theme toggle
- Mobile responsive improvements
- Export trade history to CSV
- Sharpe ratio and max drawdown calculations

## Next Tasks
1. Wire Telegram bot polling to actually send/receive messages
2. Add confirmation dialogs for high-risk events
3. Implement live trailing stop chart using Recharts
4. Add Prometheus metrics export endpoint
5. Test with Alpaca paper trading API
