import { useEffect, useRef, useCallback } from 'react';
import { useStore } from '@/stores/useStore';

const BACKEND_URL = import.meta.env.REACT_APP_BACKEND_URL || '';

function getWsUrl(): string {
  if (BACKEND_URL) {
    const url = new URL(BACKEND_URL);
    const proto = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${proto}//${url.host}/api/ws`;
  }
  return `ws://${window.location.hostname}:8001/api/ws`;
}

export function useWebSocket() {
  const socket = useRef<WebSocket | null>(null);
  const reconnect = useRef<ReturnType<typeof setTimeout> | null>(null);
  const store = useStore();

  const connect = useCallback(() => {
    if (socket.current?.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(getWsUrl());
    socket.current = ws;

    ws.onopen = () => {
      store.setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'INITIAL_STATE') {
          if (data.tickers) store.setTickers(data.tickers);
          if (data.prices) store.setPrices(data.prices);
          if (data.profits) store.setProfits(data.profits);
          if (data.cash_reserve !== undefined) store.setCashReserve(data.cash_reserve);
          if (data.increment_step !== undefined) store.setIncrementStep(data.increment_step);
          if (data.decrement_step !== undefined) store.setDecrementStep(data.decrement_step);
          if (data.account_balance !== undefined) {
            store.setAccountBalance(data.account_balance, data.allocated ?? 0, data.available ?? 0);
          }
          store.setPaused(data.paused ?? false);
          store.setRunning(data.running ?? false);
          store.setMarketOpen(data.market_open ?? false);
        }

        if (data.type === 'PRICE_UPDATE') {
          if (data.prices) {
            store.setPrices(data.prices);
            store.appendPriceHistory(data.prices);
          }
          if (data.positions) store.setPositions(data.positions);
          if (data.profits) store.setProfits(data.profits);
          if (data.cash_reserve !== undefined) store.setCashReserve(data.cash_reserve);
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
          store.addTicker(data.ticker);
        }

        if (data.type === 'TICKER_UPDATED') {
          store.updateTicker(data.ticker.symbol, data.ticker);
        }

        if (data.type === 'TICKER_DELETED') {
          store.removeTicker(data.symbol);
        }

        if (data.type === 'TICKERS_REORDERED') {
          if (data.tickers) store.setTickers(data.tickers);
        }

        if (data.type === 'ACCOUNT_UPDATE') {
          store.setAccountBalance(data.account_balance ?? 0, data.allocated ?? 0, data.available ?? 0);
        }

        if (data.type === 'BOT_STATUS') {
          store.setRunning(data.running ?? store.running);
          store.setPaused(data.paused ?? store.paused);
        }
      } catch (err) {
        console.error('WS parse error:', err);
      }
    };

    ws.onclose = () => {
      store.setConnected(false);
      reconnect.current = setTimeout(connect, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnect.current) clearTimeout(reconnect.current);
      socket.current?.close();
    };
  }, [connect]);

  const send = useCallback((action: string, payload: Record<string, any> = {}) => {
    if (socket.current?.readyState === WebSocket.OPEN) {
      socket.current.send(JSON.stringify({ action, ...payload }));
    }
  }, []);

  return { send };
}
