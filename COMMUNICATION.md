# Sentinel Pulse - Communication Architecture

This document describes how Sentinel Pulse communicates with Sentinel Edge and external systems.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Sentinel Pulse (Port 8002)                       │
│  ┌─────────┐  ┌─────────────┐  ┌──────────┐  ┌─────────────────┐  │
│  │ Engine │  │ Signal API │  │  Web API │  │ Alert Webhook  │  │
│  └────┬───┘  └─────┬──────┘  └────┬────┘  └───────┬─────────┘  │
│       │            │               │               │            │           │
└───────┼────────────┼───────────────┼───────────────┼───────────┼─────────┘
        │            │               │               │            │
     ┌──▼───────────▼──┐   ┌────▼─────┐  ┌───▼──────────▼────┐
     │ MongoDB          │   │ Browser │  │ Edge/Alertmanager │
     └─────────────────┘   └─────────┘  └──────────────────┘
```

## Communication Files

### 1. alert_handler.py - Alertmanager Webhook Handler

**Location:** `backend/alert_handler.py`

**Purpose:** Receives Prometheus Alertmanager webhooks and executes ticker actions.

**Endpoint:** `POST /api/alerts/webhook`

**Alertmanager Payload:**
```json
{
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "EdgeVolatilitySurge",
        "symbol": "AAPL",
        "severity": "warning"
      },
      "annotations": {
        "summary": "Volatility surge detected on AAPL"
      }
    }
  ]
}
```

**Action Mapping:**

| Alert Name | Ticker Action | Description |
|-----------|--------------|-------------|
| EdgeVolatilitySurge | `enabled: false` | Pause ticker |
| EdgeORBBreakoutBull | `buy_offset -0.5` | Lower buy offset |
| EdgeORBBreakoutBear | `stop_offset +0.5` | Tighten stop |
| EdgeRSIOverbought | `buy_blocked: true` | Block new buys |
| EdgePatternHS | `enabled: false` | Pause ticker |

**Key Functions:**
- `receive_alert()` - Main webhook handler
- `dispatch_action()` - Execute ticker action in database

### 2. routes/edge.py - Edge API

**Location:** `backend/routes/edge.py`

**Purpose:** Bidirectional Edge ↔ Pulse communication.

**Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/edge/signals/{symbol}` | POST | Receive Edge signals |
| `/api/edge/metrics` | GET | Prometheus metrics |
| `/api/edge/tickers/{symbol}/decision` | POST | Buy/sell/stop decisions |
| `/api/edge/positions/{symbol}` | GET | Get position |
| `/api/edge/status` | GET | Edge API key and Mongo command-channel health |

All Edge API endpoints require the configured `edge_api_key`. Pulse accepts either `X-API-Key: <key>` or `Authorization: Bearer <key>` so Edge clients can use either shared-secret convention.

#### Signal Submission

Edge sends signals to Pulse:

```python
# Edge calls this:
POST /api/edge/signals/AAPL
{
  "action": "signal",
  "rsi": 65,
  "signal_type": "bullish",
  "orb_high": 150.25,
  "orb_low": 149.50,
  "pattern": "hs",
  "volatility": 0.25,
  "volume": 1500000
}

# Pulse responds:
{"status": "ok", "symbol": "AAPL", "action": "signal", "message": "signal cached"}
```

#### Signal Cache

Signals are cached in memory (`_signal_cache` dict) and exposed as Prometheus metrics:

```
GET /api/edge/metrics

# Returns:
sentinel_rsi{symbol="AAPL",direction="bullish"} 65
sentinel_orb_breakout{symbol="AAPL",direction="1"} 1
sentinel_volatility_24h{symbol="AAPL"} 0.25
sentinel_pattern_hs{symbol="AAPL"} 1
```

### Prometheus Alert Rules

**Edge Signals (sentinel_edge.yml)**

```yaml
groups:
  - name: sentinel_edge
    rules:
      # Volatility Surge
      - alert: EdgeVolatilitySurge
        expr: |
          (sentinel_volatility_24h > sentinel_volatility_10d_avg * 2.5)
          and (sentinel_volatility_24h > 0.5)
        for: 1m
        labels:
          alertname: EdgeVolatilitySurge
          severity: warning
      
      # RSI Overbought
      - alert: EdgeRSIOverbought
        expr: sentinel_rsi > 70
        for: 5m
        
      # ORB Bullish Breakout
      - alert: EdgeORBBreakoutBull
        expr: |
          (sentinel_orb_breakout == 1)
          and (sentinel_orb_direction == 1)
        for: 30s
```

**Pulse Engine (sentinel_pulse.yml)**

Engine health and risk alerts:

```yaml
groups:
  - name: sentinel_pulse_engine
    rules:
      - alert: PulseEngineDown
        expr: sentinel_pulse_up == 0
        for: 1m
        severity: critical
        
      - alert: PulseHighDrawdown
        expr: sentinel_pulse_total_pnl_usd < -500
        for: 10m
        severity: critical
        
      - alert: PulseDailyLossLimit
        expr: sentinel_pulse_daily_loss_usd > sentinel_pulse_account_balance_usd * 0.05
        for: 1m
        severity: critical
```

### 3. shared/mongo_client.py - Edge MongoDB Client

**Location:** `backend/shared/mongo_client.py`

**Purpose:** Pulse sends commands TO Edge via MongoDB.

**Environment Variables:**
- `EDGE_MONGO_URL` - Edge MongoDB connection string

Pulse startup does not require Sentinel Edge to be running. If the Edge MongoDB endpoint is unavailable at Pulse startup, Pulse logs the connection error, leaves the integration configured, and continues normal bot startup. Exponential retry backoff is only applied after Pulse has successfully connected to the Edge command channel at least once during the current process; this avoids turning a missing Edge process into a Pulse startup failure.

The retry attempt limit is controlled from Settings as `edge_retry_max_attempts` and defaults to `10`. A value of `0` disables retries after the first post-connection Edge failure.

**Commands Sent to Edge:**

| Command | Description |
|---------|-------------|
| ORDER_FILLED | Trade executed |
| POSITION_UPDATE | Position changed |
| ACCOUNT_UPDATE | Balance changed |
| PULSE_STATUS | Heartbeat with trading mode |
| BROKER_STATUS | Broker connection status |
| AUTO_STOP_TRIGGERED | Stop loss triggered |

```python
# Example: Send ORDER_FILLED to Edge
await edge_client.send_order_filled(OrderFilled(
    symbol="AAPL",
    side="BUY",
    quantity=100,
    price=150.25,
    ...
))
```

### 4. config.py - Environment Configuration

**Location:** `backend/config.py`

**Environments:**

| Environment | Description |
|-------------|-------------|
| development | Local dev (localhost MongoDB) |
| staging | Staging infrastructure |
| production | Production (both paper + live trading) |

**Default Settings (production):**
```python
debug: False           # No debug logging
log_level: WARNING    # Reduced noise
paper_trading: True   # Enabled for beta
live_trading: True    # Enabled for beta
```

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Pulse (desktop) | 8002 | Main application |
| Pulse (API) | 8000 | Standalone API |
| Edge | 8001 | Signal calculation |
| Prometheus | 9090 | Metrics + alerting |
| Alertmanager | 9093 | Alert routing |
| MongoDB | 27017 | Data store |

## Integration Flow

### Edge Signals → Alert Action

```
1. Edge calculates RSI, ORB, volatility, patterns
         │
         ▼
2. Edge POSTs to /api/edge/signals/{symbol}
         │
         ▼
3. Pulse caches signal in _signal_cache
         │
         ▼
4. Prometheus scrapes /api/edge/metrics (every 15s)
         │
         ▼
5. Prometheus evaluates rules/sentinel_edge.yml
         │
         ▼
6. Alert fires → Alertmanager receives
         │
         ▼
7. Alertmanager POSTs to /api/alerts/webhook
         │
         ▼
8. alert_handler.py executes ticker action
    (pause, adjust brackets, block buys)
```

### Prometheus Configuration

**File:** `rules/prometheus.yml`

```yaml
scrape_configs:
  # Pulse engine metrics
  - job_name: 'sentinel-pulse'
    static_configs:
      - targets: ['localhost:8002']
    metrics_path: '/api/health/metrics'
  
  # Edge signal metrics
  - job_name: 'sentinel-edge'
    static_configs:
      - targets: ['localhost:8002']
    metrics_path: '/api/edge/metrics'

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']

rule_files:
  - 'rules/sentinel_edge.yml'
  - 'rules/sentinel_pulse.yml'
```

### Alertmanager Configuration

**File:** `alertmanager.yml`

```yaml
route:
  receiver: 'pulse-api'
  group_by: ['alertname', 'symbol']

receivers:
  - name: 'pulse-api'
    webhook_configs:
      - url: 'http://localhost:8002/api/alerts/webhook'
        send_resolved: true
```

## Edge → Pulse Decision Flow

```
1. Edge analyzes market data → generates signal
         │
         ▼
2. Edge POSTs /api/edge/tickers/{symbol}/decision
    {"decision": "buy", "confidence": 0.9, "price": 150.00}
         │
         ▼
3. Pulse validates signal:
    - Checks position exists
    - Verifies market open
    - Checks capital available
         │
         ▼
4. Executes trade via broker API
         │
         ▼
5. Sends ORDER_FILLED to Edge via MongoDB
```

## Testing

### Test Signal Submission
```bash
curl -X POST http://localhost:8002/api/edge/signals/AAPL \
  -H "Content-Type: application/json" \
  -d '{
    "action": "signal",
    "rsi": 72,
    "signal_type": "bullish",
    "orb_high": 151.00,
    "orb_low": 150.25,
    "volatility": 0.28,
    "volume": 2500000
  }'
```

### Test Metrics Output
```bash
curl http://localhost:8002/api/edge/metrics
```

### Test Alert Webhook
```bash
curl -X POST http://localhost:8002/api/alerts/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "EdgeVolatilitySurge",
        "symbol": "TSLA",
        "severity": "warning"
      }
    }]
  }'
```

## Security

- API key validation via `edge_api_key` setting
- Rate limiting (60 req/min per IP)
- No hardcoded credentials
- JWT_SECRET randomly generated if not set
