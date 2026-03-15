# Bracket Bot Pro v3.0

Advanced trading dashboard with scheduling, risk management, alerts, and analytics.

## New Features in v3.0

### 🎯 Core Enhancements
| Feature | Description |
|---------|-------------|
| **Scheduled Trading** | Auto-place brackets at market open/close or custom times |
| **Price Alerts** | Get notified when prices cross thresholds |
| **Risk Management** | Daily loss limits, position limits, trade caps |
| **Performance Analytics** | Win rate, profit factor, cumulative P/L charts |
| **Market Hours Awareness** | Shows market status, time until open |
| **Multi-Strategy Support** | Bracket, market, trailing stop orders |
| **Ticker Tags & Filtering** | Organize tickers with tags, filter watchlist |
| **Export/Import** | CSV export for tickers and trade history |

### 🛡️ Risk Management
- **Max Daily Loss** - Auto-pause when limit reached
- **Max Position Size** - Prevent oversized trades  
- **Daily Trade Limit** - Cap number of trades per day
- **Max Positions** - Limit concurrent positions
- **Confirmation Threshold** - Require confirmation for large trades

### ⏰ Scheduling System
| Frequency | Description |
|-----------|-------------|
| `market_open` | Execute at 9:30 AM EST |
| `market_close` | Execute at 3:55 PM EST |
| `daily` | Execute at specified time |
| `once` | Execute once at specified time |

### 🔔 Alert Types
| Condition | Triggers When |
|-----------|---------------|
| `above` | Price >= target |
| `below` | Price <= target |
| `crosses_above` | Price crosses up through target |
| `crosses_below` | Price crosses down through target |

### 📉 Analytics Dashboard
- Total trades, wins, losses
- Win rate percentage
- Profit factor (gross profit / gross loss)
- Average win/loss amounts
- Best/worst trades
- 30-day cumulative P/L chart
- Per-symbol performance breakdown

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/status` | View tickers status |
| `/portfolio` | Account summary |
| `/risk` | Risk status |
| `/buy SYMBOL` | Place bracket |
| `/cancel SYMBOL` | Cancel symbol orders |
| `/cancelall` | Cancel all orders |
| `/alert SYMBOL above/below PRICE` | Create price alert |
| `/schedule SYMBOL market_open` | Create schedule |
| `/stop` | Pause bot |
| `/restart` | Resume bot |
| `/reset SYMBOL` | Reset P/L |

---

## Files Created

| File | Purpose |
|------|---------|
| `ticker_config.json` | Tickers, profits, tracked orders |
| `trades_history.json` | Trade history (max 1000) |
| `price_alerts.json` | Active/triggered alerts |
| `schedules.json` | Scheduled tasks |
| `risk_settings.json` | Risk management config |
| `analytics_data.json` | Performance metrics |
| `bot_dashboard.log` | Application logs |
| `pause.flag` | Pause state |

---

## Background Workers

The bot runs 3 background threads:

1. **Profit Monitor** (60s interval)
   - Checks tracked orders for closures
   - Auto-updates profits for compounding
   - Sends Telegram notifications

2. **Alert Monitor** (30s interval)
   - Checks prices against active alerts
   - Triggers notifications when conditions met

3. **Schedule Executor** (30s interval)
   - Checks for due schedules
   - Executes actions (place_bracket, cancel_orders)
   - Respects pause state

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements_bot_pro.txt

# Set environment variables (optional)
export ALPACA_API_KEY="your_key"
export ALPACA_SECRET_KEY="your_secret"
export TELEGRAM_TOKEN="your_bot_token"
export TELEGRAM_USER_ID="your_id"

# Run
streamlit run bot_dashboard_pro.py
```

---

## UI Tabs

1. **📊 Watchlist** - Main trading dashboard with filters
2. **📈 Positions** - Open positions with P/L
3. **🔔 Alerts** - Price alert management
4. **⏰ Schedules** - Scheduled task management
5. **📜 History** - Trade history with export
6. **📉 Analytics** - Performance metrics & charts
7. **⚙️ Settings** - Risk management & logs

---

## Differences from v2.0

| Feature | v2.0 | v3.0 |
|---------|------|------|
| Scheduling | ❌ | ✅ Market open/close/custom |
| Alerts | ❌ | ✅ Price alerts with conditions |
| Risk Management | ❌ | ✅ Full risk controls |
| Analytics | Basic | Advanced with charts |
| Market Hours | ❌ | ✅ Status + countdown |
| Ticker Tags | ❌ | ✅ Organize & filter |
| Export | ❌ | ✅ CSV export |
| Order Types | Bracket only | Bracket, Market, Trailing Stop |
| UI | 4 tabs | 7 tabs |
| Telegram | 12 commands | 15 commands |
