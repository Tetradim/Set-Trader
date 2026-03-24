# Sentinel Pulse - Product Requirements Document

## Original Problem Statement
Build a sophisticated trading bot with bracket-based trading rules, multi-broker support, and advanced risk management features.

## Core Features Implemented

### Trading Engine
- **Bracket Trading**: Buy/Sell/Stop rules based on moving average offsets (% or $)
- **Multi-Broker Support**: Alpaca, Robinhood, Interactive Brokers, TD Ameritrade, etc.
- **Paper/Live Trading Modes**: Simulated 24/7 trading and live broker execution
- **Partial Fills (Scale In/Out)**: Buy and sell in multiple legs at different price levels

### Time-Based Risk Management (NEW - March 2025)
- **Opening Bell Mode**: Force trailing stop during first 30 mins after market open
  - Separate trail value (% or $) from normal trailing stop
  - Tracks session high, sells if price drops by trail amount
  - Auto-rebrackets to new price level after 30 min window
- **Halve Stop Loss at Open**: Cuts stop-loss distance in half (0.5x) during opening volatility

### Position Management
- Manual position sell (market or limit orders)
- Pending limit sell tracking
- Trailing stop with customizable % or $ values
- Compound profits option

### Risk Controls
- Max daily loss limit
- Max consecutive losses limit
- Auto-stop with manual re-enable required

### Auto-Rebracket
- Threshold-based bracket adjustment
- Cooldown period
- Lookback period for recent low detection

### Notifications
- Telegram bot integration for alerts
- Trade notifications with detailed metadata

## Architecture

```
/app
├── backend/
│   ├── brokers/          # Broker adapters
│   ├── routes/           # API routes
│   ├── broker_manager.py
│   ├── deps.py           # Shared state
│   ├── email_service.py
│   ├── price_service.py
│   ├── schemas.py        # Pydantic models
│   ├── strategies.py
│   ├── telegram_service.py
│   ├── trading_engine.py # Core engine
│   ├── ws_manager.py
│   └── server.py         # FastAPI app
└── frontend/
    └── src/
        ├── components/
        │   ├── ConfigModal.tsx
        │   └── tabs/
        └── stores/
            └── useStore.ts
```

## Database Schema (MongoDB)

### tickers collection
- symbol, base_power, avg_days
- buy_offset, buy_percent, buy_order_type
- sell_offset, sell_percent, sell_order_type
- stop_offset, stop_percent, stop_order_type
- trailing_enabled, trailing_percent, trailing_percent_mode
- partial_fills_enabled, buy_legs, sell_legs
- opening_bell_enabled, opening_bell_trail_value, opening_bell_trail_is_percent
- halve_stop_at_open, lock_trailing_at_open
- auto_rebracket, rebracket_threshold, rebracket_spread, etc.
- broker_ids, broker_allocations

### trades collection
- symbol, side, price, quantity, reason, pnl, timestamp
- order_type, rule_mode, entry_price, target_price
- trail_high, trail_trigger, trail_value, trail_mode
- trading_mode, broker_results

## API Endpoints

- `GET/POST /api/tickers` - Ticker management
- `PUT /api/tickers/{symbol}` - Update ticker config
- `POST /api/positions/{symbol}/sell` - Manual position sell
- `GET /api/positions/pending-sells` - Pending limit sells
- `DELETE /api/positions/pending-sells/{symbol}` - Cancel pending sell
- `GET /api/health` - System health check
- `WS /api/ws` - Real-time updates

## Backlog

### P1 (High Priority)
- [ ] Promotional landing page for beta testing
- [ ] Broker Health Dashboard panel (connection status, latency, fill rates)

### P2 (Medium Priority)
- [ ] "Sell All Positions" emergency liquidation button
- [ ] Volatility-adaptive brackets
- [ ] Multi-bracket laddering

### P3 (Low Priority)
- [ ] Real SMTP credentials for email delivery
- [ ] Prometheus + Grafana monitoring package
- [ ] Auto-bracket optimizer
- [ ] CSV export for trade history
- [ ] Multi-user authentication

## Known Issues
- Telegram uses test token (placeholder)
- Docker-based CI/CD has path issues (bypassed with non-Docker workflow)
