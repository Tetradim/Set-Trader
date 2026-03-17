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
import { PlusCircle, AlertTriangle } from 'lucide-react';

export function AddTickerDialog() {
  const { send } = useWebSocket();
  const accountBalance = useStore((s) => s.accountBalance);
  const tickers = useStore((s) => s.tickers);
  const [open, setOpen] = useState(false);
  const [symbol, setSymbol] = useState('');
  const [basePower, setBasePower] = useState(100);
  const [error, setError] = useState('');

  const currentAllocated = Object.values(tickers).reduce((s, t) => s + (t.base_power ?? 0), 0);
  const currentAvailable = accountBalance - currentAllocated;
  const wouldExceed = accountBalance > 0 && basePower > currentAvailable;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const sym = symbol.toUpperCase().trim();
    if (sym.length < 1 || sym.length > 10) {
      setError('Symbol must be 1-10 characters');
      return;
    }
    if (!/^[A-Z0-9.]+$/.test(sym)) {
      setError('Invalid symbol format');
      return;
    }
    if (basePower < 1 || basePower > 1000000) {
      setError('Base power must be $1 - $1,000,000');
      return;
    }
    send('ADD_TICKER', { symbol: sym, base_power: basePower });
    setSymbol('');
    setBasePower(100);
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
            Enter the stock symbol and allocation amount to start tracking.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div>
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">
              Symbol
            </label>
            <input
              data-testid="ticker-symbol-input"
              required
              value={symbol}
              onChange={(e) => { setSymbol(e.target.value.toUpperCase()); setError(''); }}
              placeholder="e.g. AAPL, TSLA, NVDA"
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono uppercase placeholder:lowercase placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background"
            />
          </div>
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

            {/* Budget context */}
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

            {/* Over-allocation warning */}
            {wouldExceed && (
              <div className="mt-2 flex items-center gap-1.5 text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-2.5 py-1.5" data-testid="add-ticker-over-warning">
                <AlertTriangle size={11} className="shrink-0" />
                <span>This allocation exceeds your available balance by ${(basePower - currentAvailable).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}. You can still add it, but your account will be over-allocated.</span>
              </div>
            )}
          </div>
          {error && (
            <p className="text-xs text-red-400" data-testid="add-ticker-error">{error}</p>
          )}
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
