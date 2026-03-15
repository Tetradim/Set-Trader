# Enhanced Bracket Bot Dashboard v2.0

A powerful Streamlit-based trading dashboard for automated bracket orders via Alpaca API, with Telegram remote control and advanced profit tracking.

## What's New in v2.0

### Core Improvements

| Feature | Description |
|---------|-------------|
| **Automated Profit Tracking** | Background monitor detects closed trades and automatically updates profits for compounding |
| **Order Cancellation** | Cancel orders per-symbol or all orders at once (UI + Telegram) |
| **Proper Logging** | Full Python logging to file + console with timestamps and levels |
| **Input Validation** | All inputs validated with user-friendly error messages |
| **Config Schema Validation** | JSON schema validation prevents corrupted configs |
| **Trade History** | Persistent trade history with win rate statistics |

### New Features

| Feature | Description |
|---------|-------------|
| **Portfolio Overview** | Real-time equity, cash, buying power, and day P/L display |
| **Positions Tab** | View all open positions with P/L breakdown |
| **Trade History Tab** | Historical trades with statistics |
| **Logs Tab** | In-app log viewer with filtering |
| **Enhanced UI** | Tabs, expanders, metrics, custom styling |
| **More Telegram Commands** | `/cancel`, `/cancelall`, `/portfolio`, `/history`, `/help` |

---

## Installation

```bash
pip install -r requirements_bot.txt
```

## Running the Bot

```bash
streamlit run bot_dashboard_enhanced.py
```

---

## Configuration

### Environment Variables (Recommended)

```bash
export ALPACA_API_KEY="your_api_key"
export ALPACA_SECRET_KEY="your_secret_key"
export TELEGRAM_TOKEN="your_bot_token"
export TELEGRAM_USER_ID="your_user_id"
```

### Files Created

| File | Purpose |
|------|---------|
| `ticker_config.json` | Ticker configurations and profits |
| `trades_history.json` | Trade history records |
| `bot_dashboard.log` | Application logs |
| `pause.flag` | Pause state indicator |

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` or `/help` | Show all commands |
| `/status` | View all tickers with status |
| `/portfolio` | View portfolio summary |
| `/buy SYMBOL` | Place bracket order |
| `/cancel SYMBOL` | Cancel orders for symbol |
| `/cancelall` | Cancel ALL open orders |
| `/stop` | Pause the bot |
| `/restart` | Resume the bot |
| `/reset SYMBOL` | Reset profits for symbol |
| `/add SYMBOL ...` | Add/edit ticker config |
| `/history` | View recent trades |

### Add Ticker via Telegram

```
/add SYMBOL buy_power avg_days buy_offset buy_% sell_offset sell_%

Example:
/add AAPL 500 30 -3 true 5 true
```

---

## Input Validation Rules

| Field | Valid Range |
|-------|-------------|
| Symbol | 1-5 letters only |
| Buy Power | $1 - $1,000,000 |
| Avg Days | 1 - 365 |
| Buy Offset | -50 to +50 |
| Sell Offset | -50 to +100 |
| Stop Offset | -50 to +50 |
| Max Multiple | 1 - 100 |
| Max Dollar Cap | $0 - $10,000,000 |

---

## Automated Profit Tracking

The bot automatically monitors tracked orders in the background:

1. When you place a bracket order, it's added to `tracked_orders`
2. Background thread checks every 60 seconds for closed positions
3. When a position closes, profit is calculated and added to the ticker's profit pool
4. Trade is recorded in history for statistics

### Manual Profit Check

Click **"Check Closed Trades & Update Profits"** button to force an immediate check.

---

## Architecture

```
bot_dashboard_enhanced.py
├── Logging Setup
├── Constants & Enums
├── Config Schema (JSON Schema validation)
├── Input Validation Helpers
├── Config Persistence (load/save/repair)
├── Trade History Management
├── Trading Helpers
│   ├── get_avg_price()
│   ├── has_open_position()
│   ├── get_open_orders()
│   ├── cancel_orders()
│   ├── cancel_all_orders()
│   ├── calc_effective_power()
│   └── place_bracket()
├── Profit Monitoring (background thread)
├── Portfolio Analytics
├── Streamlit UI
│   ├── Sidebar (settings, add ticker)
│   ├── Portfolio Overview
│   ├── Tab 1: Watchlist
│   ├── Tab 2: Positions
│   ├── Tab 3: Trade History
│   ├── Tab 4: Logs
│   └── Global Actions
└── Telegram Bot (background thread)
```

---

## Error Handling

### API Errors
- All Alpaca API calls wrapped in try-except
- Specific error messages returned to user
- Errors logged with full stack trace

### Config Corruption
- JSON parse errors: config backed up, fresh config created
- Schema validation: invalid entries removed, defaults applied
- Missing fields: auto-filled with defaults

### Validation Errors
- Custom `ValidationError` class with user-friendly messages
- Input bounds checked before any operation
- Clear feedback on what's wrong and valid ranges

---

## Logging

Logs are written to `bot_dashboard.log` with format:
```
2024-01-15 10:30:45 | INFO     | BracketBot | Bracket placed for AAPL | Qty: 10 | Buy @ $180.50
```

### Log Levels
- **DEBUG**: Detailed operation info
- **INFO**: Normal operations (trades, config changes)
- **WARNING**: Non-critical issues (validation warnings)
- **ERROR**: Failed operations

---

## Best Practices

1. **Start with Paper Trading**: Always test strategies on paper first
2. **Set Conservative Stops**: Use stop offsets appropriate for volatility
3. **Monitor Logs**: Check logs tab regularly for issues
4. **Backup Config**: Copy `ticker_config.json` periodically
5. **Use Environment Variables**: Don't hardcode API keys

---

## Differences from v1.0

| Aspect | v1.0 | v2.0 |
|--------|------|------|
| Profit Tracking | Manual reset only | Auto-detect closed trades |
| Order Cancel | Not available | Per-symbol + all orders |
| Logging | st.error only | Full Python logging |
| Validation | Basic | Schema + range validation |
| Config Safety | None | Backup + repair corrupted |
| UI | Single page | Tabbed interface |
| Telegram | 7 commands | 12 commands |
| Trade History | None | Persistent with stats |
| Portfolio View | None | Full overview |

---

## License

MIT License - Use at your own risk. Trading involves financial risk.
