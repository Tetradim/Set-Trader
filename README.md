# BracketBot Terminal

[![Build & Release](https://github.com/Tetradim/Bracket-Bot-Main/actions/workflows/main.yml/badge.svg)](https://github.com/Tetradim/Bracket-Bot-Main/actions)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](https://ghcr.io/tetradim/bracket-bot-main)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Automated bracket trading bot with a production-grade Radix/Lucide-powered dark-mode dashboard.**

Real-time price feeds, configurable buy/sell/trailing-stop rules per ticker, Telegram integration for remote control, and a complete portfolio tracking system.

![BracketBot Dashboard](https://via.placeholder.com/1200x600/0B0C10/6366f1?text=BracketBot+Terminal+Dashboard)

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
              +--------------+--------------+
              |              |              |
        +-----+----+  +-----+----+  +------+------+
        |  MongoDB  |  | yfinance |  |  Telegram   |
        | (Tickers, |  | (Live    |  |  Bot API    |
        |  Trades,  |  |  Prices) |  | (Commands)  |
        |  Config)  |  +----------+  +-------------+
        +-----------+
```

| Layer      | Tech Stack                                                        |
|------------|-------------------------------------------------------------------|
| Frontend   | React 18, TypeScript, Vite, Tailwind CSS, Radix UI, Lucide, Zustand, Framer Motion |
| Backend    | Python 3.11, FastAPI, WebSockets, Motor (async MongoDB)           |
| Data       | MongoDB 7, yfinance (free real-time stock data)                   |
| Infra      | Docker Compose, GitHub Actions CI/CD, Nginx (prod)               |

---

## Features

### Account Balance & Capital Management

BracketBot uses a three-tier capital management system that mirrors how real brokerage accounts work:

```
+-----------------------------------------------+
|          ACCOUNT BALANCE ($100,000)            |  <-- Your total trading capital
|                                                |      Set in Settings > Account Balance
+---+---+---+---+---+---+---+---+---+---+-------+
| SPY   | NVDA  | TSLA  | AAPL  | ... |  AVAIL  |
|$10,000|  $500 |$2,000 | $100  |     |$78,400  |
+---+---+---+---+---+---+---+---+---+---+-------+
  |         |        |       |              |
  |   ALLOCATED ($21,600)    |         AVAILABLE
  |   Sum of all ticker      |       Balance - Allocated
  |   Buy Power values       |       (unallocated capital)
  |                          |
  +------+-------------------+
         |
    CASH RESERVE ($2,315)  <-- Profits pulled via "Take Profit"
```

**How it works:**

| Concept | Where to set it | What it means |
|---------|----------------|---------------|
| **Account Balance** | Settings tab | Your total trading capital. Think of this as the amount in your brokerage account. The bot never moves real money — this is your reference number for allocation tracking. |
| **Buy Power** (per ticker) | Ticker config > Rules tab > Buy Power | The dollar amount allocated to a specific ticker. When the bot buys, it uses `Buy Power / Price` to determine share quantity. |
| **Allocated** | Header (auto-calculated) | The sum of all ticker Buy Power values. This is how much capital is assigned to tickers. |
| **Available** | Header (auto-calculated) | `Account Balance − Allocated`. This is your unallocated capital — the money sitting idle that you could assign to a new or existing ticker. Turns red if you over-allocate. |
| **Cash Reserve** | Header (auto-calculated) | Profits extracted via the "Take Profit" button. This is realized profit that has been pulled out of individual tickers. |

**Example flow:**

1. You set your **Account Balance** to `$100,000` in Settings.
2. You add SPY with **Buy Power** `$10,000`. The header shows: Allocated `$10,000` / Available `$90,000`.
3. You add TSLA with **Buy Power** `$2,000`. Allocated `$12,000` / Available `$88,000`.
4. SPY makes a $50 profit. Its P&L shows `+$50.00`.
5. If **Compound Profits** is ON: SPY's Buy Power grows to `$10,050` (the $50 is automatically reinvested).
6. You click **Take Profit** on SPY: the $50 moves to **Cash Reserve**. If compounding was on, SPY's Buy Power drops back to `$10,000`.
7. Cash Reserve now shows `$50.00`. This is your realized, extracted profit.

**Calculations at a glance:**

```
Allocated     = SUM(ticker.base_power for all tickers)
Available     = Account Balance − Allocated
Cash Reserve  = SUM(all Take Profit withdrawals)
Total P&L     = SUM(unrealized P&L across all tickers)
```

> **Note:** Account Balance is a tracking number you set manually. It does not auto-increment from profits — use "Take Profit" to explicitly move gains into Cash Reserve. If you want profits to stay in-play, enable **Compound Profits** on each ticker.

### Trading Engine
| Feature                  | Description                                                          |
|--------------------------|----------------------------------------------------------------------|
| Bracket Orders           | Auto buy/sell at configurable offsets from moving average             |
| Trailing Stop            | Dynamic stop-loss that tracks price highs (% or $ mode)              |
| Stop-Loss                | Hard stop at configurable percentage/dollar amount                   |
| Partial Shares           | Buys fractional shares based on allocation                           |
| Preset Strategies        | Conservative 1Y, Aggressive Monthly, Swing Trader (toggle on/off)   |
| Market Hours Check       | Respects NYSE hours (9:30-4:00 ET), with 24/7 simulation toggle     |
| Compound Profits         | Toggle to auto-reinvest sell profits into a ticker's buy power       |
| Auto Rebracket           | Resets bracket when price drifts, with cooldown/lookback/buffer      |
| Risk Controls            | Auto-stop trading on max daily loss or consecutive losses            |
| Order Types              | MARKET or LIMIT for each rule (buy, sell, stop, trailing)            |
| Trade Cooldown           | 30-second per-symbol cooldown to prevent rapid-fire trades           |
| Rich Trade Logging       | Every trade records: order type, rule mode, entry/target/fill price, buy power, P&L |
| Loss Log Files           | Each losing trade writes a detailed `.txt` file organized by date    |

### Dashboard UI
| Tab / Section            | What it shows                                                        |
|--------------------------|----------------------------------------------------------------------|
| **Watchlist**            | Drag-and-drop ticker card grid with live prices, P&L, quick stats    |
| **Positions**            | Open positions with unrealized P&L, market value                     |
| **History**              | Trade log with filters (All/Buys/Sells/Stops/Trail/Losses), expandable details, win rate stats |
| **Logs**                 | Loss trade log files by date + system log viewer with level filtering |
| **Settings**             | Account balance, arrow step sizes, Telegram bot config               |
| **Activity Sidebar**     | Real-time trade feed with order type badges, loss callouts           |
| **Command Palette**      | `Ctrl+K` quick actions and navigation                                |
| **Config Modal**         | Double-click any card → tabbed config (Rules / Risk / Rebracket / Advanced) |

### Telegram Commands
| Command                  | Action                                                               |
|--------------------------|----------------------------------------------------------------------|
| `/new SYMBOL POWER`      | Add a new ticker with specified buy power                            |
| `/cancel SYMBOL`         | Cancel all orders for a symbol                                       |
| `/cancelall`             | Cancel all open orders                                               |
| `/portfolio`             | View portfolio summary                                               |
| `/history`               | Recent trade history                                                 |
| `/help`                  | List all available commands                                          |

### Keyboard Shortcuts
| Shortcut                 | Action                                                               |
|--------------------------|----------------------------------------------------------------------|
| `Ctrl+K` / `Cmd+K`      | Open command palette                                                 |
| Arrow keys               | Navigate command palette                                             |
| `Enter`                  | Select command                                                       |
| `Esc`                    | Close modals/palette                                                 |

---

## Quick Start

### Docker Compose (Recommended)

```bash
git clone https://github.com/Tetradim/Bracket-Bot-Main.git
cd Bracket-Bot-Main
make up
```

Open [http://localhost:3000](http://localhost:3000)

### Manual Setup

**Backend:**
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Set environment variables
export MONGO_URL=mongodb://localhost:27017
export DB_NAME=bracket_bot
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

**Frontend:**
```bash
cd frontend
yarn install
echo "REACT_APP_BACKEND_URL=http://localhost:8001" > .env
yarn dev
```

---

## Makefile Commands

| Command              | Description                                    |
|----------------------|------------------------------------------------|
| `make up`            | Start all services (dev)                       |
| `make down`          | Stop and remove volumes                        |
| `make logs`          | Tail all service logs                          |
| `make prod`          | Start production stack                         |
| `make prod-down`     | Stop production stack                          |
| `make test`          | Run smoke tests                                |
| `make clean`         | Remove everything (containers, images, volumes)|
| `make restart-backend` | Restart backend only                         |
| `make restart-frontend`| Restart frontend only                        |
| `make mongo-shell`   | Open MongoDB shell                             |

---

## Configuration

### Environment Variables

**Backend (`backend/.env`)**
| Variable         | Required | Description                           |
|------------------|----------|---------------------------------------|
| `MONGO_URL`      | Yes      | MongoDB connection string             |
| `DB_NAME`        | Yes      | Database name                         |
| `ALPACA_KEY`     | No       | Alpaca API key (for live trading)     |
| `ALPACA_SECRET`  | No       | Alpaca API secret                     |

**Frontend (`frontend/.env`)**
| Variable                  | Required | Description                    |
|---------------------------|----------|--------------------------------|
| `REACT_APP_BACKEND_URL`   | Yes      | Backend API URL                |

### Ticker Card Configuration

Each ticker supports (configured via the tabbed config modal):

**Rules tab:**
- **Buy Offset**: Price below average to trigger buy (% or $)
- **Sell Offset**: Price above entry to trigger sell (% or $)
- **Order Types**: MARKET or LIMIT per rule (buy, sell, stop, trailing)
- **Buy Power**: Dollar allocation per ticker (drawn from Account Balance)
- **Average Period**: Days for moving average calculation (1-365)
- **Compound Profits**: Auto-reinvest sell profits into buy power
- **Wait 1 Day**: Delay selling until at least 1 day after buy

**Risk tab:**
- **Stop Offset**: Stop-loss threshold (% or $)
- **Trailing Stop**: Dynamic stop that follows price upward (% or $ mode)
- **Max Daily Loss**: Auto-disable ticker after exceeding $ loss in a day
- **Max Consecutive Losses**: Auto-disable ticker after N consecutive losing trades

**Rebracket tab:**
- **Threshold ($)**: How far price must drift from current bracket to trigger rebracket
- **Spread ($)**: Width of the new bracket
- **Cooldown (s)**: Minimum seconds between rebrackets (prevents rapid-fire on volatile tickers)
- **Lookback Ticks**: Number of recent price ticks to find the recent low
- **Buffer ($)**: Gap below recent low for the new buy target

**Advanced tab:**
- **Preset Strategies**: Toggle between Conservative 1Y, Aggressive Monthly, Swing Trader (with backup/restore of custom settings)

### Preset Strategies

| Strategy              | Avg Period | Buy | Sell | Stop | Trailing |
|-----------------------|-----------|-----|------|------|----------|
| Conservative 1Y       | 365 days  | -5% | +8%  | -10% | Off      |
| Aggressive Monthly    | 30 days   | -2% | +4%  | -5%  | 1.5%     |
| Swing Trader          | 14 days   | -1.5%| +3% | -3%  | 2.0%     |

---

## API Reference

### REST Endpoints

| Method | Endpoint                           | Description                     |
|--------|------------------------------------|---------------------------------|
| GET    | `/api/health`                      | System health check             |
| GET    | `/api/tickers`                     | List all tickers (sorted by sort_order) |
| POST   | `/api/tickers`                     | Add new ticker                  |
| PUT    | `/api/tickers/{symbol}`            | Update ticker config            |
| DELETE | `/api/tickers/{symbol}`            | Remove ticker                   |
| POST   | `/api/tickers/reorder`             | Reorder tickers `{order: ["SPY","NVDA",...]}` |
| POST   | `/api/tickers/{symbol}/apply-strategy` | Apply/toggle preset strategy |
| POST   | `/api/tickers/{symbol}/take-profit` | Move P&L to cash reserve       |
| POST   | `/api/tickers/{symbol}/reset-auto-stop` | Re-enable an auto-stopped ticker |
| GET    | `/api/trades`                      | Trade history (rich metadata)   |
| GET    | `/api/loss-logs`                   | List loss log dates and files   |
| GET    | `/api/loss-logs/{date}/{filename}` | View a specific loss log file   |
| GET    | `/api/portfolio`                   | Portfolio summary               |
| GET    | `/api/positions`                   | Open positions                  |
| GET    | `/api/logs`                        | Application logs with level filter |
| POST   | `/api/bot/start`                   | Start trading engine            |
| POST   | `/api/bot/stop`                    | Stop trading engine             |
| GET    | `/api/settings`                    | Get settings (incl. account_balance, allocated, available) |
| POST   | `/api/settings`                    | Update settings (telegram, steps, account_balance) |
| POST   | `/api/settings/telegram/test`      | Send a test Telegram message    |

### WebSocket

Connect to `/api/ws` for real-time updates.

**Outgoing messages (server -> client):**
- `INITIAL_STATE` - Full state on connect (tickers, prices, profits, account_balance, allocated, available)
- `PRICE_UPDATE` - Prices every ~2 seconds
- `TRADE` - Trade execution with full metadata (order_type, rule_mode, entry_price, targets, P&L)
- `TICKER_ADDED/UPDATED/DELETED` - Ticker changes
- `TICKERS_REORDERED` - After drag-and-drop reorder
- `ACCOUNT_UPDATE` - When account_balance changes (account_balance, allocated, available)
- `BOT_STATUS` - Running/paused state

**Incoming messages (client -> server):**
- `ADD_TICKER`, `DELETE_TICKER`, `UPDATE_TICKER`
- `START_BOT`, `STOP_BOT`
- `APPLY_STRATEGY`, `TAKE_PROFIT`

---

## Development

### VS Code Dev Container

The project includes a `.devcontainer/devcontainer.json` for instant setup:

1. Install the "Dev Containers" extension
2. Open the project folder
3. Click "Reopen in Container"
4. All services start automatically

### Project Structure

```
Bracket-Bot-Main/
+-- backend/
|   +-- server.py           # FastAPI app + trading engine
|   +-- trade_logs/         # Loss log .txt files organized by date
|   |   +-- losses/
|   |       +-- YYYY-MM-DD/
|   |           +-- SYMBOL_SIDE_TIME_ID.txt
|   +-- Dockerfile           # Dev container
|   +-- Dockerfile.prod      # Production container
|   +-- requirements.txt     # Python dependencies
|   +-- .env                 # Environment variables
+-- frontend/
|   +-- src/
|   |   +-- components/
|   |   |   +-- Dashboard.tsx          # Main layout
|   |   |   +-- Header.tsx             # Top bar (account balance, P&L, controls)
|   |   |   +-- TickerCard.tsx         # Compact card with drag handle + chart
|   |   |   +-- ConfigModal.tsx        # Tabbed config modal (double-click to open)
|   |   |   +-- CommandPalette.tsx     # Ctrl+K palette
|   |   |   +-- AddTickerDialog.tsx
|   |   |   +-- TradeLogSidebar.tsx    # Real-time trade feed
|   |   |   +-- ticker-card/
|   |   |   |   +-- ConfigWidgets.tsx  # Shared input components
|   |   |   +-- tabs/
|   |   |       +-- WatchlistTab.tsx   # Drag-and-drop card grid
|   |   |       +-- PositionsTab.tsx
|   |   |       +-- HistoryTab.tsx     # Trade history with filters
|   |   |       +-- LogsTab.tsx        # Loss logs + system logs
|   |   |       +-- SettingsTab.tsx    # Account balance + Telegram + steps
|   |   +-- stores/useStore.ts         # Zustand state
|   |   +-- hooks/useWebSocket.ts      # WS connection
|   |   +-- lib/api.ts                 # REST client
|   +-- vite.config.ts
|   +-- tailwind.config.js
|   +-- package.json
+-- docker-compose.yml        # Dev stack
+-- docker-compose.prod.yml   # Production stack
+-- Makefile                   # CLI shortcuts
+-- .github/workflows/
|   +-- ci.yml                 # CI pipeline
|   +-- build-windows.yml      # Windows executable build
+-- build_win.py               # PyInstaller build script
+-- pyinstaller.spec           # PyInstaller spec
+-- win_run.bat                # Windows launcher
```

---

## CI/CD Pipeline

The GitHub Actions workflow:

1. **Test** - Spins up Docker Compose, runs backend + frontend smoke tests
2. **Build** - Multi-platform Docker images (amd64 + arm64) on tag push
3. **Release** - Creates GitHub release with image references

Push a tag to trigger:
```bash
git tag v1.0.0 && git push origin v1.0.0
```

---

## Tech Stack

| Category   | Technology                                             |
|------------|--------------------------------------------------------|
| Frontend   | React 18, TypeScript 5, Vite 5                        |
| Styling    | Tailwind CSS 3, Radix UI primitives                   |
| Icons      | Lucide React                                           |
| State      | Zustand 4                                              |
| Animation  | Framer Motion 11                                       |
| Drag & Drop| @dnd-kit/core + @dnd-kit/sortable                     |
| Charts     | Recharts                                               |
| Backend    | FastAPI, Python 3.11                                   |
| Database   | MongoDB 7 (Motor async driver)                         |
| Prices     | yfinance (free Yahoo Finance data)                     |
| Real-time  | WebSockets (native)                                    |
| Alerts     | python-telegram-bot                                    |
| Packaging  | PyInstaller (standalone Windows .exe)                  |
| Container  | Docker, Docker Compose                                 |
| CI/CD      | GitHub Actions, GHCR                                   |

---

## License

MIT

---

*Built with precision for traders who demand control.*
