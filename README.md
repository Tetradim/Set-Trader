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

### Trading Engine
| Feature                  | Description                                                          |
|--------------------------|----------------------------------------------------------------------|
| Bracket Orders           | Auto buy/sell at configurable offsets from moving average             |
| Trailing Stop            | Dynamic stop-loss that tracks price highs                            |
| Partial Shares           | Buys fractional shares based on allocation                           |
| Stop-Loss                | Hard stop at configurable percentage/dollar amount                   |
| Preset Strategies        | Conservative 1Y, Aggressive Monthly, Swing Trader                   |
| Market Hours Check       | Respects NYSE hours (9:30-4:00 ET), with 24/7 simulation toggle     |
| Per-Ticker P&L           | Individual profit tracking per symbol for compounding                |

### Dashboard UI
| Tab / Section            | What it shows                                                        |
|--------------------------|----------------------------------------------------------------------|
| **Watchlist**            | Ticker card grid with live prices, P&L, expandable config            |
| **Positions**            | Open positions with unrealized P&L, market value                     |
| **History**              | Full trade log with win rate statistics                              |
| **Logs**                 | In-app log viewer with level filtering                               |
| **Settings**             | Telegram bot token + chat ID management                              |
| **Activity Sidebar**     | Real-time trade feed with color-coded entries                        |
| **Command Palette**      | `Ctrl+K` quick actions and navigation                                |

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

Each ticker supports:
- **Buy Offset**: Price below average to trigger buy (% or $)
- **Sell Offset**: Price above average to trigger sell (% or $)
- **Stop Offset**: Stop-loss threshold (% or $)
- **Trailing Stop**: Dynamic stop that follows price upward
- **Base Power**: Dollar allocation per trade
- **Average Period**: Days for moving average calculation (1-365)

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
| GET    | `/api/tickers`                     | List all tickers                |
| POST   | `/api/tickers`                     | Add new ticker                  |
| PUT    | `/api/tickers/{symbol}`            | Update ticker config            |
| DELETE | `/api/tickers/{symbol}`            | Remove ticker                   |
| POST   | `/api/tickers/{symbol}/strategy/{preset}` | Apply preset strategy  |
| GET    | `/api/strategies`                  | List preset strategies          |
| GET    | `/api/trades`                      | Trade history                   |
| GET    | `/api/portfolio`                   | Portfolio summary               |
| GET    | `/api/positions`                   | Open positions                  |
| GET    | `/api/logs`                        | Application logs                |
| POST   | `/api/bot/start`                   | Start trading engine            |
| POST   | `/api/bot/stop`                    | Stop trading engine             |
| POST   | `/api/bot/pause`                   | Toggle pause                    |
| GET    | `/api/settings`                    | Get settings                    |
| POST   | `/api/settings`                    | Update settings                 |

### WebSocket

Connect to `/api/ws` for real-time updates.

**Outgoing messages (server -> client):**
- `INITIAL_STATE` - Full state on connect
- `PRICE_UPDATE` - Prices every ~2 seconds
- `TRADE` - Trade execution notification
- `TICKER_ADDED/UPDATED/DELETED` - Ticker changes
- `BOT_STATUS` - Running/paused state

**Incoming messages (client -> server):**
- `ADD_TICKER`, `DELETE_TICKER`, `UPDATE_TICKER`
- `GLOBAL_PAUSE`, `START_BOT`, `STOP_BOT`
- `APPLY_STRATEGY`

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
|   +-- Dockerfile           # Dev container
|   +-- Dockerfile.prod      # Production container
|   +-- requirements.txt     # Python dependencies
|   +-- .env                 # Environment variables
+-- frontend/
|   +-- src/
|   |   +-- components/
|   |   |   +-- Dashboard.tsx      # Main layout
|   |   |   +-- Header.tsx         # Top bar with controls
|   |   |   +-- TickerCard.tsx     # Per-stock card
|   |   |   +-- CommandPalette.tsx # Ctrl+K palette
|   |   |   +-- AddTickerDialog.tsx
|   |   |   +-- TradeLogSidebar.tsx
|   |   |   +-- tabs/
|   |   |       +-- WatchlistTab.tsx
|   |   |       +-- PositionsTab.tsx
|   |   |       +-- HistoryTab.tsx
|   |   |       +-- LogsTab.tsx
|   |   |       +-- SettingsTab.tsx
|   |   +-- stores/useStore.ts     # Zustand state
|   |   +-- hooks/useWebSocket.ts  # WS connection
|   |   +-- lib/api.ts             # REST client
|   +-- vite.config.ts
|   +-- tailwind.config.js
|   +-- package.json
+-- docker-compose.yml        # Dev stack
+-- docker-compose.prod.yml   # Production stack
+-- Makefile                   # CLI shortcuts
+-- .github/workflows/main.yml # CI/CD
+-- .devcontainer/             # VS Code dev container
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
| Backend    | FastAPI, Python 3.11                                   |
| Database   | MongoDB 7 (Motor async driver)                         |
| Prices     | yfinance (free Yahoo Finance data)                     |
| Real-time  | WebSockets (native)                                    |
| Container  | Docker, Docker Compose                                 |
| CI/CD      | GitHub Actions, GHCR                                   |

---

## License

MIT

---

*Built with precision for traders who demand control.*
