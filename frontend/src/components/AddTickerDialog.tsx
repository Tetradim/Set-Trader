import React, { useEffect, useState } from 'react';
import { useStore } from '@/stores/useStore';
import { apiFetch } from '@/lib/api';
import { detectMarketCode } from '@/lib/market-utils';
import { uiLog } from '@/lib/clientLogger';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { PlusCircle, AlertTriangle, ChevronDown } from 'lucide-react';

type MarketOption = {
  code: string;
  name: string;
  flag: string;
  yf_suffix: string;
  ticker_examples: string[];
};

const FALLBACK_MARKET: MarketOption = {
  code: 'US',
  name: 'United States (NYSE / NASDAQ)',
  flag: '🇺🇸',
  yf_suffix: '',
  ticker_examples: ['AAPL', 'TSLA', 'NVDA'],
};

type AddTickerDialogProps = {
  trigger?: React.ReactNode;
}

export function AddTickerDialog({ trigger }: AddTickerDialogProps = {}) {
  const accountBalance = useStore((s) => s.accountBalance);
  const tickers = useStore((s) => s.tickers);
  const addTicker = useStore((s) => s.addTicker);
  const setAccountBalance = useStore((s) => s.setAccountBalance);
  const [open, setOpen] = useState(false);
  const [symbol, setSymbol] = useState('');
  const [basePower, setBasePower] = useState(100);
  const [market, setMarket] = useState('US');
  const [marketOptions, setMarketOptions] = useState<MarketOption[]>([FALLBACK_MARKET]);
  const [marketsLoaded, setMarketsLoaded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const currentAllocated = Object.values(tickers).reduce((sum, ticker) => sum + (ticker.base_power ?? 0), 0);
  const currentAvailable = accountBalance - currentAllocated;
  const wouldExceed = accountBalance > 0 && basePower > currentAvailable;
  const selectedMarket = marketOptions.find((option) => option.code === market) ?? marketOptions[0] ?? FALLBACK_MARKET;
  const selectedHint = selectedMarket.ticker_examples?.slice(0, 3).join(', ') || 'AAPL, TSLA, NVDA';

  useEffect(() => {
    if (!open || marketsLoaded) return;
    let cancelled = false;
    apiFetch('/api/markets')
      .then((data) => {
        const options = ((data?.markets ?? []) as MarketOption[]).filter((option) => option.code && option.name);
        if (!cancelled && options.length) setMarketOptions(options);
      })
      .catch((err) => uiLog.error('add_ticker.markets_load_failed', err))
      .finally(() => {
        if (!cancelled) setMarketsLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open, marketsLoaded]);

  useEffect(() => {
    function handleTickerError(event: Event) {
      const detail = (event as CustomEvent<{ error?: string; symbol?: string }>).detail;
      setError(detail?.error || 'Failed to add ticker');
      setOpen(true);
    }

    window.addEventListener('ticker-error', handleTickerError);
    return () => window.removeEventListener('ticker-error', handleTickerError);
  }, []);

  const handleSymbolChange = (value: string) => {
    const upper = value.toUpperCase();
    setSymbol(upper);
    setError('');
    const detected = detectMarketCode({ symbol: upper });
    if (marketOptions.some((option) => option.code === detected)) setMarket(detected);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const sym = symbol.toUpperCase().trim();
    if (sym.length < 1 || sym.length > 20) {
      setError('Symbol must be 1-20 characters');
      return;
    }
    if (!/^[A-Z0-9.-]+$/.test(sym)) {
      setError('Invalid symbol format (letters, numbers, dots, and hyphens only)');
      return;
    }
    if (basePower < 1 || basePower > 1000000) {
      setError('Base power must be $1 - $1,000,000');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const saved = await apiFetch('/api/tickers', {
        method: 'POST',
        body: JSON.stringify({ symbol: sym, base_power: basePower, market }),
      });
      addTicker(saved);
      const allocatedAfterAdd = currentAllocated + (saved.base_power ?? basePower);
      setAccountBalance(accountBalance, allocatedAfterAdd, accountBalance - allocatedAfterAdd);
      setSymbol('');
      setBasePower(100);
      setMarket('US');
      setOpen(false);
    } catch (err: any) {
      setError(err.message || 'Failed to add ticker');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <button
            type="button"
            data-testid="add-ticker-btn"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary/20 text-primary border border-primary/30 hover:bg-primary/30 transition-all"
          >
            <PlusCircle size={13} /> Add Stock
          </button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md glass border-border" data-testid="add-ticker-dialog">
        <DialogHeader>
          <DialogTitle className="text-foreground">Add Ticker Symbol</DialogTitle>
          <DialogDescription className="text-muted-foreground">
            Enter the exchange-specific ticker. Foreign symbols usually need their suffix, such as
            <span className="font-mono text-foreground/80"> 7203.T</span>,
            <span className="font-mono text-foreground/80"> BHP.AX</span>, or
            <span className="font-mono text-foreground/80"> ASML.AS</span>.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div>
            <label htmlFor="ticker-symbol-input" className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">
              Symbol
            </label>
            <input
              id="ticker-symbol-input"
              data-testid="ticker-symbol-input"
              required
              aria-invalid={!!error}
              aria-describedby={error ? 'add-ticker-error' : undefined}
              value={symbol}
              onChange={(event) => handleSymbolChange(event.target.value)}
              placeholder={`e.g. ${selectedHint}`}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono uppercase placeholder:lowercase placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background"
            />
          </div>

          <div>
            <label htmlFor="ticker-market-select" className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">
              Exchange / Market
            </label>
            <div className="relative">
              <select
                id="ticker-market-select"
                data-testid="ticker-market-select"
                value={market}
                onChange={(event) => setMarket(event.target.value)}
                className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background appearance-none pr-8"
              >
                {marketOptions.map((option) => (
                  <option key={option.code} value={option.code}>
                    {option.flag} {option.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            </div>
            {selectedMarket.yf_suffix && (
              <p className="text-[10px] text-muted-foreground/60 mt-1">
                Required suffix: <span className="font-mono text-foreground/70">{selectedMarket.yf_suffix}</span>
                {' '} - e.g. <span className="font-mono text-foreground/70">{selectedMarket.ticker_examples?.[0]}</span>
              </p>
            )}
          </div>

          <div>
            <label htmlFor="ticker-power-input" className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">
              Buy Power ($)
            </label>
            <input
              id="ticker-power-input"
              data-testid="ticker-power-input"
              type="number"
              min={1}
              max={1000000}
              step={1}
              inputMode="numeric"
              aria-invalid={!!error}
              value={basePower}
              onChange={(event) => { setBasePower(Number(event.target.value)); setError(''); }}
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

          {error && <p id="add-ticker-error" className="text-xs text-red-400" role="alert" data-testid="add-ticker-error">{error}</p>}

          <button
            type="submit"
            data-testid="add-ticker-submit"
            disabled={submitting}
            className={`w-full py-2.5 rounded-lg font-semibold text-sm transition-all shadow-lg ${
              wouldExceed
                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 shadow-amber-500/10'
                : 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-primary/25'
            }`}
          >
            {submitting ? 'Adding...' : wouldExceed ? 'Add Anyway (Over-Allocated)' : 'Add to Watchlist'}
          </button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
