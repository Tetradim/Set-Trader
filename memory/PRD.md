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
- [x] Settings tab: separate Increase Step and Decrease Step inputs
- [x] Steps persist in MongoDB and sync via WebSocket

### 2026-03-16 - Decimal Input Bug Fix (P0)
- [x] Fixed: Users could not type decimal points (.) in number inputs
- [x] Implemented useDecimalInput hook with local string state, regex validation, parse on blur

### 2026-03-16 - Trade Dedup + Condensed Display
- [x] Backend: Added 30-second per-symbol trade cooldown
- [x] Frontend Sidebar: Grouped consecutive same-symbol/side trades
- [x] Frontend History Tab: Collapsible grouped rows with count badge, avg price, total qty, net P&L

### 2026-03-16 - Trailing Stop Percent/Dollar Mode
- [x] Added trailing_percent_mode field to ticker schema
- [x] Backend: dollar mode = high - $value, percent mode = high * (1 - %/100)

### 2026-03-16 - Auto Rebracket Feature
- [x] Detects when price drifts beyond bracket by configurable threshold
- [x] Auto-sets new bracket using rolling recent low + configurable spread
- [x] Telegram notification on each rebracket

### 2026-03-16 - Compound Profits Toggle
- [x] When enabled, positive P&L from sells is added to the ticker's buy power

### 2026-03-16 - Windows Executable Packaging Workflow
- [x] PyInstaller + GitHub Actions workflow

### 2026-03-16 - Limit/Market Order Types + Wait-a-Day Toggle
- [x] Added LIMIT/MARKET toggle for each rule section: Buy, Sell, Stop Loss, Trailing Stop

### 2026-03-16 - Live Price Chart + Preset Strategy Toggle
- [x] Live chart: checkbox next to ticker name toggles embedded Recharts LineChart
- [x] Preset strategy toggle: clicking active preset restores custom_backup from MongoDB

### 2026-03-17 - Rich Trade Logging & Metadata
- [x] Expanded TradeRecord with 14 new metadata fields: order_type, rule_mode, entry_price, target_price, total_value, buy_power, avg_price, sell_target, stop_target, trail_high, trail_trigger, trail_value, trail_mode
- [x] All 4 trade types (BUY, SELL, STOP, TRAILING_STOP) now log full context
- [x] History tab redesigned: 6 stat cards, filter pills (All/Buys/Sells/Stops/Trail/Losses), expandable trade details with MKT/LMT + PERCENT/DOLLAR badges
- [x] Sidebar shows order type badges, loss count, entry→target info per trade
- [x] Backend logger outputs rich trade info: order type, mode, target, entry, value, power, P&L
- [x] Telegram alerts enriched with metadata

### 2026-03-17 - Loss Trade Log Files
- [x] Each losing trade generates a .txt file in /backend/trade_logs/losses/YYYY-MM-DD/
- [x] Files contain: Trade ID, Timestamp, Symbol, Side, Order Info, Prices, Position, Targets, P&L, % Change, Reason
- [x] Trailing stop losses include trail_high, trail_trigger, trail_value, trail_mode
- [x] API: GET /api/loss-logs (list dates/files), GET /api/loss-logs/{date}/{filename} (view content)
- [x] Frontend Logs tab: LossLogViewer with date folders, file list, inline text viewer

### 2026-03-17 - Auto Rebracket Custom Inputs for Volatile Tickers
- [x] Added 3 new configurable fields: rebracket_cooldown (seconds), rebracket_lookback (ticks), rebracket_buffer ($)
- [x] Cooldown prevents rapid-fire rebrackets on volatile stocks
- [x] Lookback controls how many recent price ticks to use for finding recent low
- [x] Buffer controls how far below recent low to place the new buy target
- [x] All fields in backend schema, API, frontend UI, and preset strategy backup/restore
- [x] Testing: 12/12 backend tests passed, 100% frontend verified

## Prioritized Backlog
### P1
- Live broker connection (Alpaca paper trading)
- Confirmation dialogs for high-risk actions
### P2
- Input validation pass across all fields
- Prometheus + Grafana monitoring
### P3
- Authentication system, multi-broker support, CSV export

## Next Tasks
1. Confirmation dialogs for high-risk/volatile stock actions
2. Input validation pass
3. Alpaca paper trading API integration
