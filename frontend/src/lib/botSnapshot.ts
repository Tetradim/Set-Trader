import { useStore } from '@/stores/useStore';

export function applyBotSnapshot(snapshot: any) {
  const store = useStore.getState();

  if (Array.isArray(snapshot.tickers)) store.setTickers(snapshot.tickers);
  if (snapshot.prices) {
    store.setPrices(snapshot.prices);
    store.appendPriceHistory(snapshot.prices);
  }
  if (snapshot.positions) store.setPositions(snapshot.positions);
  if (snapshot.profits) store.setProfits(snapshot.profits);
  if (Array.isArray(snapshot.trades)) store.setTrades(snapshot.trades);
  if (snapshot.cash_reserve !== undefined) store.setCashReserve(snapshot.cash_reserve);
  if (snapshot.account_balance !== undefined) {
    store.setAccountBalance(snapshot.account_balance, snapshot.allocated ?? 0, snapshot.available ?? 0);
  }
  if (snapshot.increment_step !== undefined) store.setIncrementStep(snapshot.increment_step);
  if (snapshot.decrement_step !== undefined) store.setDecrementStep(snapshot.decrement_step);
  if (snapshot.simulate_24_7 !== undefined) store.setSimulate247(snapshot.simulate_24_7);
  if (snapshot.live_during_market_hours !== undefined) store.setLiveDuringMarketHours(snapshot.live_during_market_hours);
  if (snapshot.paper_after_hours !== undefined) store.setPaperAfterHours(snapshot.paper_after_hours);
  if (snapshot.running !== undefined) store.setRunning(snapshot.running);
  if (snapshot.paused !== undefined) store.setPaused(snapshot.paused);
  if (snapshot.market_open !== undefined) store.setMarketOpen(snapshot.market_open);
  if (snapshot.simulate_24_7 !== undefined) {
    store.setTradingMode(snapshot.simulate_24_7 ? 'paper' : 'live');
  }
}
