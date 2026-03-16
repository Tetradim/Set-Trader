import { create } from 'zustand';

export interface TickerConfig {
  id: string;
  symbol: string;
  base_power: number;
  avg_days: number;
  buy_offset: number;
  buy_percent: boolean;
  buy_order_type: string;
  sell_offset: number;
  sell_percent: boolean;
  sell_order_type: string;
  stop_offset: number;
  stop_percent: boolean;
  stop_order_type: string;
  trailing_enabled: boolean;
  trailing_percent: number;
  trailing_percent_mode: boolean;
  trailing_order_type: string;
  wait_day_after_buy: boolean;
  enabled: boolean;
  strategy: string;
  created_at: string;
  custom_backup?: Record<string, any>;
}

export interface TradeLog {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL' | 'STOP' | 'TRAILING_STOP';
  price: number;
  quantity: number;
  reason: string;
  pnl: number;
  timestamp: string;
}

export interface PositionData {
  symbol: string;
  quantity: number;
  avg_entry: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
}

export interface PricePoint {
  time: number;
  price: number;
}

interface BotState {
  // Connection
  connected: boolean;
  setConnected: (s: boolean) => void;

  // Bot status
  running: boolean;
  paused: boolean;
  marketOpen: boolean;
  setRunning: (s: boolean) => void;
  setPaused: (s: boolean) => void;
  setMarketOpen: (s: boolean) => void;

  // Tickers
  tickers: Record<string, TickerConfig>;
  setTickers: (t: TickerConfig[]) => void;
  addTicker: (t: TickerConfig) => void;
  updateTicker: (symbol: string, updates: Partial<TickerConfig>) => void;
  removeTicker: (symbol: string) => void;

  // Prices
  prices: Record<string, number>;
  setPrices: (p: Record<string, number>) => void;

  // Price history for charts
  priceHistory: Record<string, PricePoint[]>;
  appendPriceHistory: (prices: Record<string, number>) => void;

  // Chart enabled per ticker
  chartEnabled: Record<string, boolean>;
  toggleChart: (symbol: string) => void;

  // Profits
  profits: Record<string, number>;
  setProfits: (p: Record<string, number>) => void;

  // Positions
  positions: Record<string, PositionData>;
  setPositions: (p: Record<string, PositionData>) => void;

  // Trade logs
  trades: TradeLog[];
  addTrade: (t: TradeLog) => void;
  setTrades: (t: TradeLog[]) => void;

  // Active tab
  activeTab: string;
  setActiveTab: (tab: string) => void;

  // Settings
  simulate247: boolean;
  setSimulate247: (s: boolean) => void;
  telegramToken: string;
  telegramChatIds: string[];
  setTelegramConfig: (token: string, chatIds: string[]) => void;

  // Cash reserve from Take Profit
  cashReserve: number;
  setCashReserve: (v: number) => void;

  // Custom step increments
  incrementStep: number;
  decrementStep: number;
  setIncrementStep: (v: number) => void;
  setDecrementStep: (v: number) => void;
}

export const useStore = create<BotState>((set) => ({
  connected: false,
  setConnected: (connected) => set({ connected }),

  running: false,
  paused: false,
  marketOpen: false,
  setRunning: (running) => set({ running }),
  setPaused: (paused) => set({ paused }),
  setMarketOpen: (marketOpen) => set({ marketOpen }),

  tickers: {},
  setTickers: (arr) => set({
    tickers: arr.reduce((acc, t) => ({ ...acc, [t.symbol]: t }), {} as Record<string, TickerConfig>)
  }),
  addTicker: (t) => set((state) => ({
    tickers: { ...state.tickers, [t.symbol]: t }
  })),
  updateTicker: (symbol, updates) => set((state) => {
    const existing = state.tickers[symbol];
    if (!existing) return state;
    return { tickers: { ...state.tickers, [symbol]: { ...existing, ...updates } } };
  }),
  removeTicker: (symbol) => set((state) => {
    const copy = { ...state.tickers };
    delete copy[symbol];
    return { tickers: copy };
  }),

  prices: {},
  setPrices: (prices) => set({ prices }),

  priceHistory: {},
  appendPriceHistory: (prices) => set((state) => {
    const now = Date.now();
    const updated = { ...state.priceHistory };
    for (const [sym, price] of Object.entries(prices)) {
      const arr = updated[sym] || [];
      const next = [...arr, { time: now, price }];
      updated[sym] = next.length > 120 ? next.slice(-120) : next;
    }
    return { priceHistory: updated };
  }),

  chartEnabled: {},
  toggleChart: (symbol) => set((state) => ({
    chartEnabled: { ...state.chartEnabled, [symbol]: !state.chartEnabled[symbol] }
  })),

  profits: {},
  setProfits: (profits) => set({ profits }),

  positions: {},
  setPositions: (positions) => set({ positions }),

  trades: [],
  addTrade: (t) => set((state) => ({
    trades: [t, ...state.trades].slice(0, 200)
  })),
  setTrades: (trades) => set({ trades }),

  activeTab: 'watchlist',
  setActiveTab: (activeTab) => set({ activeTab }),

  simulate247: false,
  setSimulate247: (simulate247) => set({ simulate247 }),
  telegramToken: '',
  telegramChatIds: [],
  setTelegramConfig: (telegramToken, telegramChatIds) => set({ telegramToken, telegramChatIds }),

  cashReserve: 0,
  setCashReserve: (cashReserve) => set({ cashReserve }),

  incrementStep: 0.5,
  decrementStep: 0.5,
  setIncrementStep: (incrementStep) => set({ incrementStep }),
  setDecrementStep: (decrementStep) => set({ decrementStep }),
}));
