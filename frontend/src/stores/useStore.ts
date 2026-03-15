import { create } from 'zustand';

export interface TradeLog {
  id: string;
  symbol: string;
  type: 'BUY' | 'SELL' | 'STOP';
  price: number;
  timestamp: string;
}

// Matches TickerConfig in main.py
export interface Ticker {
  symbol: string;
  base_power: number;
  enabled: boolean;
  avg_days: number;
  buy_offset: number;
  buy_percent: boolean;
  sell_offset: number;
  sell_percent: boolean;
  stop_offset: number;
  stop_percent: boolean;
}

interface BotState {
  tickers: Record<string, Ticker>;
  profits: Record<string, number>; // Backend sends this separately
  connected: boolean;
  paused: boolean;
  logs: TradeLog[];
  
  // Actions
  setTickers: (tickers: Record<string, Ticker>) => void;
  setProfits: (profits: Record<string, number>) => void;
  updateTicker: (symbol: string, updates: Partial<Ticker>) => void;
  setConnected: (status: boolean) => void;
  setPaused: (status: boolean) => void;
  removeTicker: (symbol: string) => void;
  addLog: (log: TradeLog) => void;
}

export const useStore = create<BotState>((set) => ({
  tickers: {},
  profits: {},
  connected: false,
  paused: false,
  logs: [],

  setTickers: (tickers) => set({ tickers }),
  
  setProfits: (profits) => set({ profits }),

  updateTicker: (symbol, updates) =>
    set((state) => {
      const existingTicker = state.tickers[symbol];
      if (!existingTicker) return state;

      return {
        tickers: {
          ...state.tickers,
          [symbol]: { ...existingTicker, ...updates },
        },
      };
    }),

  setConnected: (status) => set({ connected: status }),

  setPaused: (status) => set({ paused: status }),

  removeTicker: (symbol) =>
    set((state) => {
      const newTickers = { ...state.tickers };
      delete newTickers[symbol];
      return { tickers: newTickers };
    }),

  addLog: (log) =>
    set((state) => ({
      logs: [log, ...state.logs].slice(0, 50),
    })),
}));