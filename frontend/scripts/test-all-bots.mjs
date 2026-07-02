import { chromium } from 'playwright';
import { WebSocketServer } from 'ws';
import { execFile, spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import http from 'node:http';
import net from 'node:net';
import path from 'node:path';

const root = process.cwd();
const artifactDir = path.join(root, 'test-artifacts', 'all-bots');
const reportPath = path.join(artifactDir, 'all-bots-report.json');
const markdownPath = path.join(artifactDir, 'all-bots-report.md');

const tabIds = [
  'watchlist',
  'test-lab',
  'portfolio',
  'positions',
  'orders',
  'history',
  'preflight',
  'risk-center',
  'reconciliation',
  'compliance',
  'logs',
  'traces',
  'incidents',
  'slo',
  'analytics',
  'brokers',
  'foreign',
  'settings',
  'admin',
];

const tabGroups = {
  watchlist: 'trading',
  'test-lab': 'trading',
  portfolio: 'trading',
  positions: 'trading',
  orders: 'trading',
  history: 'trading',
  preflight: 'risk',
  'risk-center': 'risk',
  reconciliation: 'risk',
  compliance: 'risk',
  logs: 'monitoring',
  traces: 'monitoring',
  incidents: 'monitoring',
  slo: 'monitoring',
  analytics: 'monitoring',
  brokers: 'integrations',
  foreign: 'integrations',
  settings: 'settings',
  admin: 'settings',
};

function ticker(symbol, sortOrder, price) {
  return {
    id: symbol,
    symbol,
    base_power: 1000,
    avg_days: 7,
    buy_offset: 1,
    buy_percent: true,
    buy_order_type: 'MARKET',
    sell_offset: 2,
    sell_percent: true,
    sell_order_type: 'MARKET',
    stop_offset: 1.5,
    stop_percent: true,
    stop_order_type: 'MARKET',
    trailing_enabled: sortOrder === 1,
    trailing_percent: 1,
    trailing_percent_mode: true,
    trailing_order_type: 'MARKET',
    wait_day_after_buy: false,
    compound_profits: false,
    max_daily_loss: 500,
    max_consecutive_losses: 3,
    auto_stopped: false,
    auto_stop_reason: '',
    auto_rebracket: false,
    rebracket_threshold: 1,
    rebracket_spread: 1,
    rebracket_cooldown: 60,
    rebracket_lookback: 20,
    rebracket_buffer: 0.1,
    enabled: true,
    strategy: sortOrder === 2 ? 'macd_v' : 'rsi',
    broker_id: 'paper',
    broker_ids: ['paper', 'simulation'],
    broker_allocations: { paper: 700, simulation: 300 },
    sort_order: sortOrder,
    created_at: new Date().toISOString(),
    partial_fills_enabled: false,
    buy_legs: [],
    sell_legs: [],
    lock_trailing_at_open: false,
    halve_stop_at_open: false,
    opening_bell_enabled: false,
    opening_bell_trail_value: 0,
    opening_bell_trail_is_percent: false,
    market: 'US',
    strategy_config: {},
    _price: price,
  };
}

const state = {
  tickers: [
    ticker('AAPL', 0, 189.12),
    ticker('MSFT', 1, 421.55),
    ticker('TSLA', 2, 174.88),
  ],
  prices: { AAPL: 189.12, MSFT: 421.55, TSLA: 174.88 },
  profits: { AAPL: 42.2, MSFT: 18.4, TSLA: -9.8 },
  running: false,
  paused: false,
  simulate_24_7: true,
  market_hours_only: false,
  live_during_market_hours: false,
  paper_after_hours: true,
  currencyDisplay: 'usd',
  preferBrokerPrices: true,
};

const requests = [];
const unknownRoutes = [];

function json(response, payload, status = 200) {
  response.writeHead(status, { 'Content-Type': 'application/json' });
  response.end(JSON.stringify(payload));
}

function text(response, payload, status = 200, contentType = 'text/plain') {
  response.writeHead(status, { 'Content-Type': contentType });
  response.end(payload);
}

async function readBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf8');
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    return { raw };
  }
}

function snapshot() {
  return {
    tickers: state.tickers,
    prices: state.prices,
    price_sources: Object.fromEntries(state.tickers.map((item) => [item.symbol, 'mock'])),
    price_errors: {},
    positions: {
      AAPL: { symbol: 'AAPL', quantity: 4, avg_entry: 184.25, current_price: state.prices.AAPL, market_value: 756.48, unrealized_pnl: 19.48 },
      MSFT: { symbol: 'MSFT', quantity: 2, avg_entry: 412.1, current_price: state.prices.MSFT, market_value: 843.1, unrealized_pnl: 18.9 },
    },
    profits: state.profits,
    trades: sampleTrades(),
    cash_reserve: 250,
    account_balance: 25000,
    allocated: 3000,
    available: 22000,
    increment_step: 0.5,
    decrement_step: 0.5,
    paused: state.paused,
    running: state.running,
    market_open: true,
    simulate_24_7: state.simulate_24_7,
    market_hours_only: state.market_hours_only,
    live_during_market_hours: state.live_during_market_hours,
    paper_after_hours: state.paper_after_hours,
    replay: { active: false, session_id: null },
  };
}

function sampleTrades() {
  return [
    {
      id: 'trade-1',
      symbol: 'AAPL',
      side: 'BUY',
      price: 184.25,
      quantity: 4,
      reason: 'Paper fill from exhaustive bot test',
      pnl: 0,
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      order_type: 'MARKET',
      rule_mode: 'PERCENT',
      entry_price: 184.25,
      target_price: 188,
      total_value: 737,
      buy_power: 1000,
      avg_price: 185,
      sell_target: 2,
      stop_target: 1.5,
      trail_high: 190,
      trail_trigger: 188,
      trail_value: 1,
      trail_mode: 'PERCENT',
      trading_mode: state.simulate_24_7 ? 'paper' : 'live',
      broker_results: [{ broker_id: 'paper', status: 'filled' }],
    },
  ];
}

function brokerList() {
  return [
    {
      id: 'paper',
      name: 'Paper Engine',
      description: 'Pulse paper-trading execution adapter for safe tests.',
      supported: true,
      readiness: 'production',
      readiness_note: 'Mocked for exhaustive automation.',
      auth_fields: ['api_key', 'api_secret'],
      docs_url: 'about:blank',
      color: '#22c55e',
      risk_warning: null,
    },
    {
      id: 'simulation',
      name: 'Separate Bot Engine',
      description: 'Separate Sentinel Archive used to compare bot behavior.',
      supported: true,
      readiness: 'beta',
      readiness_note: 'Runs without live broker access in this test.',
      auth_fields: ['api_key'],
      docs_url: 'about:blank',
      color: '#38bdf8',
      risk_warning: null,
    },
    {
      id: 'alpaca',
      name: 'Alpaca Paper',
      description: 'Paper broker connector with market-data support.',
      supported: true,
      readiness: 'beta',
      readiness_note: 'Credentials are validated by the mock endpoint.',
      auth_fields: ['api_key', 'api_secret', 'paper'],
      docs_url: 'about:blank',
      color: '#f59e0b',
      risk_warning: { level: 'medium', message: 'Use paper mode until live permissions and risk limits are verified.' },
    },
  ];
}

function strategyRegistry() {
  return {
    strategies: {
      rsi: {
        name: 'RSI',
        version: '1.0.0',
        description: 'Relative strength paper strategy',
        author: 'Sentinel',
        tags: ['momentum'],
        risk_level: 'medium',
        requires_history_bars: 20,
        supported_markets: ['US'],
        is_signal_strategy: true,
        default_params: { period: 14, oversold: 30, overbought: 70, enabled: true },
        config_schema: {
          type: 'object',
          properties: {
            period: { type: 'integer', minimum: 2, maximum: 50, default: 14 },
            oversold: { type: 'number', minimum: 1, maximum: 50, default: 30 },
            overbought: { type: 'number', minimum: 50, maximum: 99, default: 70 },
            enabled: { type: 'boolean', default: true },
          },
        },
      },
      macd_v: {
        name: 'MACD-V',
        version: '1.0.0',
        description: 'Volume-adjusted MACD signal engine',
        author: 'Sentinel',
        tags: ['trend', 'volume'],
        risk_level: 'medium',
        requires_history_bars: 50,
        supported_markets: ['US'],
        is_signal_strategy: true,
        default_params: { fast: 12, slow: 26, signal: 9 },
        config_schema: {
          type: 'object',
          properties: {
            fast: { type: 'integer', minimum: 2, maximum: 30, default: 12 },
            slow: { type: 'integer', minimum: 10, maximum: 60, default: 26 },
            signal: { type: 'integer', minimum: 2, maximum: 20, default: 9 },
          },
        },
      },
    },
  };
}

async function handleApi(request, response) {
  const url = new URL(request.url ?? '/', 'http://127.0.0.1');
  const body = request.method === 'GET' || request.method === 'HEAD' ? {} : await readBody(request);
  requests.push({ method: request.method, path: url.pathname, search: url.search, body });

  if (url.pathname === '/api/auth/me') return json(response, { username: 'automation' });
  if (url.pathname === '/api/auth/bootstrap-status') return json(response, { needs_bootstrap: false });
  if (url.pathname === '/api/auth/login' || url.pathname === '/api/auth/bootstrap') return json(response, { access_token: 'automation-token', username: 'automation' });
  if (url.pathname === '/api/auth/users') return json(response, [{ id: 'admin', username: 'admin', role: 'owner', enabled: true }]);
  if (url.pathname === '/api/auth/api-keys') return json(response, [{ id: 'paper-key', name: 'Paper Key', prefix: 'sp_test', created_at: new Date().toISOString() }]);
  if (url.pathname === '/api/logs/client-events' || url.pathname === '/api/logs/client-error') return json(response, { ok: true });

  if (url.pathname === '/api/bot/snapshot') return json(response, snapshot());
  if (url.pathname === '/api/bot/start') {
    state.running = true;
    state.paused = false;
    if (body.enable_all !== false) state.tickers = state.tickers.map((item) => ({ ...item, enabled: true, buying_paused: false }));
    broadcast({ type: 'BOT_STATUS', running: state.running, paused: state.paused });
    broadcast({ type: 'TICKERS_REORDERED', tickers: state.tickers });
    return json(response, { running: state.running, paused: state.paused, tickers: state.tickers });
  }
  if (url.pathname === '/api/bot/pause') {
    state.paused = !state.paused;
    broadcast({ type: 'BOT_STATUS', running: state.running, paused: state.paused });
    return json(response, { running: state.running, paused: state.paused });
  }
  if (url.pathname === '/api/bot/stop') {
    state.running = false;
    state.paused = false;
    if (body.disable_all !== false) state.tickers = state.tickers.map((item) => ({ ...item, enabled: false }));
    broadcast({ type: 'BOT_STATUS', running: state.running, paused: state.paused });
    broadcast({ type: 'TICKERS_REORDERED', tickers: state.tickers });
    return json(response, { running: state.running, paused: state.paused, tickers: state.tickers });
  }

  if (url.pathname === '/api/settings' && request.method === 'GET') {
    return json(response, {
      account_balance: 25000,
      increment_step: 0.5,
      decrement_step: 0.5,
      simulate_24_7: state.simulate_24_7,
      market_hours_only: state.market_hours_only,
      live_during_market_hours: state.live_during_market_hours,
      paper_after_hours: state.paper_after_hours,
      telegram_bot_token: '',
      telegram_chat_ids: [],
      global_daily_drawdown_enabled: true,
      global_daily_drawdown_limit: 3,
      global_daily_drawdown_type: 'percent',
    });
  }
  if (url.pathname === '/api/settings' && request.method === 'POST') {
    Object.assign(state, {
      simulate_24_7: body.simulate_24_7 ?? state.simulate_24_7,
      market_hours_only: body.market_hours_only ?? state.market_hours_only,
      live_during_market_hours: body.live_during_market_hours ?? state.live_during_market_hours,
      paper_after_hours: body.paper_after_hours ?? state.paper_after_hours,
    });
    broadcast({ type: 'MODE_SWITCH', simulate_24_7: state.simulate_24_7, trading_mode: state.simulate_24_7 ? 'paper' : 'live' });
    return json(response, { ok: true, ...body });
  }
  if (url.pathname === '/api/settings/telegram/test') return json(response, { ok: true, sent: false, detail: 'mocked' });
  if (url.pathname === '/api/settings/currency-display' && request.method === 'GET') return json(response, { mode: state.currencyDisplay });
  if (url.pathname === '/api/settings/currency-display' && request.method === 'POST') {
    state.currencyDisplay = url.searchParams.get('mode') || state.currencyDisplay;
    return json(response, { mode: state.currencyDisplay });
  }

  if (url.pathname === '/api/tickers' && request.method === 'GET') return json(response, state.tickers);
  if (url.pathname === '/api/tickers' && request.method === 'POST') {
    const next = ticker((body.symbol || `BOT${state.tickers.length + 1}`).toUpperCase(), state.tickers.length, 100);
    Object.assign(next, body);
    state.tickers.push(next);
    state.prices[next.symbol] = next._price || 100;
    broadcast({ type: 'TICKER_ADDED', ticker: next });
    return json(response, next);
  }
  if (url.pathname === '/api/tickers/reorder') {
    return json(response, { ok: true, tickers: state.tickers });
  }
  const tickerMatch = url.pathname.match(/^\/api\/tickers\/([^/]+)$/);
  if (tickerMatch && request.method === 'PUT') {
    const symbol = decodeURIComponent(tickerMatch[1]).toUpperCase();
    const index = state.tickers.findIndex((item) => item.symbol === symbol);
    if (index >= 0) {
      state.tickers[index] = { ...state.tickers[index], ...body, symbol };
      broadcast({ type: 'TICKER_UPDATED', ticker: state.tickers[index] });
      return json(response, state.tickers[index]);
    }
    return json(response, { detail: 'Ticker not found' }, 404);
  }
  if (tickerMatch && request.method === 'DELETE') {
    const symbol = decodeURIComponent(tickerMatch[1]).toUpperCase();
    const existing = state.tickers.find((item) => item.symbol === symbol);
    if (existing) broadcast({ type: 'TICKER_UPDATED', ticker: existing });
    return json(response, { ok: true });
  }

  if (url.pathname === '/api/strategies/registry') return json(response, strategyRegistry());
  if (url.pathname === '/api/strategies/reload') return json(response, { ok: true, ...strategyRegistry() });
  if (url.pathname === '/api/brokers') return json(response, brokerList());
  if (url.pathname.match(/^\/api\/brokers\/[^/]+\/test$/)) {
    const brokerId = url.pathname.split('/')[3];
    return json(response, {
      broker_id: brokerId,
      broker_name: brokerList().find((broker) => broker.id === brokerId)?.name || brokerId,
      overall: 'pass',
      checks: [
        { name: 'credentials_format', status: 'pass', message: 'Credentials accepted by mock validator.' },
        { name: 'account_access', status: 'pass', message: 'Buying Power: $25,000.00 | Balance: $25,000.00' },
        { name: 'market_data', status: 'pass', message: 'Mock market data stream is available.' },
      ],
    });
  }
  if (url.pathname.match(/^\/api\/rate-limits\/[^/]+$/)) return json(response, {
    broker_id: url.pathname.split('/').pop(),
    circuit_state: 'closed',
    failure_count: 0,
    requests_last_minute: 2,
    requests_last_second: 0,
    concurrent_requests: 0,
    limits: {
      requests_per_minute: 60,
      requests_per_second: 5,
      burst_limit: 10,
      failure_threshold: 5,
      recovery_timeout_seconds: 60,
    },
    recovery_remaining_seconds: null,
    config: {
      broker_id: url.pathname.split('/').pop(),
      circuit_state: 'closed',
      limits: {
        requests_per_minute: 60,
        requests_per_second: 5,
        burst_limit: 10,
        failure_threshold: 5,
        recovery_timeout_seconds: 60,
      },
    },
  });
  if (url.pathname === '/api/price-sources/toggle') {
    state.preferBrokerPrices = url.searchParams.get('prefer_broker') !== 'false';
    return json(response, { prefer_broker: state.preferBrokerPrices });
  }

  if (url.pathname === '/api/markets') return json(response, [
    { code: 'US', name: 'United States', currency: 'USD', is_open: true, timezone: 'America/New_York' },
    { code: 'HK', name: 'Hong Kong', currency: 'HKD', is_open: false, timezone: 'Asia/Hong_Kong' },
  ]);
  if (url.pathname === '/api/fx-rates') return json(response, { rates: { USD: 1, HKD: 0.128, GBP: 1.27, CAD: 0.73 } });

  if (url.pathname === '/api/preflight') return json(response, {
    ready_to_trade: true,
    summary: { pass: 4, warn: 0, fail: 0 },
    checks: [
      { id: 'account', label: 'Account', status: 'pass', detail: 'Mock account funded.', action: 'None' },
      { id: 'pulse-engine', label: 'Pulse Engine', status: 'pass', detail: 'Paper engine online.', action: 'None' },
      { id: 'separate-engine', label: 'Sentinel Archive', status: 'pass', detail: 'Sentinel Archive online.', action: 'None' },
      { id: 'tickers', label: '3 Bots', status: 'pass', detail: 'AAPL, MSFT, TSLA enabled.', action: 'None' },
    ],
    context: { trading_mode: state.simulate_24_7 ? 'paper' : 'live', account_balance: 25000, allocated: 3000, available: 22000, enabled_tickers: 3, connected_brokers: 2, running: state.running, paused: state.paused },
  });
  if (url.pathname === '/api/positions') return json(response, Object.values(snapshot().positions));
  if (url.pathname === '/api/positions/pending-sells') return json(response, { TSLA: { symbol: 'TSLA', quantity: 1, limit_price: 180 } });
  if (url.pathname === '/api/positions/by-broker') return json(response, [{ broker_id: 'paper', symbol: 'AAPL', quantity: 4, market_value: 756.48 }]);
  if (url.pathname.match(/^\/api\/positions\/[^/]+\/sell$/)) return json(response, { ok: true, order_id: 'mock-sell' });
  if (url.pathname.match(/^\/api\/positions\/[^/]+\/pending-sell$/)) return json(response, { ok: true });

  if (url.pathname === '/api/orders') return json(response, { orders: [{
    order_id: 'order-1',
    symbol: 'AAPL',
    side: 'buy',
    order_type: 'MARKET',
    quantity: 4,
    price: 184.25,
    status: 'filled',
    filled_quantity: 4,
    avg_fill_price: 184.25,
    created_at: new Date(Date.now() - 3600000).toISOString(),
    updated_at: new Date(Date.now() - 3590000).toISOString(),
    broker: 'paper',
    external_id: 'paper-order-1',
    execution_lag_ms: 18,
  }] });
  if (url.pathname === '/api/orders/stats') return json(response, {
    total_orders: 1,
    filled_orders: 1,
    rejected_orders: 0,
    pending_orders: 0,
    avg_slippage: 1.5,
    avg_execution_lag_ms: 18,
    fill_rate: 1,
  });
  if (url.pathname === '/api/trades') return json(response, sampleTrades());
  if (url.pathname === '/api/loss-logs') return json(response, [{ date: '2026-06-15', file: 'paper-losses.log', size: 120 }]);
  if (url.pathname.match(/^\/api\/loss-logs\//)) return text(response, 'No losses in mock test run.');

  if (url.pathname === '/api/portfolio/stats') return json(response, { total_value: 25000, cash: 22000, invested: 3000, pnl: 50, pnl_pct: 0.2 });
  if (url.pathname === '/api/portfolio/daily-returns') return json(response, [{ date: '2026-06-15', return_pct: 0.2, pnl: 50 }]);
  if (url.pathname === '/api/portfolio/export') return text(response, 'symbol,qty,value\nAAPL,4,756.48\n', 200, 'text/csv');
  if (url.pathname === '/api/analytics/portfolio') return json(response, {
    total_value: 25000,
    total_pnl: 50,
    daily_pnl: 18,
    total_return: 0.2,
    sharpe_ratio: 1.2,
    max_drawdown: 2.1,
    win_rate: 0.62,
    avg_win: 42,
    avg_loss: -18,
    turnover: 0.08,
    trade_count: 12,
  });
  if (url.pathname === '/api/analytics/attribution') return json(response, {
    attribution: [
      { strategy: 'RSI', pnl: 42.2, allocation: 0.55 },
      { strategy: 'MACD-V', pnl: 7.8, allocation: 0.45 },
    ],
  });
  if (url.pathname === '/api/analytics/regimes') return json(response, {
    regimes: [
      { regime: 'trend', count: 8, win_rate: 0.75 },
      { regime: 'range', count: 4, win_rate: 0.5 },
    ],
  });

  if (url.pathname === '/api/risk/limits') return json(response, { max_daily_loss: 500, max_position_pct: 20, max_order_value: 1000 });
  if (url.pathname === '/api/risk/kill-switches') return json(response, [{ id: 'global', label: 'Global Trading', enabled: false }]);
  if (url.pathname.match(/^\/api\/risk\/kill-switches\//)) return json(response, { ok: true });
  if (url.pathname === '/api/reconciliation/records') return json(response, { records: [{
    record_id: 'rec-1',
    symbol: 'AAPL',
    side: 'buy',
    quantity: 4,
    price: 184.25,
    broker: 'paper',
    internal_timestamp: new Date(Date.now() - 3600000).toISOString(),
    broker_timestamp: new Date(Date.now() - 3599500).toISOString(),
    status: 'matched',
    pnl: 19.48,
  }] });
  if (url.pathname === '/api/reconciliation/summary') return json(response, {
    total_records: 1,
    matched: 1,
    breaks: 0,
    pending: 0,
    total_pnl: 19.48,
    last_sync: new Date().toISOString(),
  });
  if (url.pathname === '/api/reconciliation/signoff') return json(response, { ok: true, signed_by: 'automation' });
  if (url.pathname === '/api/audit/events') return json(response, { events: [{
    event_id: 'audit-1',
    event_type: 'SETTING_CHANGED',
    timestamp: new Date().toISOString(),
    user_id: 'automation',
    username: 'automation',
    action: 'Exhaustive paper-mode control test',
    details: { engine: state.simulate_24_7 ? 'paper' : 'market-hours' },
    ip_address: '127.0.0.1',
  }], count: 1 });
  if (url.pathname === '/api/audit/summary') return json(response, {
    total_events: 1,
    unique_users: 1,
    events_today: 1,
    high_risk_events: 0,
  });
  if (url.pathname === '/api/audit/export') return json(response, { download_url: 'about:blank' });
  if (url.pathname === '/api/audit-logs') return json(response, { logs: [{ id: 'log-1', event_type: 'INFO', message: 'Mock audit log', timestamp: new Date().toISOString() }], total: 1 });

  if (url.pathname === '/api/ops/services') return json(response, [{ id: 'pulse', status: 'healthy' }, { id: 'separate-bot-engine', status: 'healthy' }]);
  if (url.pathname === '/api/ops/incidents') return json(response, [{ id: 'inc-1', severity: 'low', status: 'resolved', title: 'Mock incident' }]);
  if (url.pathname === '/api/ops/runbooks') return json(response, [{ id: 'rb-1', title: 'Pause all bots', steps: ['Pause', 'Verify'] }]);
  if (url.pathname === '/api/slo') return json(response, { uptime_pct: 99.9, latency_p95_ms: 42, error_rate_pct: 0.01 });
  if (url.pathname === '/api/slo/alerts') return json(response, []);
  if (url.pathname === '/api/slo/incidents') return json(response, []);
  if (url.pathname === '/api/slo/summary') return json(response, { ok: true, burn_rate: 0.1 });
  if (url.pathname === '/api/traces') return json(response, { traces: [{ trace_id: 'trace-1', span_count: 4, duration_ms: 24 }], total: 1 });

  const replaySession = {
    session_id: 'replay-1',
    name: 'AAPL MSFT TSLA mock replay',
    source: 'automation',
    symbols: ['AAPL', 'MSFT', 'TSLA'],
    trading_date: '2026-06-15',
    interval: '1m',
    bar_count: 120,
    imported_at: new Date().toISOString(),
  };
  if (url.pathname === '/api/replay/sessions') return json(response, { sessions: [replaySession] });
  if (url.pathname === '/api/replay/status') return json(response, { replay: { active: false, session_id: null, symbols: [], speed: 30, loop: false } });
  if (url.pathname.match(/^\/api\/replay\/sessions\/[^/]+\/start$/)) return json(response, { replay: { active: true, session_id: url.pathname.split('/')[4], symbols: replaySession.symbols, speed: body.speed || 30, loop: Boolean(body.loop) } });
  if (url.pathname === '/api/replay/stop') return json(response, { replay: { active: false, session_id: null, symbols: [] } });
  if (url.pathname === '/api/replay/import/yfinance' || url.pathname === '/api/replay/import/alpaca') return json(response, { ok: true, session_id: 'imported-replay', bars_imported: 120, session: { ...replaySession, session_id: 'imported-replay', name: body.name || replaySession.name } });

  if (url.pathname === '/api/beta/register' || url.pathname === '/api/feedback') return json(response, { ok: true });

  unknownRoutes.push(`${request.method} ${url.pathname}${url.search}`);
  return json(response, { ok: true, mocked: true });
}

let wss;
const wsClients = new Set();
function broadcast(payload) {
  for (const client of wsClients) {
    if (client.readyState === 1) client.send(JSON.stringify(payload));
  }
}

async function startBackend(port) {
  const server = http.createServer((request, response) => {
    response.setHeader('Access-Control-Allow-Origin', '*');
    response.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,PATCH,DELETE,OPTIONS');
    response.setHeader('Access-Control-Allow-Headers', 'authorization,content-type');
    if (request.method === 'OPTIONS') {
      response.writeHead(204);
      response.end();
      return;
    }
    if ((request.url ?? '').startsWith('/api/')) {
      handleApi(request, response).catch((error) => json(response, { detail: error.message }, 500));
      return;
    }
    json(response, { ok: true });
  });

  wss = new WebSocketServer({ noServer: true });
  server.on('upgrade', (request, socket, head) => {
    if ((request.url ?? '').startsWith('/api/ws')) {
      wss.handleUpgrade(request, socket, head, (ws) => wss.emit('connection', ws, request));
      return;
    }
    socket.destroy();
  });
  wss.on('connection', (ws) => {
    wsClients.add(ws);
    ws.on('close', () => wsClients.delete(ws));
    ws.send(JSON.stringify({ type: 'INITIAL_STATE', ...snapshot() }));
    setTimeout(() => ws.readyState === 1 && ws.send(JSON.stringify({
      type: 'PRICE_UPDATE',
      prices: { AAPL: 190.35, MSFT: 420.92, TSLA: 172.4 },
      profits: { AAPL: 49.1, MSFT: 16.2, TSLA: -12.5 },
      positions: snapshot().positions,
      trades: sampleTrades(),
      account_balance: 25000,
      allocated: 3000,
      available: 22000,
      simulate_24_7: state.simulate_24_7,
      live_during_market_hours: state.live_during_market_hours,
      paper_after_hours: state.paper_after_hours,
      running: state.running,
      paused: state.paused,
      market_open: true,
    })), 400);
  });

  await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve));
  return server;
}

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

async function waitForVite(port, vite) {
  const deadline = Date.now() + 25_000;
  let lastError = '';
  while (Date.now() < deadline) {
    if (vite.exitCode !== null) throw new Error(`Vite exited early.\n${vite.output}`);
    try {
      const response = await fetch(`http://127.0.0.1:${port}`);
      const html = await response.text();
      if (response.ok && html.includes('/src/main.tsx')) return;
      lastError = `Unexpected dev-server response: ${response.status}`;
    } catch (error) {
      lastError = error.message;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Vite did not start on owned port ${port}: ${lastError}\n${vite.output}`);
}

function startVite(frontendPort, backendPort) {
  const command = process.platform === 'win32'
    ? ['cmd.exe', ['/d', '/s', '/c', `npm.cmd run dev -- --host 127.0.0.1 --port ${frontendPort} --strictPort`]]
    : ['npm', ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort']];
  const vite = spawn(command[0], command[1], {
    cwd: root,
    env: {
      ...process.env,
      VITE_BACKEND_URL: `http://127.0.0.1:${backendPort}`,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  vite.output = '';
  vite.stdout.on('data', (chunk) => { vite.output += chunk.toString(); });
  vite.stderr.on('data', (chunk) => { vite.output += chunk.toString(); });
  return vite;
}

async function clickIfVisible(page, locator, label, issues, timeout = 1200) {
  try {
    if ((await locator.count()) === 0) return false;
    const first = locator.first();
    await first.waitFor({ state: 'visible', timeout });
    await first.scrollIntoViewIfNeeded();
    await first.click({ timeout, force: true });
    return true;
  } catch (error) {
    issues.push({ severity: 'error', area: label, message: error.message });
    return false;
  }
}

async function exerciseControls(page, tabId, passName, issues, actions, scopeLocator = null) {
  const scope = scopeLocator ?? page.getByTestId('tab-content');
  const selectors = [
    ['button', 'button:not([disabled])'],
    ['checkbox', 'input[type="checkbox"]:not([disabled]), [role="checkbox"]:not([aria-disabled="true"])'],
    ['switch', '[role="switch"]:not([aria-disabled="true"])'],
    ['toggle', '[role="radio"]:not([aria-disabled="true"]), [data-radix-collection-item]:not([disabled])'],
    ['select', 'select:not([disabled]), [role="combobox"]:not([aria-disabled="true"])'],
    ['input', 'input:not([type="hidden"]):not([type="checkbox"]):not([disabled]), textarea:not([disabled])'],
  ];

  for (const [kind, selector] of selectors) {
    const count = Math.min(await scope.locator(selector).count(), kind === 'button' ? 18 : 12);
    for (let index = 0; index < count; index += 1) {
      const locator = scope.locator(selector).nth(index);
      const action = `${passName}:${tabId}:${kind}:${index}`;
      try {
        if (!(await locator.isVisible().catch(() => false))) continue;
        await locator.scrollIntoViewIfNeeded();
        if (kind === 'input') {
          const type = await locator.getAttribute('type').catch(() => '');
          const value = type === 'number' ? '2' : `Auto ${tabId}`;
          await locator.fill(value, { timeout: 1200 }).catch(async () => {
            await locator.click({ timeout: 1200, force: true });
          });
        } else if (kind === 'select') {
          if ((await locator.evaluate((node) => node.tagName.toLowerCase()).catch(() => '')) === 'select') {
            const values = await locator.locator('option').evaluateAll((options) => options.map((option) => option.value).filter(Boolean));
            if (values[0]) await locator.selectOption(values[0], { timeout: 1200 });
          } else {
            await locator.click({ timeout: 1200, force: true });
            await page.keyboard.press('Escape').catch(() => {});
          }
        } else {
          await locator.click({ timeout: 1200, force: true });
        }
        actions.push(action);
        await page.waitForTimeout(80);
      } catch (error) {
        issues.push({ severity: 'error', area: `${tabId} ${kind}`, message: error.message, action });
      }
      await closeTransientUi(page);
    }
  }
}

async function closeTransientUi(page) {
  await page.keyboard.press('Escape').catch(() => {});
  const dialogCloseButtons = page.locator('button[aria-label*="Close"], button:has-text("Cancel"), button:has-text("Close")');
  const count = Math.min(await dialogCloseButtons.count().catch(() => 0), 3);
  for (let i = 0; i < count; i += 1) {
    const button = dialogCloseButtons.nth(i);
    if (await button.isVisible().catch(() => false)) {
      await button.click({ timeout: 500, force: true }).catch(() => {});
    }
  }
}

async function runPass(page, passName, issues, actions) {
  await page.getByTestId('tab-bar').waitFor({ state: 'visible', timeout: 10_000 });
  for (const tabId of tabIds) {
    const groupId = tabGroups[tabId];
    if (groupId) {
      await clickIfVisible(page, page.getByTestId(`tab-group-${groupId}`), `group:${groupId}`, issues, 2500);
      await page.waitForTimeout(100);
    }
    const tab = page.getByTestId(`tab-${tabId}`);
    if ((await tab.count()) === 0) {
      issues.push({ severity: 'error', area: 'navigation', message: `Missing tab ${tabId}` });
      continue;
    }
    await clickIfVisible(page, tab, `tab:${tabId}`, issues, 2500);
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.waitForTimeout(250);
    const fallback = page.getByText(`Tab "${tabId}" failed to render`);
    if (await fallback.isVisible().catch(() => false)) {
      issues.push({ severity: 'error', area: tabId, message: 'Tab error boundary rendered' });
    }
    await exerciseControls(page, tabId, passName, issues, actions);
    await page.screenshot({ path: path.join(artifactDir, `${passName}-${tabId}.png`), fullPage: true }).catch(() => {});
  }

  await page.getByTestId('tab-group-trading').click();
  await page.getByTestId('tab-watchlist').click();
  broadcast({ type: 'INITIAL_STATE', ...snapshot() });
  await page.waitForFunction(() => {
    return ['AAPL', 'MSFT', 'TSLA'].every((symbol) => (
      document.querySelector(`[data-testid="ticker-card-${symbol}"]`)
    ));
  }, null, { timeout: 6000 }).catch((error) => {
    issues.push({ severity: 'error', area: 'bot-cards', message: `Bot cards did not restore after destructive-control sweep: ${error.message}` });
  });

  for (const symbol of ['AAPL', 'MSFT', 'TSLA']) {
    await page.getByTestId(`ticker-card-${symbol}`).waitFor({ state: 'visible', timeout: 5000 }).catch((error) => {
      issues.push({ severity: 'error', area: `bot:${symbol}`, message: `Ticker card not visible: ${error.message}` });
    });
    await clickIfVisible(page, page.getByLabel(`Configure ${symbol}`), `configure:${symbol}`, issues, 2500);
    await page.waitForTimeout(250);
    const configModal = page.getByTestId(`config-modal-${symbol}`);
    if (await configModal.isVisible().catch(() => false)) {
      const modalTabs = ['strategy', 'brokers', 'advanced', 'partial-fills'];
      for (const modalTab of modalTabs) {
        await clickIfVisible(page, configModal.locator(`[role="tab"]:has-text("${modalTab}")`), `config:${symbol}:${modalTab}`, issues, 800);
        await exerciseControls(page, `config-${symbol}-${modalTab}`, passName, issues, actions, configModal);
      }
      await clickIfVisible(page, page.getByTestId(`close-config-modal-${symbol}`), `close-config:${symbol}`, issues, 1500);
    }
  }
}

function recommendations() {
  return [
    'Add a paper-trading replay preset that runs the same ticker set through Pulse paper mode and the separate Sentinel Archive, then displays order-by-order drift.',
    'Add per-bot readiness gates: market data freshness, broker buying power, strategy confidence, max spread, and news/volatility lockouts before any order is allowed.',
    'Expose strategy outcome telemetry beside each bot: signal reason, rejected-signal reason, expected R multiple, realized slippage, and cooldown state.',
    'Add a one-click safe test run that force-enables simulate_24_7, disables live broker adapters, runs a replay session, and exports a trade-quality report.',
    'Add guardrails for profitability testing: walk-forward replay, fee/slippage modeling, position sizing caps, and broker-specific fill simulation.',
  ];
}

async function run() {
  await fs.mkdir(artifactDir, { recursive: true });
  const backendPort = await freePort();
  const frontendPort = await freePort();
  const backend = await startBackend(backendPort);
  const vite = startVite(frontendPort, backendPort);
  const report = {
    started_at: new Date().toISOString(),
    frontend_port: frontendPort,
    backend_port: backendPort,
    passes: [],
    issues: [],
    actions: [],
    requests,
    unknown_routes: unknownRoutes,
    recommendations: recommendations(),
  };

  let browser;
  try {
    await waitForVite(frontendPort, vite);
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    await page.addInitScript(() => {
      localStorage.setItem('sentinel_auth_token', 'automation-token');
    });

    page.on('console', (message) => {
      if (message.type() === 'error') {
        report.issues.push({ severity: 'error', area: 'console', message: message.text() });
      }
    });
    page.on('pageerror', (error) => {
      report.issues.push({ severity: 'error', area: 'pageerror', message: error.message });
    });
    page.on('response', (response) => {
      if (response.url().includes('/api/') && response.status() >= 400) {
        report.issues.push({ severity: 'error', area: 'api', message: `${response.status()} ${response.url()}` });
      }
    });

    await page.goto(`http://127.0.0.1:${frontendPort}`, { waitUntil: 'domcontentloaded' });
    await page.getByTestId('tab-bar').waitFor({ state: 'visible', timeout: 10_000 });

    for (const engineMode of [
      { name: 'pulse-paper-engine', settings: { simulate_24_7: true, live_during_market_hours: false, paper_after_hours: true } },
      { name: 'pulse-market-hours-engine', settings: { simulate_24_7: false, live_during_market_hours: true, paper_after_hours: true } },
      { name: 'separate-bot-engine', settings: { simulate_24_7: true, live_during_market_hours: false, paper_after_hours: true, separate_bot_engine: true } },
    ]) {
      await fetch(`http://127.0.0.1:${backendPort}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(engineMode.settings),
      });
      broadcast({ type: 'INITIAL_STATE', ...snapshot() });
      const beforeIssueCount = report.issues.length;
      const beforeActionCount = report.actions.length;
      await runPass(page, engineMode.name, report.issues, report.actions);
      report.passes.push({
        name: engineMode.name,
        issue_count: report.issues.length - beforeIssueCount,
        action_count: report.actions.length - beforeActionCount,
      });
    }

    await page.screenshot({ path: path.join(artifactDir, 'final-state.png'), fullPage: true });
  } finally {
    if (browser) await browser.close().catch(() => {});
    for (const client of wsClients) client.terminate();
    if (wss) wss.close();
    await new Promise((resolve) => backend.close(resolve));
    await stopProcessTree(vite.pid);
  }

  const uniqueIssues = [];
  const seenIssues = new Set();
  for (const issue of report.issues) {
    const key = `${issue.area}:${issue.message}`;
    if (seenIssues.has(key)) continue;
    seenIssues.add(key);
    uniqueIssues.push(issue);
  }
  report.unique_issues = uniqueIssues;
  report.completed_at = new Date().toISOString();
  await fs.writeFile(reportPath, JSON.stringify(report, null, 2));
  await fs.writeFile(markdownPath, renderMarkdown(report));

  if (uniqueIssues.length > 0) {
    console.error(`All-bots automation completed with ${uniqueIssues.length} unique issue(s).`);
    console.error(`Report: ${markdownPath}`);
    process.exitCode = 1;
  } else {
    console.log(`All-bots automation passed. Report: ${markdownPath}`);
  }
}

function renderMarkdown(report) {
  const lines = [
    '# Sentinel Pulse All-Bots Automation Report',
    '',
    `Started: ${report.started_at}`,
    `Completed: ${report.completed_at}`,
    '',
    '## Passes',
    '',
    '| Pass | Actions | Issues |',
    '| --- | ---: | ---: |',
    ...report.passes.map((item) => `| ${item.name} | ${item.action_count} | ${item.issue_count} |`),
    '',
    '## Bugs And Errors',
    '',
  ];

  if (report.unique_issues.length === 0) {
    lines.push('No unique UI, console, page, or API errors were captured.');
  } else {
    for (const issue of report.unique_issues) {
      lines.push(`- ${issue.severity.toUpperCase()} [${issue.area}]: ${issue.message.replace(/\s+/g, ' ').slice(0, 500)}`);
    }
  }

  lines.push('', '## Unknown Mocked Routes', '');
  if (report.unknown_routes.length === 0) {
    lines.push('No unknown API routes were hit.');
  } else {
    for (const route of [...new Set(report.unknown_routes)]) lines.push(`- ${route}`);
  }

  lines.push('', '## Trading Improvement Suggestions', '');
  for (const item of report.recommendations) lines.push(`- ${item}`);
  lines.push('');
  return `${lines.join('\n')}\n`;
}

function stopProcessTree(pid) {
  if (!pid) return Promise.resolve();
  if (process.platform !== 'win32') {
    try {
      process.kill(pid, 'SIGTERM');
    } catch {}
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    execFile('taskkill.exe', ['/PID', String(pid), '/T', '/F'], () => resolve());
  });
}

await run();
