import { useStore, PositionData } from '@/stores/useStore';
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { TrendingUp, TrendingDown, Briefcase } from 'lucide-react';

export function PositionsTab() {
  const wsPositions = useStore((s) => s.positions);
  const [apiPositions, setApiPositions] = useState<PositionData[]>([]);

  // Fetch from REST as fallback / initial load
  useEffect(() => {
    apiFetch('/api/positions')
      .then((data) => setApiPositions(data || []))
      .catch(() => {});
  }, []);

  // Merge: prefer WS data (real-time), fall back to API data
  const wsArr = Object.values(wsPositions).filter((p) => p && p.quantity > 0);
  const positions: PositionData[] = wsArr.length > 0 ? wsArr : apiPositions;

  const totalValue = positions.reduce((a, p) => a + (p.market_value ?? p.current_price * p.quantity ?? 0), 0);
  const totalUnrealized = positions.reduce((a, p) => a + (p.unrealized_pnl ?? 0), 0);

  const safe = (val: number | undefined | null, decimals = 2) => {
    if (val === undefined || val === null || isNaN(val)) return '0.00';
    return val.toFixed(decimals);
  };

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
            {positions.map((pos) => {
              const unrealized = pos.unrealized_pnl ?? 0;
              const mktVal = pos.market_value ?? (pos.current_price ?? 0) * (pos.quantity ?? 0);
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
