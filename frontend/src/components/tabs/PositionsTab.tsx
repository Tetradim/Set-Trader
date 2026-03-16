import { useStore } from '@/stores/useStore';
import { TrendingUp, TrendingDown } from 'lucide-react';

export function PositionsTab() {
  const positions = useStore((s) => Object.values(s.positions));
  const prices = useStore((s) => s.prices);

  const totalValue = positions.reduce((a, p) => a + (p.market_value || 0), 0);
  const totalUnrealized = positions.reduce((a, p) => a + (p.unrealized_pnl || 0), 0);

  return (
    <div className="space-y-6" data-testid="positions-tab">
      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <SummaryCard label="Open Positions" value={positions.length.toString()} />
        <SummaryCard
          label="Total Market Value"
          value={`$${totalValue.toFixed(2)}`}
        />
        <SummaryCard
          label="Unrealized P&L"
          value={`${totalUnrealized >= 0 ? '+' : ''}$${totalUnrealized.toFixed(2)}`}
          positive={totalUnrealized >= 0}
        />
      </div>

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
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => (
              <tr key={pos.symbol} className="border-b border-border/50 hover:bg-secondary/30 transition-colors" data-testid={`position-row-${pos.symbol}`}>
                <td className="px-4 py-3 font-bold text-sm text-foreground">{pos.symbol}</td>
                <td className="px-4 py-3 font-mono text-sm text-right text-foreground">{pos.quantity.toFixed(4)}</td>
                <td className="px-4 py-3 font-mono text-sm text-right text-muted-foreground">${pos.avg_entry.toFixed(2)}</td>
                <td className="px-4 py-3 font-mono text-sm text-right text-foreground">${pos.current_price.toFixed(2)}</td>
                <td className="px-4 py-3 font-mono text-sm text-right text-foreground">${pos.market_value.toFixed(2)}</td>
                <td className={`px-4 py-3 font-mono text-sm text-right font-bold ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  <span className="flex items-center justify-end gap-1">
                    {pos.unrealized_pnl >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                    {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {positions.length === 0 && (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-xs" data-testid="no-positions">
            <p>No open positions</p>
            <p className="mt-1 text-muted-foreground/60">Positions will appear when the bot executes trades</p>
          </div>
        )}
      </div>
    </div>
  );
}

function SummaryCard({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="glass rounded-xl border border-border p-4">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className={`font-mono text-xl font-bold tracking-tight mt-1 ${
        positive === undefined ? 'text-foreground' : positive ? 'text-emerald-400' : 'text-red-400'
      }`}>
        {value}
      </p>
    </div>
  );
}
