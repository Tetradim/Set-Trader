import { create } from 'zustand';

export interface TickerConfig {
  id: string;
  symbol: string;
  base_power: number;
  avg_days: number;
  buy_offset: number;
  buy_percent: boolean;
  sell_offset: number;
  sell_percent: boolean;
  stop_offset: number;
  stop_percent: boolean;
  trailing_enabled: boolean;
  trailing_percent: number;
  enabled: boolean;
  strategy: string;
  created_at: string;
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
