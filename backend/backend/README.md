# Bracket Bot

A modern, delightful trading bot for automated bracket orders.

**Press ⌘K to do everything.**

## Quick Start

```bash
# Clone and setup
cp .env.example .env
# Add your Alpaca API keys to .env

# One command to rule them all
docker compose up
```

Open [http://localhost:5173](http://localhost:5173)

## Philosophy

- **One truth**: You want to experiment with bracket strategies fast
- **Two enemies**: Context switching + configuration fatigue  
- **Three desires**: Beautiful UI, instant feedback, low mental overhead

## Features

### Command Palette (⌘K)
Everything is 2-3 keystrokes away:
- Add tickers
- Place brackets
- Cancel orders
- Apply strategy presets

### Real-time Updates
WebSocket pushes live data every 8 seconds:
- Current prices
- Position status
- Profit tracking
- Account balances

### Beautiful Cards
Animated ticker cards with:
- Price levels (buy/current/sell)
- Spread to buy percentage
- Profit tracking with glow effects
- One-click actions

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Vite + React 18 + TypeScript |
| UI | Tailwind CSS + shadcn/ui + Framer Motion |
| State | Zustand |
| Backend | FastAPI + WebSocket |
| Trading | Alpaca API |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/state` | Full app state |
| GET | `/tickers` | List all tickers |
| POST | `/tickers` | Add ticker |
| DELETE | `/tickers/{symbol}` | Remove ticker |
| POST | `/actions/place/{symbol}` | Place bracket |
| POST | `/actions/place-all` | Place all brackets |
| POST | `/actions/cancel-all` | Cancel all orders |
| POST | `/actions/pause` | Pause bot |
| POST | `/actions/resume` | Resume bot |
| WS | `/ws` | WebSocket live updates |

## Development

### Backend only
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend only
```bash
cd frontend
yarn install
yarn dev
```

### Both with Docker
```bash
docker compose up
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| ⌘K / Ctrl+K | Open command palette |
| Escape | Close dialogs |
| ↑↓ | Navigate commands |
| Enter | Select command |

## License

MIT - Trade at your own risk.
