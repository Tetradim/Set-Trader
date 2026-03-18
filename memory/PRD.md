# Sentinel Pulse — PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application with bracket trading, real-time price feeds, Telegram integration, and Windows executable distribution. Expand to support beta tester onboarding, Prometheus monitoring, multi-broker live trading, feedback system, email notifications, and distributed tracing.

## Architecture (Post-Refactoring — March 2026)

```
/app/backend/
├── server.py              # 198 lines — Slim orchestrator
├── deps.py                # 48 lines — Shared state container
├── schemas.py             # 174 lines — All Pydantic models
├── ws_manager.py          # 25 lines — WebSocket ConnectionManager
├── price_service.py       # 78 lines — yfinance + drift simulation
├── trading_engine.py      # ~580 lines — Core trading logic + manual sell
├── telegram_service.py    # 283 lines — Telegram bot lifecycle
├── broker_manager.py      # 213 lines — Credential storage, parallel orders
├── strategies.py          # 23 lines — Preset trading strategies
├── email_service.py       # Existing — SMTP service
├── telemetry.py           # Existing — OpenTelemetry setup
├── routes/
│   ├── health.py          # health, traces, metrics, beta, feedback
│   ├── brokers.py         # broker CRUD, test, connect, status
│   ├── tickers.py         # ticker CRUD, strategies, take-profit
│   ├── trades.py          # trades, portfolio, positions, manual sell, loss-logs
│   ├── bot.py             # bot control, settings, telegram test
│   └── ws.py              # WebSocket endpoint
└── brokers/               # 10 broker adapter files
```

## What's Been Implemented

### Core Trading Engine
- [x] Bracket orders, stop-loss, trailing stop, auto rebracket
- [x] Risk controls, compound profits, trade cooldown
- [x] Master Account Balance with allocation tracking

### Live & Paper Trading
- [x] Unified simulation toggle (simulate_24_7)
- [x] BrokerConnectionManager: encrypted credentials, parallel orders
- [x] Broker failure handling: skip + Telegram alert + BROKER_FAILED WebSocket
- [x] Flashing red broker chips on failure
- [x] Telegram `/reconnect_brokers` command

### Manual Position Sell (March 2026)
- [x] **Sell button** on each position row in the Positions tab
- [x] **Sell modal** with position details (qty, entry, current price, market value)
- [x] **Market sell**: Execute immediately at current market price
- [x] **Limit sell**: Place pending order, engine executes when price >= target
- [x] **Estimated P&L** updates dynamically based on order type and price
- [x] **Pending sells section** with cancel button
- [x] **PAPER/LIVE badge** in modal showing current trading mode
- [x] Backend: `POST /api/positions/{symbol}/sell`, `GET /api/positions/pending-sells`, `DELETE /api/positions/{symbol}/pending-sell`

### Refactoring (March 2026)
- [x] Decomposed 2308-line server.py into 12+ modules
- [x] deps.py shared state pattern eliminates circular imports

### Multi-Broker Support
- [x] 10 broker adapters (9 live-ready)
- [x] Multi-broker per ticker with per-broker allocations

### Monitoring & Tracing
- [x] Prometheus /api/metrics
- [x] OpenTelemetry auto-instrumentation

## Prioritized Backlog

### P1
- Configure real SMTP credentials
- Prometheus + Grafana monitoring package

### P2
- Auto-bracket optimizer
- CSV trade history export

### P3
- Multi-user authentication
- Fix Docker CI/CD workflow
