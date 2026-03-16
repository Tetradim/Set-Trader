import { useStore } from '@/stores/useStore';
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { TrendingUp, TrendingDown, BarChart3 } from 'lucide-react';

export function HistoryTab() {
  const trades = useStore((s) => s.trades);
  const [history, setHistory] = useState<any[]>([]);
  const [stats, setStats] = useState({ wins: 0, losses: 0, total: 0, winRate: 0 });

  useEffect(() => {
    apiFetch('/api/trades?limit=100')
      .then((data) => {
        setHistory(data);
        const wins = data.filter((t: any) => t.pnl > 0).length;
        const losses = data.filter((t: any) => t.pnl < 0).length;
        const total = data.length;
        setStats({
          wins,
          losses,
          total,
          winRate: wins + losses > 0 ? Math.round((wins / (wins + losses)) * 100) : 0,
        });
      })
      .catch(() => {});
  }, [trades.length]);

  const allTrades = history.length > 0 ? history : trades;

  const sideColors: Record<string, string> = {
    BUY: 'text-emerald-400 bg-emerald-400/10',
    SELL: 'text-blue-400 bg-blue-400/10',
    STOP: 'text-red-400 bg-red-400/10',
    TRAILING_STOP: 'text-amber-400 bg-amber-400/10',
  };

  return (
    <div className="space-y-6" data-testid="history-tab">
      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Total Trades" value={stats.total} />
        <StatCard label="Wins" value={stats.wins} color="text-emerald-400" />
        <StatCard label="Losses" value={stats.losses} color="text-red-400" />
        <div className="glass rounded-xl border border-border p-4">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Win Rate</p>
          <div className="flex items-center gap-2 mt-1">
            <BarChart3 size={16} className="text-primary" />
            <span className="font-mono text-xl font-bold text-foreground">{stats.winRate}%</span>
          </div>
          <div className="w-full h-1 bg-secondary rounded-full mt-2 overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all"
              style={{ width: `${stats.winRate}%` }}
            />
          </div>
        </div>
      </div>

      {/* Trade History Table */}
      <div className="glass rounded-xl border border-border overflow-hidden">
        <table className="w-full" data-testid="history-table">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Time</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Symbol</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Side</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold text-right">Price</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold text-right">Qty</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold text-right">P&L</th>
              <th className="px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Reason</th>
            </tr>
          </thead>
          <tbody>
            {allTrades.map((t: any) => (
              <tr key={t.id} className="border-b border-border/50 hover:bg-secondary/30 transition-colors" data-testid={`history-row-${t.id}`}>
                <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                  {new Date(t.timestamp).toLocaleString()}
                </td>
                <td className="px-4 py-2.5 font-bold text-sm text-foreground">{t.symbol}</td>
                <td className="px-4 py-2.5">
                  <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${sideColors[t.side] || ''}`}>
                    {t.side}
                  </span>
                </td>
                <td className="px-4 py-2.5 font-mono text-sm text-right text-foreground">${t.price?.toFixed(2)}</td>
                <td className="px-4 py-2.5 font-mono text-sm text-right text-muted-foreground">{t.quantity?.toFixed(4)}</td>
                <td className={`px-4 py-2.5 font-mono text-sm text-right font-bold ${
                  (t.pnl || 0) > 0 ? 'text-emerald-400' : (t.pnl || 0) < 0 ? 'text-red-400' : 'text-muted-foreground'
                }`}>
                  {(t.pnl || 0) !== 0 ? `${t.pnl > 0 ? '+' : ''}$${t.pnl?.toFixed(2)}` : '-'}
                </td>
                <td className="px-4 py-2.5 text-xs text-muted-foreground max-w-[200px] truncate">{t.reason || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {allTrades.length === 0 && (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-xs" data-testid="no-history">
            <p>No trade history yet</p>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="glass rounded-xl border border-border p-4">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className={`font-mono text-xl font-bold tracking-tight mt-1 ${color || 'text-foreground'}`}>
        {value}
      </p>
    </div>
  );
}
