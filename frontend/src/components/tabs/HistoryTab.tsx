import { useStore, TradeLog } from '@/stores/useStore';
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { TrendingUp, TrendingDown, BarChart3, ChevronDown, ChevronUp } from 'lucide-react';

interface TradeGroup {
  key: string;
  symbol: string;
  side: string;
  trades: TradeLog[];
  avgPrice: number;
  totalQty: number;
  totalPnl: number;
  firstTime: string;
  lastTime: string;
}

function groupConsecutiveTrades(trades: TradeLog[]): TradeGroup[] {
  const groups: TradeGroup[] = [];
  let current: TradeGroup | null = null;

  for (const t of trades) {
    if (current && current.symbol === t.symbol && current.side === t.side) {
      current.trades.push(t);
      current.totalQty += t.quantity;
      current.totalPnl += t.pnl;
      current.avgPrice =
        current.trades.reduce((s, tr) => s + tr.price * tr.quantity, 0) / current.totalQty;
      current.lastTime = t.timestamp;
    } else {
      current = {
        key: t.id,
        symbol: t.symbol,
        side: t.side,
        trades: [t],
        avgPrice: t.price,
        totalQty: t.quantity,
        totalPnl: t.pnl,
        firstTime: t.timestamp,
        lastTime: t.timestamp,
      };
      groups.push(current);
    }
  }
  return groups;
}

const sideColors: Record<string, string> = {
  BUY: 'text-emerald-400 bg-emerald-400/10',
  SELL: 'text-blue-400 bg-blue-400/10',
  STOP: 'text-red-400 bg-red-400/10',
  TRAILING_STOP: 'text-amber-400 bg-amber-400/10',
};

function GroupedRow({ group }: { group: TradeGroup }) {
  const [expanded, setExpanded] = useState(false);
  const count = group.trades.length;
  const isSingle = count === 1;

  return (
    <>
      <tr
        className={`border-b border-border/50 transition-colors ${
          isSingle ? 'hover:bg-secondary/30' : 'hover:bg-secondary/40 cursor-pointer'
        }`}
        onClick={() => !isSingle && setExpanded(!expanded)}
        data-testid={`history-group-${group.key}`}
      >
        <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
          {new Date(group.firstTime).toLocaleString()}
        </td>
        <td className="px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm text-foreground">{group.symbol}</span>
            {!isSingle && (
              <span className="text-[10px] font-mono text-muted-foreground bg-secondary px-1.5 py-0.5 rounded-full border border-border">
                x{count}
              </span>
            )}
          </div>
        </td>
        <td className="px-4 py-2.5">
          <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${sideColors[group.side] || ''}`}>
            {group.side}
          </span>
        </td>
        <td className="px-4 py-2.5 font-mono text-sm text-right text-foreground">
          ${group.avgPrice.toFixed(2)}
          {!isSingle && <span className="text-[10px] text-muted-foreground ml-1">avg</span>}
        </td>
        <td className="px-4 py-2.5 font-mono text-sm text-right text-muted-foreground">
          {group.totalQty.toFixed(4)}
        </td>
        <td className={`px-4 py-2.5 font-mono text-sm text-right font-bold ${
          group.totalPnl > 0 ? 'text-emerald-400' : group.totalPnl < 0 ? 'text-red-400' : 'text-muted-foreground'
        }`}>
          {group.totalPnl !== 0 ? `${group.totalPnl > 0 ? '+' : ''}$${group.totalPnl.toFixed(2)}` : '-'}
        </td>
        <td className="px-4 py-2.5 text-xs text-muted-foreground">
          <div className="flex items-center gap-1">
            {isSingle ? (
              <span className="truncate max-w-[200px]">{group.trades[0].reason || '-'}</span>
            ) : (
              <>
                <span className="truncate max-w-[160px]">{group.trades[0].reason || '-'}</span>
                {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              </>
            )}
          </div>
        </td>
      </tr>

      {expanded && !isSingle && group.trades.map((t) => (
        <tr key={t.id} className="border-b border-border/20 bg-secondary/20" data-testid={`history-row-${t.id}`}>
          <td className="pl-8 pr-4 py-1.5 font-mono text-[10px] text-muted-foreground/70">
            {new Date(t.timestamp).toLocaleTimeString()}
          </td>
          <td className="px-4 py-1.5 text-xs text-muted-foreground">{t.symbol}</td>
          <td className="px-4 py-1.5">
            <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${sideColors[t.side] || ''}`}>
              {t.side}
            </span>
          </td>
          <td className="px-4 py-1.5 font-mono text-xs text-right text-muted-foreground">${t.price.toFixed(2)}</td>
          <td className="px-4 py-1.5 font-mono text-xs text-right text-muted-foreground/70">{t.quantity.toFixed(4)}</td>
          <td className={`px-4 py-1.5 font-mono text-xs text-right ${
            t.pnl > 0 ? 'text-emerald-400' : t.pnl < 0 ? 'text-red-400' : 'text-muted-foreground/70'
          }`}>
            {t.pnl !== 0 ? `${t.pnl > 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '-'}
          </td>
          <td className="px-4 py-1.5 text-[10px] text-muted-foreground/60 truncate max-w-[200px]">{t.reason || '-'}</td>
        </tr>
      ))}
    </>
  );
}

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

  const allTrades: TradeLog[] = history.length > 0 ? history : trades;
  const groups = groupConsecutiveTrades(allTrades);

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

      {/* Grouped count */}
      {allTrades.length > 0 && groups.length < allTrades.length && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono text-primary">{allTrades.length}</span> trades condensed into
          <span className="font-mono text-primary">{groups.length}</span> groups
          <span className="text-muted-foreground/50">- click a group to expand</span>
        </div>
      )}

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
            {groups.map((g) => (
              <GroupedRow key={g.key} group={g} />
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
