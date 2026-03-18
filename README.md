# Sentinel Pulse

**Automated bracket trading bot with multi-broker support, real-time price feeds, and a production-grade dark-mode dashboard.**

Trade the same ticker across multiple broker accounts simultaneously with independent buy power allocation per broker. Features bracket orders, trailing stops, auto-rebracket, risk controls, Telegram integration, OpenTelemetry distributed tracing, and Prometheus monitoring.

---

## Architecture

```
                    +------------------+
                    |   React + Vite   |
                    |   (Port 3000)    |
                    +--------+---------+
                             |
                    WebSocket + REST API
                             |
                    +--------+---------+
                    |  FastAPI Server  |
                    |   (Port 8001)    |
                    +--------+---------+
                             |
          +------------------+------------------+
          |          |           |               |
    +-----+----+ +--+------+ +-+--------+ +----+------+
    |  MongoDB  | | yfinance| | Telegram | |  Brokers  |
    | (Tickers, | | (Live   | | Bot API  | | (10 Live  |
    |  Trades,  | | Prices) | | (Alerts) | |  Adapters)|
    |  Config)  | +---------+ +----------+ +-----------+
    +-----------+
```

| Layer      | Tech Stack                                                         |
| ---------- | ------------------------------------------------------------------ |
| Frontend   | React 18, TypeScript, Vite, Tailwind CSS, Radix UI, Zustand, @dnd-kit, Recharts |
| Backend    | FastAPI, Motor (async MongoDB), WebSocket, yfinance, python-telegram-bot |
| Database   | MongoDB 7                                                          |
| Monitoring | OpenTelemetry (tracing), Prometheus-compatible /api/metrics         |
| Brokers    | 10-broker adapter layer with aiohttp session pooling               |
| Email      | SMTP service with rate limiting (2/hr)                             |
| Packaging  | PyInstaller (Windows .exe), GitHub Actions CI/CD                   |

---

## Features

### Multi-Broker Live Trading

Sentinel Pulse supports **10 brokers** through a unified adapter interface. Each ticker card can be assigned to **multiple brokers simultaneously**, allowing you to trade the same stock across different accounts with independent buy power allocation.

| Broker | Risk Level | API Type | Status |
| ------ | ---------- | -------- | ------ |
| Alpaca | LOW | Official REST + WebSocket | Available |
| Interactive Brokers (IBKR) | LOW | TWS/Gateway REST | Available |
| Tradier | LOW | Official REST | Available |
| TradeStation | LOW | OAuth REST | Available |
| TD Ameritrade (Schwab) | MEDIUM | OAuth REST | Available |
| Thinkorswim (Schwab) | MEDIUM | OAuth REST | Available |
| Fidelity | MEDIUM | No Public API | Placeholder |
| Robinhood | HIGH | Session Auth (robin_stocks) | Available |
| Webull | HIGH | Unofficial/Reverse-Engineered | Available |
| Wealthsimple Trade | HIGH | Unofficial REST | Available |

**Per-Broker Buy Power Allocation:**
Each ticker can have custom buy power distributed across brokers. For example, SPY can be configured with:
- $50 from Alpaca
- $70 from IBKR
- Total buy power on card: $120

Configure allocations in **Settings > Broker Allocations**. The card's total `base_power` automatically equals the sum of all broker allocations.

**Test Connection:**
Every broker has a full credential validation pipeline:
1. Required fields check
2. Format validation (e.g., IBKR gateway URL, Alpaca key length, Robinhood MFA format)
3. Live connection test
4. Account access verification (balance + buying power)

### Bracket Trading Engine

The core trading logic evaluates each ticker on a loop:

- **Buy Trigger:** When price drops to/below the buy target, a BUY order is placed
- **Sell Trigger:** When price rises to/above the sell target, a SELL order is placed
- **Dollar or Percent Mode:** Offsets can be set in absolute dollars or as a percentage of the average price
- **Order Types:** MARKET or LIMIT orders per side

**Configuration per ticker:**
- `buy_offset` / `sell_offset` — how far from average to set buy/sell targets
- `buy_percent` / `sell_percent` — toggle between dollar and percent mode
- `buy_order_type` / `sell_order_type` — MARKET or LIMIT
- `avg_days` — lookback period for average price calculation (1-365 days)

### Trailing Stop

When enabled, a trailing stop tracks the highest price after a buy and triggers a sell when the price drops by the configured amount.

- `trailing_percent` — the drop threshold ($ or %)
- Displays as a **TRAIL** badge on the ticker card

### Auto Rebracket

Automatically adjusts buy/sell brackets when the price drifts significantly from the current bracket range. Displays as a **REBRACKET** badge.

- `rebracket_threshold` — how far price must drift to trigger
- `rebracket_spread` — the new bracket width after rebracket
- `rebracket_cooldown` — minimum seconds between rebrackets (0-3600)
- `rebracket_lookback` — number of recent price ticks to analyze (2-100)
- `rebracket_buffer` — additional buffer around the new bracket

### Risk Controls

- **Max Daily Loss:** Auto-stops the ticker if cumulative daily loss exceeds this amount
- **Max Consecutive Losses:** Auto-stops after N consecutive losing trades
- **Auto-stopped** tickers show a **STOPPED** badge and won't trade until manually re-enabled

### Capital Management

**Master Account Balance:**
Set a total account balance in Settings. The system tracks:
- **Total Balance:** Your declared capital
- **Allocated:** Sum of all tickers' buy power
- **Available:** Total minus Allocated

**Warnings:**
- 🔴 **Over-allocation banner** when Available < 0 (allocated more than you have)
- 🟡 **Low balance warning** when Available < 10% of total

**Compound Profits:**
When enabled, realized profits from a sell are added back to the ticker's buy power, growing the position size over time. With multi-broker allocations, profits compound proportionally per broker.

### Take Profit (Multi-Broker Logic)

When Take Profit is triggered on a multi-broker ticker:
1. Each broker's position is sold independently through its own API
2. Realized gains return proportionally to each broker's allocation
3. With compounding ON, each broker's allocation grows by its share of the profit
4. Cash reserve receives the take-profit amount
5. Total buy power on the card = sum of all updated broker allocations

### Drag-and-Drop Watchlist

Ticker cards can be reordered by dragging. Order is persisted to MongoDB. Double-click any card to open the full configuration modal with tabs:
- **Rules** — Buy/sell offsets, order types, modes
- **Risk** — Stop-loss, max daily loss, consecutive loss limit
- **Rebracket** — Auto-rebracket settings
- **Advanced** — Compounding, wait-1-day, strategy

### Trade History & Logging

**Rich Trade History (History tab):**
- Stat cards: total trades, wins/losses, P&L summary
- Filter by ticker, side, date range
- Expandable detail rows showing full trade metadata

**Loss Log Files (Logs tab):**
- Every losing trade generates a detailed `.txt` log file
- Organized by date in `/trade_logs/losses/`
- Viewable directly in the UI

### Feedback & Bug Reports

A **Feedback** button in the header opens a dialog to submit:
- Bug Reports
- Error Logs (with paste area for stack traces)
- Suggestions
- Complaints

Each report auto-includes the registered user's name/email and the app version (`1.0.0-beta`). Reports are stored in MongoDB and emailed via SMTP (when configured). Rate limited to 2 emails/hour to prevent flooding.

### Telegram Integration

- Bot commands for remote status checks
- Trade alerts sent to configured chat IDs
- Restart notifications

Configure with your Telegram bot token and chat ID(s) in Settings.

### OpenTelemetry Distributed Tracing

Auto-instruments FastAPI HTTP requests and MongoDB queries. Custom spans on:
- `trade.execute` — full trade attributes (symbol, side, price, P&L, rule mode)
- `ticker.evaluate` — each evaluation cycle per ticker
- `ticker.rebracket` — rebracket events with old/new bracket details

**Traces tab** in the dashboard shows:
- Stat cards: Trade Executions, Ticker Evaluations, HTTP Requests
- Span list with name, kind, status, duration
- Expandable rows showing attributes and events
- Name filter and refresh

Optional OTLP export to Jaeger/Grafana Tempo via `OTEL_EXPORTER_OTLP_ENDPOINT` env var.

### Prometheus Metrics

`GET /api/metrics` returns Prometheus-scrapeable text format with 15+ metric types:
- Engine status, market state, WebSocket client count
- Account balance, allocated/available capital
- Ticker count, per-ticker buy power
- Trade counts (total, by side), per-ticker P&L, total P&L
- Cash reserve, open positions, unrealized P&L

### Beta Tester Onboarding

Mandatory registration modal (currently disabled) that collects:
- Full name, email, phone, last 4 SSN, complete address, jurisdiction
- Agreement to legal terms (anti-reverse engineering, copyright)
- Registration details emailed to admin via SMTP

### Windows Executable

Build a standalone `.exe` for distribution:
```powershell
.\build-windows.ps1
```
Uses PyInstaller. In desktop mode, FastAPI serves the built React app with API routes taking priority over static files.

---

## API Reference

### Core
| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET | `/api/health` | Engine status, connections |
| GET | `/api/tickers` | List all tickers |
| POST | `/api/tickers` | Add a new ticker |
| GET | `/api/trades` | Trade history |
| GET | `/api/metrics` | Prometheus metrics |
| GET | `/api/traces` | OpenTelemetry spans |

### Brokers
| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET | `/api/brokers` | List all brokers (ordered low→high risk) |
| GET | `/api/brokers/{id}` | Broker details |
| POST | `/api/brokers/{id}/test` | Full credential validation + connection test |

### Feedback & Beta
| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| POST | `/api/feedback` | Submit bug report/suggestion/complaint |
| GET | `/api/beta/status` | Check registration status |
| POST | `/api/beta/register` | Submit beta registration |

### Settings
| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET | `/api/settings` | Current settings |
| POST | `/api/settings` | Update settings |
| POST | `/api/tickers/reorder` | Update card sort order |

### Logs
| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| GET | `/api/logs/loss/dates` | Dates with loss logs |
| GET | `/api/logs/loss/files/{date}` | Loss log files for date |
| GET | `/api/logs/loss/file/{date}/{filename}` | View loss log content |

---

## Environment Variables

### Backend (`/backend/.env`)
| Variable | Description |
| -------- | ----------- |
| `MONGO_URL` | MongoDB connection string |
| `DB_NAME` | Database name |
| `SMTP_HOST` | SMTP server hostname |
| `SMTP_PORT` | SMTP port (default: 587) |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `SMTP_RECIPIENT` | Admin email for notifications |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (Optional) OTLP collector URL |
| `OTEL_CONSOLE_EXPORT` | (Optional) Set to "true" for console span export |

### Frontend (`/frontend/.env`)
| Variable | Description |
| -------- | ----------- |
| `REACT_APP_BACKEND_URL` | Backend API URL |

---

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001

# Frontend
cd frontend
yarn install
yarn dev
```

The dashboard opens at `http://localhost:3000`. WebSocket connects automatically.

---

## Database Collections

| Collection | Purpose |
| ---------- | ------- |
| `tickers` | Ticker configs (symbol, offsets, broker_ids, broker_allocations, sort_order) |
| `trades` | Complete trade history with metadata |
| `profits` | Per-ticker realized P&L |
| `positions` | Open positions |
| `settings` | Account balance, Telegram config, UI prefs |
| `feedback` | Bug reports, suggestions, complaints |
| `beta_registrations` | Beta tester registration data |
