import { useCallback, useEffect } from 'react';
import { useStore } from '@/stores/useStore';
import { getAuthToken } from '@/lib/api';
import { uiLog } from '@/lib/clientLogger';
import { wsLog } from '@/lib/wsLogger';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';

function getWsUrl(): string {
  const token = getAuthToken();
  if (!token) return '';

  const url = BACKEND_URL
    ? new URL(BACKEND_URL).host
    : `${window.location.host}`;
  const proto = BACKEND_URL
    ? (new URL(BACKEND_URL).protocol === 'https:' ? 'wss:' : 'ws:')
    : (window.location.protocol === 'https:' ? 'wss:' : 'ws:');
  const wsUrl = new URL(`${proto}//${url}/api/ws`);
  wsUrl.searchParams.set('token', token);
  uiLog.ws('url_created', { host: wsUrl.host, path: wsUrl.pathname });
  return wsUrl.toString();
}

let socket: WebSocket | null = null;
let reconnect: ReturnType<typeof setTimeout> | null = null;
let disconnectGraceTimer: ReturnType<typeof setTimeout> | null = null;
let reconnectDelay = 3000;
let subscribers = 0;
let intentionalClose = false;

function handleMessage(event: MessageEvent) {
  const store = useStore.getState();

  try {
    const data = JSON.parse(event.data);
    wsLog.in(data.type, data);
    uiLog.ws('message_in', { message_type: data.type });

    if (data.type === 'INITIAL_STATE') {
      uiLog.ws('initial_state', {
        ticker_count: data.tickers ? Object.keys(data.tickers).length : 0,
        price_count: data.prices ? Object.keys(data.prices).length : 0,
      });
      if (data.tickers) store.setTickers(data.tickers);
      if (data.prices) {
        store.setPrices(data.prices);
        store.appendPriceHistory(data.prices);
      }
      if (data.profits) store.setProfits(data.profits);
      if (data.cash_reserve !== undefined) store.setCashReserve(data.cash_reserve);
      if (data.increment_step !== undefined) store.setIncrementStep(data.increment_step);
      if (data.decrement_step !== undefined) store.setDecrementStep(data.decrement_step);
      if (data.account_balance !== undefined) {
        store.setAccountBalance(data.account_balance, data.allocated ?? 0, data.available ?? 0);
      }
      if (data.simulate_24_7 !== undefined) store.setSimulate247(data.simulate_24_7);
      if (data.live_during_market_hours !== undefined) store.setLiveDuringMarketHours(data.live_during_market_hours);
      if (data.paper_after_hours !== undefined) store.setPaperAfterHours(data.paper_after_hours);
      store.setPaused(data.paused ?? false);
      store.setRunning(data.running ?? false);
      store.setMarketOpen(data.market_open ?? false);
    }

    if (data.type === 'PRICE_UPDATE') {
      uiLog.ws('price_update', { price_count: data.prices ? Object.keys(data.prices).length : 0 });
      if (data.prices) {
        store.setPrices(data.prices);
        store.appendPriceHistory(data.prices);
      }
      if (data.positions) store.setPositions(data.positions);
      if (data.profits) store.setProfits(data.profits);
      if (data.trades) store.setTrades(data.trades);
      if (data.cash_reserve !== undefined) store.setCashReserve(data.cash_reserve);
      if (data.account_balance !== undefined) {
        store.setAccountBalance(data.account_balance, data.allocated ?? 0, data.available ?? 0);
      }
      if (data.simulate_24_7 !== undefined) store.setSimulate247(data.simulate_24_7);
      if (data.live_during_market_hours !== undefined) store.setLiveDuringMarketHours(data.live_during_market_hours);
      if (data.paper_after_hours !== undefined) store.setPaperAfterHours(data.paper_after_hours);
      store.setPaused(data.paused ?? store.paused);
      store.setRunning(data.running ?? store.running);
      store.setMarketOpen(data.market_open ?? store.marketOpen);
    }

    if (data.type === 'PROFITS_UPDATE') {
      if (data.profits) store.setProfits(data.profits);
      if (data.cash_reserve !== undefined) store.setCashReserve(data.cash_reserve);
    }

    if (data.type === 'TRADE') {
      store.addTrade(data.trade);
    }

    if (data.type === 'TICKER_ADDED') {
      uiLog.ws('ticker_added', { symbol: data.ticker?.symbol });
      store.addTicker(data.ticker);
    }

    if (data.type === 'TICKER_ERROR') {
      uiLog.ws('ticker_error', { error: data.error, symbol: data.symbol }, 'error');
      window.dispatchEvent(new CustomEvent('ticker-error', { detail: data }));
    }

    if (data.type === 'TICKER_UPDATED') {
      uiLog.ws('ticker_updated', { symbol: data.ticker?.symbol });
      store.updateTicker(data.ticker.symbol, data.ticker);
    }

    if (data.type === 'TICKER_DELETED') {
      uiLog.ws('ticker_deleted', { symbol: data.symbol });
      store.removeTicker(data.symbol);
    }

    if (data.type === 'TICKERS_REORDERED') {
      uiLog.ws('tickers_reordered', { ticker_count: data.tickers ? Object.keys(data.tickers).length : 0 });
      if (data.tickers) store.setTickers(data.tickers);
    }

    if (data.type === 'ACCOUNT_UPDATE') {
      uiLog.ws('account_update', {
        account_balance: data.account_balance,
        allocated: data.allocated,
        available: data.available,
      });
      store.setAccountBalance(data.account_balance ?? 0, data.allocated ?? 0, data.available ?? 0);
    }

    if (data.type === 'BOT_STATUS') {
      uiLog.ws('bot_status', { running: data.running, paused: data.paused });
      store.setRunning(data.running ?? store.running);
      store.setPaused(data.paused ?? store.paused);
    }

    if (data.type === 'MODE_SWITCH') {
      uiLog.ws('mode_switch', { simulate_24_7: data.simulate_24_7, trading_mode: data.trading_mode });
      if (data.simulate_24_7 !== undefined) store.setSimulate247(data.simulate_24_7);
      if (data.trading_mode) store.setTradingMode(data.trading_mode);
    }

    if (data.type === 'BROKER_FAILED') {
      uiLog.ws('broker_failed', { broker_id: data.broker_id, reason: data.reason, symbol: data.symbol }, 'warn');
      store.setBrokerFailed(data.broker_id, data.reason || 'Connection failed', data.symbol || '');
      setTimeout(() => {
        useStore.getState().clearBrokerFailed(data.broker_id);
      }, 30000);
    }
  } catch (err) {
    uiLog.error('ws.parse_error', err, { payload_size: event.data?.length || 0 });
  }
}

function connect() {
  if (disconnectGraceTimer) {
    clearTimeout(disconnectGraceTimer);
    disconnectGraceTimer = null;
  }

  if (socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;

  const wsUrl = getWsUrl();
  if (!wsUrl) {
    uiLog.ws('connect_skipped', { reason: 'missing_auth_token' }, 'warn');
    return;
  }

  const ws = new WebSocket(wsUrl);
  socket = ws;
  intentionalClose = false;
  uiLog.ws('connecting', {});

  ws.onopen = () => {
    uiLog.ws('open', {});
    reconnectDelay = 3000;
    useStore.getState().setConnected(true);
  };

  ws.onmessage = handleMessage;

  ws.onclose = (event) => {
    uiLog.ws('close', { code: event.code, reason: event.reason, intentional: intentionalClose }, intentionalClose ? 'info' : 'warn');
    if (socket === ws) socket = null;
    useStore.getState().setConnected(false);
    if (subscribers === 0) return;

    const delay = Math.min(reconnectDelay, 300000);
    reconnectDelay = Math.min(reconnectDelay * 2, 300000);
    uiLog.ws('reconnect_scheduled', { delay_ms: delay, next_delay_ms: reconnectDelay }, 'warn');
    reconnect = setTimeout(connect, delay);
  };

  ws.onerror = (event) => {
    if (!intentionalClose) {
      uiLog.error('ws.error', 'WebSocket error event', { ready_state: ws.readyState, event_type: event.type });
    }
    ws.close();
  };
}

export function useWebSocket() {
  useEffect(() => {
    subscribers += 1;
    connect();

    return () => {
      subscribers = Math.max(0, subscribers - 1);
      if (subscribers === 0) {
        if (reconnect) clearTimeout(reconnect);
        reconnect = null;
        disconnectGraceTimer = setTimeout(() => {
          if (subscribers > 0) return;
          intentionalClose = true;
          socket?.close();
          socket = null;
          useStore.getState().setConnected(false);
          disconnectGraceTimer = null;
        }, 250);
      }
    };
  }, []);

  const send = useCallback((action: string, payload: Record<string, any> = {}) => {
    const msg = { action, ...payload };
    wsLog.out(action, payload);
    uiLog.ws('message_out', { action });
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(msg));
    } else {
      wsLog.error(action, 'Socket not open - message dropped');
      uiLog.ws('message_drop', { action, ready_state: socket?.readyState }, 'warn');
    }
  }, []);

  return { send };
}
