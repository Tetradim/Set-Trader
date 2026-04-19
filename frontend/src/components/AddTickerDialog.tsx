import React, { useState } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useStore } from '@/stores/useStore';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { PlusCircle, AlertTriangle, ChevronDown } from 'lucide-react';

const MARKET_OPTIONS = [
  { code: 'US',     label: 'United States (NYSE/NASDAQ)', flag: '🇺🇸', suffix: '',    hint: 'AAPL, TSLA, NVDA' },
  { code: 'HK',     label: 'Hong Kong (HKEX)',            flag: '🇭🇰', suffix: '.HK', hint: '0700.HK, 9988.HK' },
  { code: 'AU',     label: 'Australia (ASX)',             flag: '🇦🇺', suffix: '.AX', hint: 'BHP.AX, CBA.AX' },
  { code: 'UK',     label: 'United Kingdom (LSE)',        flag: '🇬🇧', suffix: '.L',  hint: 'BARC.L, HSBA.L' },
  { code: 'CA',     label: 'Canada (TSX)',                flag: '🇨🇦', suffix: '.TO', hint: 'RY.TO, TD.TO' },
  { code: 'CN_SS',  label: 'China Shanghai (SSE)',        flag: '🇨🇳', suffix: '.SS', hint: '600036.SS' },
  { code: 'CN_SZ',  label: 'China Shenzhen (SZSE)',       flag: '🇨🇳', suffix: '.SZ', hint: '000001.SZ' },
];

function detectMarketFromSymbol(sym: string): string {
  const s = sym.toUpperCase();
  if (s.endsWith('.HK')) return 'HK';
  if (s.endsWith('.AX')) return 'AU';
  if (s.endsWith('.L'))  return 'UK';
  if (s.endsWith('.TO') || s.endsWith('.V')) return 'CA';
  if (s.endsWith('.SS')) return 'CN_SS';
  if (s.endsWith('.SZ')) return 'CN_SZ';
  return 'US';
}

export function AddTickerDialog() {
  const { send } = useWebSocket();
  const accountBalance = useStore((s) => s.accountBalance);
  const tickers = useStore((s) => s.tickers);
  const [open, setOpen] = useState(false);
  const [symbol, setSymbol] = useState('');
  const [basePower, setBasePower] = useState(100);
  const [market, setMarket] = useState('US');
  const [error, setError] = useState('');

  const currentAllocated = Object.values(tickers).reduce((s, t) => s + (t.base_power ?? 0), 0);
  const currentAvailable = accountBalance - currentAllocated;
  const wouldExceed = accountBalance > 0 && basePower > currentAvailable;

  const selectedMarket = MARKET_OPTIONS.find((m) => m.code === market) ?? MARKET_OPTIONS[0];

  // Auto-detect market from typed symbol suffix
  const handleSymbolChange = (val: string) => {
    const upper = val.toUpperCase();
    setSymbol(upper);
    setError('');
    const detected = detectMarketFromSymbol(upper);
    setMarket(detected);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const sym = symbol.toUpperCase().trim();
    if (sym.length < 1 || sym.length > 15) {
      setError('Symbol must be 1-15 characters');
      return;
    }
    if (!/^[A-Z0-9.]+$/.test(sym)) {
      setError('Invalid symbol format (letters, numbers, dots only)');
      return;
    }
    if (basePower < 1 || basePower > 1000000) {
      setError('Base power must be $1 - $1,000,000');
      return;
    }
    send('ADD_TICKER', { symbol: sym, base_power: basePower, market });
    setSymbol('');
    setBasePower(100);
    setMarket('US');
    setError('');
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button
          data-testid="add-ticker-btn"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary/20 text-primary border border-primary/30 hover:bg-primary/30 transition-all"
        >
          <PlusCircle size={13} /> Add Stock
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md glass border-border" data-testid="add-ticker-dialog">
        <DialogHeader>
          <DialogTitle className="text-foreground">Add Ticker Symbol</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Enter the symbol with its exchange suffix for foreign stocks (e.g. <span className="font-mono text-foreground/80">BHP.AX</span>).
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          {/* Symbol */}
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">
              Symbol
            </label>
            <input
              data-testid="ticker-symbol-input"
              required
              value={symbol}
              onChange={(e) => handleSymbolChange(e.target.value)}
              placeholder={`e.g. ${selectedMarket.hint}`}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono uppercase placeholder:lowercase placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background"
            />
          </div>

          {/* Market selector */}
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">
              Exchange / Market
            </label>
            <div className="relative">
              <select
                data-testid="ticker-market-select"
                value={market}
                onChange={(e) => setMarket(e.target.value)}
                className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background appearance-none pr-8"
              >
                {MARKET_OPTIONS.map((m) => (
                  <option key={m.code} value={m.code}>
                    {m.flag}  {m.label}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            </div>
            {selectedMarket.suffix && (
              <p className="text-[10px] text-muted-foreground/60 mt-1">
                Required suffix: <span className="font-mono text-foreground/70">{selectedMarket.suffix}</span> — e.g. <span className="font-mono text-foreground/70">{selectedMarket.hint.split(',')[0].trim()}</span>
              </p>
            )}
          </div>

          {/* Buy power */}
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">
              Buy Power ($)
            </label>
            <input
              data-testid="ticker-power-input"
              type="number"
              value={basePower}
              onChange={(e) => { setBasePower(Number(e.target.value)); setError(''); }}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background"
            />
            {accountBalance > 0 && (
              <div className="mt-2 flex items-center justify-between text-[10px] font-mono">
                <span className="text-muted-foreground">
                  Available: <span className={currentAvailable >= 0 ? 'text-emerald-400' : 'text-red-400'}>${currentAvailable.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </span>
                <span className="text-muted-foreground">
                  After: <span className={wouldExceed ? 'text-red-400' : 'text-emerald-400'}>${(currentAvailable - basePower).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </span>
              </div>
            )}
            {wouldExceed && (
              <div className="mt-2 flex items-center gap-1.5 text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-2.5 py-1.5" data-testid="add-ticker-over-warning">
                <AlertTriangle size={11} className="shrink-0" />
                <span>This allocation exceeds available balance by ${(basePower - currentAvailable).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}. You can still add it.</span>
              </div>
            )}
          </div>

          {error && <p className="text-xs text-red-400" data-testid="add-ticker-error">{error}</p>}

          <button
            type="submit"
            data-testid="add-ticker-submit"
            className={`w-full py-2.5 rounded-lg font-semibold text-sm transition-all shadow-lg ${
              wouldExceed
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 shadow-amber-500/10'
                : 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-primary/25'
            }`}
          >
            {wouldExceed ? 'Add Anyway (Over-Allocated)' : 'Add to Watchlist'}
          </button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
