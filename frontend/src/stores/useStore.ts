import { create } from 'zustand';

interface TradeLog {
  id: string;
  symbol: string;
  type: 'BUY' | 'SELL' | 'STOP';
  price: number;
  timestamp: string;
}

interface Ticker {
  symbol: string;
  base_power: number;
  enabled: boolean;
  profit: number;
  status: 'Waiting' | 'In-trade' | 'Pending';
}

interface BotState {
  tickers: Record<string, Ticker>;
  connected: boolean;
  paused: boolean;
  logs: TradeLog[];
  // Actions
  setTickers: (tickers: Record<string, Ticker>) => void;
  updateTicker: (symbol: string, updates: Partial<Ticker>) => void;
  setConnected: (status: boolean) => void;
  togglePause: () => void;
  removeTicker: (symbol: string) => void;
  addLog: (log: TradeLog) => void;
}

export const useStore = create<BotState>((set) => ({
  tickers: {},
  connected: false,
  paused: false,
  logs: [],

  setTickers: (tickers) => set({ tickers }),

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

  togglePause: () => set((state) => ({ 
    paused: !state.paused 
  })),

  removeTicker: (symbol) =>
    set((state) => {
      const newTickers = { ...state.tickers };
      delete newTickers[symbol];
      return { tickers: newTickers };
    }),

  addLog: (log) =>
    set((state) => ({
      logs: [log, ...state.logs].slice(0, 50), // Keep the last 50 entries
    })),
}));