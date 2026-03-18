import { useStore, PositionData } from '@/stores/useStore';
import { useEffect, useState, useCallback } from 'react';
import { apiFetch } from '@/lib/api';
import { TrendingUp, TrendingDown, Briefcase, X, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { toast } from 'sonner';

export function PositionsTab() {
  const wsPositions = useStore((s) => s.positions);
  const [apiPositions, setApiPositions] = useState<PositionData[]>([]);
  const [sellTarget, setSellTarget] = useState<PositionData | null>(null);
  const [pendingSells, setPendingSells] = useState<Record<string, { limit_price: number; quantity: number }>>({});

  useEffect(() => {
    apiFetch('/api/positions')
      .then((data) => setApiPositions(data || []))
      .catch(() => {});
    apiFetch('/api/positions/pending-sells')
      .then((data) => setPendingSells(data || {}))
      .catch(() => {});
  }, []);

  const wsArr = Object.values(wsPositions).filter((p) => p && p.quantity > 0);
  const positions: PositionData[] = wsArr.length > 0 ? wsArr : apiPositions;

  const totalValue = positions.reduce((a, p) => a + (p.market_value ?? p.current_price * p.quantity ?? 0), 0);
  const totalUnrealized = positions.reduce((a, p) => a + (p.unrealized_pnl ?? 0), 0);

  const safe = (val: number | undefined | null, decimals = 2) => {
    if (val === undefined || val === null || isNaN(val)) return '0.00';
    return val.toFixed(decimals);
  };

  const handleSellComplete = useCallback(() => {
    setSellTarget(null);
    apiFetch('/api/positions').then((d) => setApiPositions(d || [])).catch(() => {});
    apiFetch('/api/positions/pending-sells').then((d) => setPendingSells(d || {})).catch(() => {});
  }, []);

  const handleCancelPending = useCallback(async (sym: string) => {
    try {
      await apiFetch(`/api/positions/${sym}/pending-sell`, { method: 'DELETE' });
      toast.success(`Pending limit sell for ${sym} cancelled`);
      setPendingSells((prev) => {
        const copy = { ...prev };
        delete copy[sym];
        return copy;
      });
    } catch (e: any) {
      toast.error(e.message || 'Failed to cancel');
    }
  }, []);

  return (
    <div className="space-y-6" data-testid="positions-tab">
      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <SummaryCard
          label="Open Positions"
          value={positions.length.toString()}
          icon={<Briefcase size={16} className="text-primary" />}
        />
        <SummaryCard
          label="Total Market Value"
          value={`$${safe(totalValue)}`}
        />
        <SummaryCard
          label="Unrealized P&L"
          value={`${totalUnrealized >= 0 ? '+' : ''}$${safe(totalUnrealized)}`}
          positive={totalUnrealized >= 0}
        />
      </div>

      {/* Pending Limit Sells */}
      {Object.keys(pendingSells).length > 0 && (
        <div className="glass rounded-xl border border-amber-500/30 p-4 space-y-2" data-testid="pending-sells-section">
          <p className="text-xs font-bold text-amber-400 uppercase tracking-wider">Pending Limit Sells</p>
          <div className="space-y-1.5">
            {Object.entries(pendingSells).map(([sym, order]) => (
              <div key={sym} className="flex items-center justify-between bg-amber-500/5 rounded-lg px-3 py-2 border border-amber-500/20">
                <div className="flex items-center gap-3">
                  <span className="font-bold text-sm text-foreground">{sym}</span>
                  <span className="text-xs text-muted-foreground">
                    Sell {safe(order.quantity, 4)} shares @ <span className="text-amber-400 font-bold">${safe(order.limit_price)}</span>
                  </span>
                </div>
                <button
                  onClick={() => handleCancelPending(sym)}
                  className="text-xs text-red-400 hover:text-red-300 font-medium px-2 py-1 rounded hover:bg-red-500/10 transition-colors"
                  data-testid={`cancel-pending-sell-${sym}`}
                >
                  Cancel
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Table */}
      <div className="glass rounded-xl border border-border overflow-hidden">
        <table className="w-full" data-testid="positions-table">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Symbol</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold text-right">Qty</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold text-right">Avg Entry</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold text-right">Current</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold text-right">Mkt Value</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold text-right">Unrealized P&L</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold text-center">Action</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => {
              const unrealized = pos.unrealized_pnl ?? 0;
              const mktVal = pos.market_value ?? (pos.current_price ?? 0) * (pos.quantity ?? 0);
              const hasPending = !!pendingSells[pos.symbol];
              return (
                <tr key={pos.symbol} className="border-b border-border/50 hover:bg-secondary/30 transition-colors" data-testid={`position-row-${pos.symbol}`}>
                  <td className="px-4 py-3 font-bold text-sm text-foreground">{pos.symbol}</td>
                  <td className="px-4 py-3 font-mono text-sm text-right text-foreground">{safe(pos.quantity, 4)}</td>
                  <td className="px-4 py-3 font-mono text-sm text-right text-muted-foreground">${safe(pos.avg_entry)}</td>
                  <td className="px-4 py-3 font-mono text-sm text-right text-foreground">${safe(pos.current_price)}</td>
                  <td className="px-4 py-3 font-mono text-sm text-right text-foreground">${safe(mktVal)}</td>
                  <td className={`px-4 py-3 font-mono text-sm text-right font-bold ${unrealized >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    <span className="flex items-center justify-end gap-1">
                      {unrealized >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                      {unrealized >= 0 ? '+' : ''}${safe(unrealized)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={() => setSellTarget(pos)}
                      disabled={hasPending}
                      data-testid={`sell-btn-${pos.symbol}`}
                      className={`text-xs font-bold px-3 py-1.5 rounded-lg transition-all ${
                        hasPending
                          ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30 cursor-not-allowed'
                          : 'bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20 hover:border-red-500/50'
                      }`}
                    >
                      {hasPending ? 'Pending' : 'Sell'}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {positions.length === 0 && (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-xs" data-testid="no-positions">
            <p>No open positions</p>
            <p className="mt-1 text-muted-foreground/60">Positions will appear when the bot executes trades</p>
          </div>
        )}
      </div>

      {/* Sell Modal */}
      {sellTarget && (
        <SellModal
          position={sellTarget}
          onClose={() => setSellTarget(null)}
          onComplete={handleSellComplete}
        />
      )}
    </div>
  );
}


function SellModal({ position, onClose, onComplete }: {
  position: PositionData;
  onClose: () => void;
  onComplete: () => void;
}) {
  const [orderType, setOrderType] = useState<'market' | 'limit'>('market');
  const [limitPrice, setLimitPrice] = useState('');
  const [loading, setLoading] = useState(false);
  const simulate247 = useStore((s) => s.simulate247);

  const currentPrice = position.current_price ?? 0;
  const entry = position.avg_entry ?? 0;
  const qty = position.quantity ?? 0;
  const mktValue = currentPrice * qty;
  const estPnl = orderType === 'market'
    ? (currentPrice - entry) * qty
    : limitPrice ? (parseFloat(limitPrice) - entry) * qty : 0;

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const body: any = { order_type: orderType };
      if (orderType === 'limit') {
        const lp = parseFloat(limitPrice);
        if (!lp || lp <= 0) {
          toast.error('Enter a valid limit price');
          setLoading(false);
          return;
        }
        body.limit_price = lp;
      }
      const result = await apiFetch(`/api/positions/${position.symbol}/sell`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      if (result.status === 'executed') {
        toast.success(
          `Sold ${position.symbol} @ $${result.price.toFixed(2)} — P&L: ${result.pnl >= 0 ? '+' : ''}$${result.pnl.toFixed(2)}`
        );
      } else if (result.status === 'pending') {
        toast.success(`Limit sell placed for ${position.symbol} @ $${result.limit_price.toFixed(2)}`);
      }
      onComplete();
    } catch (e: any) {
      toast.error(e.message || 'Sell failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-md border-border" data-testid="sell-modal">
        <DialogHeader>
          <DialogTitle className="text-foreground flex items-center gap-2">
            Sell {position.symbol}
            <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${
              simulate247
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            }`}>
              {simulate247 ? 'PAPER' : 'LIVE'}
            </span>
          </DialogTitle>
          <DialogDescription className="text-muted-foreground text-xs">
            Close your entire position of {qty.toFixed(4)} shares
          </DialogDescription>
        </DialogHeader>

        {/* Position info */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <InfoCell label="Quantity" value={qty.toFixed(4)} />
          <InfoCell label="Avg Entry" value={`$${entry.toFixed(2)}`} />
          <InfoCell label="Current Price" value={`$${currentPrice.toFixed(2)}`} highlight />
          <InfoCell label="Market Value" value={`$${mktValue.toFixed(2)}`} />
        </div>

        {/* Order Type Toggle */}
        <div className="space-y-3 mt-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Order Type</p>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => setOrderType('market')}
              data-testid="sell-type-market"
              className={`text-sm font-bold py-2.5 rounded-lg border transition-all ${
                orderType === 'market'
                  ? 'bg-red-500/15 text-red-400 border-red-500/40'
                  : 'bg-secondary/30 text-muted-foreground border-border hover:border-border/80'
              }`}
            >
              Market
            </button>
            <button
              onClick={() => setOrderType('limit')}
              data-testid="sell-type-limit"
              className={`text-sm font-bold py-2.5 rounded-lg border transition-all ${
                orderType === 'limit'
                  ? 'bg-amber-500/15 text-amber-400 border-amber-500/40'
                  : 'bg-secondary/30 text-muted-foreground border-border hover:border-border/80'
              }`}
            >
              Limit
            </button>
          </div>

          {orderType === 'market' && (
            <div className="rounded-lg bg-red-500/5 border border-red-500/20 p-3">
              <p className="text-xs text-red-400 font-medium">Sell immediately at current market price</p>
              <p className="text-lg font-bold text-foreground mt-1 font-mono">${currentPrice.toFixed(2)}</p>
            </div>
          )}

          {orderType === 'limit' && (
            <div className="space-y-2">
              <div className="rounded-lg bg-amber-500/5 border border-amber-500/20 p-3">
                <p className="text-xs text-amber-400 font-medium mb-2">Sell when price reaches your target</p>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground font-mono text-sm">$</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={limitPrice}
                    onChange={(e) => setLimitPrice(e.target.value)}
                    placeholder={currentPrice.toFixed(2)}
                    data-testid="sell-limit-price-input"
                    className="w-full pl-7 pr-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-sm focus:border-amber-500/50 focus:outline-none"
                    autoFocus
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Estimated P&L */}
        <div className="rounded-lg bg-secondary/30 border border-border p-3 mt-1">
          <div className="flex justify-between items-center">
            <span className="text-xs text-muted-foreground">Estimated P&L</span>
            <span className={`font-mono font-bold text-sm ${estPnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {estPnl >= 0 ? '+' : ''}${estPnl.toFixed(2)}
            </span>
          </div>
          <div className="flex justify-between items-center mt-1">
            <span className="text-xs text-muted-foreground">Est. Total Value</span>
            <span className="font-mono text-xs text-foreground">
              ${orderType === 'market' ? mktValue.toFixed(2) : limitPrice ? (parseFloat(limitPrice) * qty).toFixed(2) : '—'}
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-3 mt-2">
          <button
            onClick={onClose}
            className="flex-1 text-sm font-medium py-2.5 rounded-lg border border-border text-muted-foreground hover:bg-secondary/30 transition-colors"
            data-testid="sell-cancel-btn"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || (orderType === 'limit' && (!limitPrice || parseFloat(limitPrice) <= 0))}
            data-testid="sell-confirm-btn"
            className={`flex-1 text-sm font-bold py-2.5 rounded-lg transition-all flex items-center justify-center gap-2 ${
              orderType === 'market'
                ? 'bg-red-500/20 text-red-400 border border-red-500/40 hover:bg-red-500/30 disabled:opacity-40'
                : 'bg-amber-500/20 text-amber-400 border border-amber-500/40 hover:bg-amber-500/30 disabled:opacity-40'
            }`}
          >
            {loading && <Loader2 size={14} className="animate-spin" />}
            {orderType === 'market' ? 'Sell Now' : 'Place Limit Sell'}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}


function InfoCell({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="rounded-lg bg-secondary/20 border border-border/50 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={`font-mono text-sm font-bold mt-0.5 ${highlight ? 'text-primary' : 'text-foreground'}`}>{value}</p>
    </div>
  );
}


function SummaryCard({ label, value, positive, icon }: { label: string; value: string; positive?: boolean; icon?: React.ReactNode }) {
  return (
    <div className="glass rounded-xl border border-border p-4">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <div className="flex items-center gap-2 mt-1">
        {icon}
        <p className={`font-mono text-xl font-bold tracking-tight ${
          positive === undefined ? 'text-foreground' : positive ? 'text-emerald-400' : 'text-red-400'
        }`}>
          {value}
        </p>
      </div>
    </div>
  );
}
