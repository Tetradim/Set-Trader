# Sentinel Pulse — PRD

## Original Problem Statement
Convert a Streamlit/JS trading bot into a production-grade WebSocket/Zustand FastAPI+React+MongoDB application with bracket trading, real-time price feeds, Telegram integration, and Windows executable distribution. Expand to support beta tester onboarding, Prometheus monitoring, multi-broker live trading, feedback system, email notifications, and distributed tracing.

## Architecture (Post-Refactoring — March 2026)

```
/app/backend/
├── server.py              # 198 lines — Slim orchestrator (lifespan, middleware, router mounting)
├── deps.py                # 48 lines — Shared state container (db, engine, ws_manager, etc.)
├── schemas.py             # 174 lines — All Pydantic models
├── ws_manager.py          # 25 lines — WebSocket ConnectionManager
├── price_service.py       # 78 lines — yfinance caching + drift simulation
├── trading_engine.py      # 478 lines — Core trading logic, evaluate_ticker, auto-rebracket
├── telegram_service.py    # 283 lines — Telegram bot lifecycle, commands, alerts
├── broker_manager.py      # 213 lines — Credential storage, connection pooling, parallel orders
├── strategies.py          # 23 lines — Preset trading strategies
├── email_service.py       # Existing — SMTP service with rate limiting
├── telemetry.py           # Existing — OpenTelemetry setup
├── routes/
│   ├── health.py          # 187 lines — health, traces, metrics, beta, feedback
│   ├── brokers.py         # 152 lines — broker CRUD, test, connect, status
│   ├── tickers.py         # 168 lines — ticker CRUD, strategies, take-profit, cash-reserve
│   ├── trades.py          # 89 lines — trades, portfolio, positions, loss-logs
│   ├── bot.py             # 92 lines — bot control, settings, telegram test
│   └── ws.py              # 187 lines — WebSocket endpoint + real-time handlers
└── brokers/               # 10 broker adapter files
    ├── base.py, registry.py
    └── [adapter_name].py
```

**Key design pattern**: `deps.py` holds all shared singletons (db, engine, ws_manager, etc.). Modules import `deps` — never each other. This eliminates circular imports.

## What's Been Implemented

### Core Trading Engine
- [x] Bracket orders, stop-loss, trailing stop, auto rebracket
- [x] Risk controls, compound profits, trade cooldown
- [x] Master Account Balance with allocation tracking

### Live & Paper Trading (March 2026)
- [x] Unified simulation toggle (simulate_24_7):
  - ON = Paper mode (market always open, no live orders)
  - OFF = Live mode (real market hours, orders routed to brokers)
- [x] BrokerConnectionManager: encrypted credentials, parallel order placement
- [x] Broker failure handling: skip + Telegram alert + BROKER_FAILED WebSocket event
- [x] Flashing red broker chips on failure
- [x] Telegram `/reconnect_brokers` command
- [x] Trade records include `trading_mode` (paper/live) and `broker_results`

### Multi-Broker Support
- [x] 10 broker adapters (9 live-ready + Fidelity placeholder)
- [x] Multi-broker per ticker with per-broker buy power allocations
- [x] Full credential validation pipeline

### Monitoring & Tracing
- [x] Prometheus /api/metrics (15+ metric types)
- [x] OpenTelemetry auto-instrumentation + custom spans
- [x] Frontend Traces tab

### Refactoring (March 2026)
- [x] Decomposed monolithic server.py (2308 lines) into 12+ focused modules
- [x] 100% regression tested — all 17 API endpoints verified, all frontend features working

## Prioritized Backlog

### P1
- Configure real SMTP credentials for email delivery
- Prometheus + Grafana monitoring package

### P2
- Auto-bracket optimizer (backtest + volatility-adaptive)
- CSV trade history export

### P3
- Multi-user authentication
- Fix Docker CI/CD workflow
