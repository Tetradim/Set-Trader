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
  compound_profits: boolean;
  max_daily_loss: number;
  max_consecutive_losses: number;
  auto_stopped: boolean;
  auto_stop_reason: string;
  auto_rebracket: boolean;
  rebracket_threshold: number;
  rebracket_spread: number;
  rebracket_cooldown: number;
  rebracket_lookback: number;
  rebracket_buffer: number;
  enabled: boolean;
  strategy: string;
  broker_id: string;
  broker_ids: string[];
  broker_allocations: Record<string, number>;
  sort_order: number;
  created_at: string;
  custom_backup?: Record<string, any>;
  // Partial fills
  partial_fills_enabled: boolean;
  buy_legs: Array<{ alloc_pct: number; offset: number; is_percent: boolean }>;
  sell_legs: Array<{ alloc_pct: number; offset: number; is_percent: boolean }>;
  // Time-based risk rules
  lock_trailing_at_open: boolean;
  halve_stop_at_open: boolean;
  // Opening Bell Mode
  opening_bell_enabled: boolean;
  opening_bell_trail_value: number;
  opening_bell_trail_is_percent: boolean;
  // Market / exchange
  market: string;
  // Pluggable strategy params (stored per-ticker for signal strategies)
  strategy_config: Record<string, number | boolean | string>;
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
  // Rich metadata
  order_type: string;       // MARKET or LIMIT
  rule_mode: string;        // PERCENT or DOLLAR
  entry_price: number;      // avg entry price (for sell-side trades)
  target_price: number;     // trigger/target price
  total_value: number;      // price * quantity
  buy_power: number;        // buying power at time of trade
  avg_price: number;        // moving average price
  sell_target: number;      // configured sell target
  stop_target: number;      // configured stop-loss target
  trail_high: number;       // trailing stop high
  trail_trigger: number;    // trailing stop trigger level
  trail_value: number;      // trailing % or $ value
  trail_mode: string;       // PERCENT or DOLLAR for trailing
  trading_mode: string;     // "paper" or "live"
  broker_results: any[];    // per-broker execution results
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
  liveDuringMarketHours: boolean;
  paperAfterHours: boolean;
  setLiveDuringMarketHours: (v: boolean) => void;
  setPaperAfterHours: (v: boolean) => void;
  telegramToken: string;
  telegramChatIds: string[];
  setTelegramConfig: (token: string, chatIds: string[]) => void;

  // Cash reserve from Take Profit
  cashReserve: number;
  setCashReserve: (v: number) => void;

  // Account balance
  accountBalance: number;
  allocated: number;
  available: number;
  setAccountBalance: (balance: number, allocated: number, available: number) => void;

  // Custom step increments
  incrementStep: number;
  decrementStep: number;
  setIncrementStep: (v: number) => void;
  setDecrementStep: (v: number) => void;

  // Trading mode
  tradingMode: string;
  setTradingMode: (mode: string) => void;

  // Currency display & FX rates
  currencyDisplay: 'usd' | 'native';
  setCurrencyDisplay: (mode: 'usd' | 'native') => void;
  fxRates: Record<string, number>;
  setFxRates: (rates: Record<string, number>) => void;

  // Failed brokers (for flashing chip animation)
  failedBrokers: Record<string, { reason: string; symbol: string; timestamp: number }>;
  setBrokerFailed: (brokerId: string, reason: string, symbol: string) => void;
  clearBrokerFailed: (brokerId: string) => void;

  // Theme settings
  themeMode: 'dark' | 'light';
  accentColor: 'blue' | 'emerald' | 'amber' | 'rose' | 'violet' | 'cyan';
  setThemeMode: (mode: 'dark' | 'light') => void;
  setAccentColor: (color: 'blue' | 'emerald' | 'amber' | 'rose' | 'violet' | 'cyan') => void;

  // Ticker card view settings
  compactMode: boolean;
  setCompactMode: (compact: boolean) => void;
  tickerColors: Record<string, string>;
  setTickerColor: (symbol: string, color: string) => void;
  selectedTickers: string[];
  toggleTickerSelection: (symbol: string) => void;
  clearTickerSelection: () => void;
  selectAllTickers: () => void;
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
  liveDuringMarketHours: false,
  paperAfterHours: false,
  setLiveDuringMarketHours: (liveDuringMarketHours) => set({ liveDuringMarketHours }),
  setPaperAfterHours: (paperAfterHours) => set({ paperAfterHours }),
  telegramToken: '',
  telegramChatIds: [],
  setTelegramConfig: (telegramToken, telegramChatIds) => set({ telegramToken, telegramChatIds }),

  cashReserve: 0,
  setCashReserve: (cashReserve) => set({ cashReserve }),

  accountBalance: 0,
  allocated: 0,
  available: 0,
  setAccountBalance: (accountBalance, allocated, available) => set({ accountBalance, allocated, available }),

  incrementStep: 0.5,
  decrementStep: 0.5,
  setIncrementStep: (incrementStep) => set({ incrementStep }),
  setDecrementStep: (decrementStep) => set({ decrementStep }),

  tradingMode: 'paper',
  setTradingMode: (tradingMode) => set({ tradingMode }),

  currencyDisplay: 'usd',
  setCurrencyDisplay: (currencyDisplay) => set({ currencyDisplay }),
  fxRates: { USD: 1.0 },
  setFxRates: (fxRates) => set({ fxRates }),

  failedBrokers: {},
  setBrokerFailed: (brokerId, reason, symbol) => set((state) => ({
    failedBrokers: {
      ...state.failedBrokers,
      [brokerId]: { reason, symbol, timestamp: Date.now() },
    },
  })),
  clearBrokerFailed: (brokerId) => set((state) => {
    const copy = { ...state.failedBrokers };
    delete copy[brokerId];
    return { failedBrokers: copy };
  }),

  themeMode: 'dark',
  accentColor: 'blue',
  setThemeMode: (themeMode) => set({ themeMode }),
  setAccentColor: (accentColor) => set({ accentColor }),

  compactMode: false,
  setCompactMode: (compactMode) => set({ compactMode }),
  tickerColors: {},
  setTickerColor: (symbol, color) => set((state) => ({
    tickerColors: { ...state.tickerColors, [symbol]: color }
  })),
  selectedTickers: [],
  toggleTickerSelection: (symbol) => set((state) => ({
    selectedTickers: state.selectedTickers.includes(symbol)
      ? state.selectedTickers.filter(s => s !== symbol)
      : [...state.selectedTickers, symbol]
  })),
  clearTickerSelection: () => set({ selectedTickers: [] }),
  selectAllTickers: () => set((state) => ({
    selectedTickers: Object.keys(state.tickers)
  })),
}));
