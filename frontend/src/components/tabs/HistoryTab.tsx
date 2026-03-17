import { useStore, TradeLog } from '@/stores/useStore';
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import {
  TrendingUp,
  TrendingDown,
  BarChart3,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  DollarSign,
  Percent,
} from 'lucide-react';

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

function OrderBadge({ type }: { type: string }) {
  if (!type) return null;
  const isMkt = type === 'MARKET';
  return (
    <span
      className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
        isMkt ? 'bg-orange-500/15 text-orange-400' : 'bg-cyan-500/15 text-cyan-400'
      }`}
      data-testid="order-type-badge"
    >
      {isMkt ? 'MKT' : 'LMT'}
    </span>
  );
}

function ModeBadge({ mode }: { mode: string }) {
  if (!mode) return null;
  const isPct = mode === 'PERCENT';
  return (
    <span
      className={`text-[9px] font-medium px-1.5 py-0.5 rounded inline-flex items-center gap-0.5 ${
        isPct ? 'bg-violet-500/15 text-violet-400' : 'bg-teal-500/15 text-teal-400'
      }`}
      data-testid="rule-mode-badge"
    >
      {isPct ? <Percent size={8} /> : <DollarSign size={8} />}
      {mode}
    </span>
  );
}

function TradeDetail({ trade }: { trade: TradeLog }) {
  const isSell = trade.side !== 'BUY';
  const isLoss = trade.pnl < 0;
  const isTrailing = trade.side === 'TRAILING_STOP';

  return (
    <div
      className={`rounded-lg border p-3 text-xs font-mono space-y-2 ${
        isLoss
          ? 'border-red-500/30 bg-red-500/5'
          : isSell && trade.pnl > 0
          ? 'border-emerald-500/30 bg-emerald-500/5'
          : 'border-border/50 bg-secondary/20'
      }`}
      data-testid={`trade-detail-${trade.id}`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`font-bold uppercase px-2 py-0.5 rounded text-[10px] ${sideColors[trade.side] || ''}`}
          >
            {trade.side}
          </span>
          <span className="font-bold text-foreground">{trade.symbol}</span>
          <OrderBadge type={trade.order_type} />
          <ModeBadge mode={trade.rule_mode} />
        </div>
        <span className="text-muted-foreground/70">
          {new Date(trade.timestamp).toLocaleString()}
        </span>
      </div>

      {/* Core trade info */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1.5">
        <div>
          <span className="text-muted-foreground/60 text-[10px]">Fill Price</span>
          <p className="text-foreground">${trade.price.toFixed(2)}</p>
        </div>
        <div>
          <span className="text-muted-foreground/60 text-[10px]">Quantity</span>
          <p className="text-foreground">{trade.quantity.toFixed(4)}</p>
        </div>
        <div>
          <span className="text-muted-foreground/60 text-[10px]">Total Value</span>
          <p className="text-foreground">${(trade.total_value || trade.price * trade.quantity).toFixed(2)}</p>
        </div>
        {trade.buy_power > 0 && (
          <div>
            <span className="text-muted-foreground/60 text-[10px]">Buy Power</span>
            <p className="text-foreground">${trade.buy_power.toFixed(2)}</p>
          </div>
        )}
      </div>

      {/* Target & Average info — only show when data exists */}
      {(trade.target_price > 0 || trade.avg_price > 0 || (isSell && trade.entry_price > 0)) && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1.5">
          {trade.target_price > 0 && (
            <div>
              <span className="text-muted-foreground/60 text-[10px]">Target Price</span>
              <p className="text-foreground">${trade.target_price.toFixed(2)}</p>
            </div>
          )}
          {trade.avg_price > 0 && (
            <div>
              <span className="text-muted-foreground/60 text-[10px]">Avg Price (MA)</span>
              <p className="text-foreground">${trade.avg_price.toFixed(2)}</p>
            </div>
          )}
          {isSell && trade.entry_price > 0 && (
            <div>
              <span className="text-muted-foreground/60 text-[10px]">Entry Price</span>
              <p className="text-foreground">${trade.entry_price.toFixed(2)}</p>
            </div>
          )}
        </div>
      )}

      {/* P&L — always show for sell-side trades */}
      {isSell && trade.pnl !== 0 && (
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground/60 text-[10px]">P&L:</span>
          <span
            className={`font-mono font-bold text-sm ${
              trade.pnl > 0 ? 'text-emerald-400' : 'text-red-400'
            }`}
          >
            {trade.pnl > 0 ? '+' : ''}${trade.pnl.toFixed(2)}
          </span>
        </div>
      )}

      {/* Sell/Stop targets at time of trade */}
      {isSell && (trade.sell_target > 0 || trade.stop_target > 0) && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1.5 pt-1 border-t border-border/30">
          {trade.sell_target > 0 && (
            <div>
              <span className="text-muted-foreground/60 text-[10px]">Sell Target</span>
              <p className="text-foreground">${trade.sell_target.toFixed(2)}</p>
            </div>
          )}
          {trade.stop_target > 0 && (
            <div>
              <span className="text-muted-foreground/60 text-[10px]">Stop Target</span>
              <p className="text-foreground">${trade.stop_target.toFixed(2)}</p>
            </div>
          )}
        </div>
      )}

      {/* Trailing stop specifics */}
      {isTrailing && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1.5 pt-1 border-t border-border/30">
          <div>
            <span className="text-muted-foreground/60 text-[10px]">Trail High</span>
            <p className="text-amber-400">${(trade.trail_high || 0).toFixed(2)}</p>
          </div>
          <div>
            <span className="text-muted-foreground/60 text-[10px]">Trail Trigger</span>
            <p className="text-amber-400">${(trade.trail_trigger || 0).toFixed(2)}</p>
          </div>
          <div>
            <span className="text-muted-foreground/60 text-[10px]">Trail Config</span>
            <p className="text-foreground">
              {trade.trail_mode === 'PERCENT' ? `${trade.trail_value}%` : `$${(trade.trail_value || 0).toFixed(2)}`}
              <span className="text-muted-foreground/50 ml-1">({trade.trail_mode || '?'})</span>
            </p>
          </div>
        </div>
      )}

      {/* Loss callout */}
      {isLoss && trade.entry_price > 0 && (
        <div className="flex items-center gap-2 pt-1 border-t border-red-500/20 text-red-400 text-[10px]">
          <AlertTriangle size={12} />
          <span>
            Loss of ${Math.abs(trade.pnl).toFixed(2)} — bought at ${trade.entry_price.toFixed(2)}, sold at $
            {trade.price.toFixed(2)} ({((trade.price / trade.entry_price - 1) * 100).toFixed(2)}%)
          </span>
        </div>
      )}
      {isLoss && !trade.entry_price && (
        <div className="flex items-center gap-2 pt-1 border-t border-red-500/20 text-red-400 text-[10px]">
          <AlertTriangle size={12} />
          <span>Loss of ${Math.abs(trade.pnl).toFixed(2)} — sold at ${trade.price.toFixed(2)}</span>
        </div>
      )}
    </div>
  );
}

function GroupedRow({ group }: { group: TradeGroup }) {
  const [expanded, setExpanded] = useState(false);
  const count = group.trades.length;
  const isSingle = count === 1;
  const isLoss = group.totalPnl < 0;

  return (
    <div className="space-y-0" data-testid={`history-group-${group.key}`}>
      <div
        className={`flex items-center justify-between px-4 py-3 transition-colors cursor-pointer border-b ${
          isLoss ? 'border-red-500/20 hover:bg-red-500/5' : 'border-border/50 hover:bg-secondary/30'
        }`}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <span className="text-muted-foreground/60 font-mono text-xs w-[140px] shrink-0">
            {new Date(group.firstTime).toLocaleString()}
          </span>
          <span className="font-bold text-sm text-foreground">{group.symbol}</span>
          {!isSingle && (
            <span className="text-[10px] font-mono text-muted-foreground bg-secondary px-1.5 py-0.5 rounded-full border border-border">
              x{count}
            </span>
          )}
          <span
            className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${sideColors[group.side] || ''}`}
          >
            {group.side}
          </span>
          {/* Show order type & mode from first trade */}
          <OrderBadge type={group.trades[0]?.order_type} />
          <ModeBadge mode={group.trades[0]?.rule_mode} />
        </div>
        <div className="flex items-center gap-4 shrink-0">
          <span className="font-mono text-sm text-foreground">
            ${group.avgPrice.toFixed(2)}
            {!isSingle && <span className="text-[10px] text-muted-foreground ml-1">avg</span>}
          </span>
          <span className="font-mono text-sm text-muted-foreground">{group.totalQty.toFixed(4)}</span>
          <span
            className={`font-mono text-sm font-bold min-w-[80px] text-right ${
              group.totalPnl > 0
                ? 'text-emerald-400'
                : group.totalPnl < 0
                ? 'text-red-400'
                : 'text-muted-foreground'
            }`}
          >
            {group.totalPnl !== 0 ? `${group.totalPnl > 0 ? '+' : ''}$${group.totalPnl.toFixed(2)}` : '-'}
          </span>
          {expanded ? (
            <ChevronUp size={14} className="text-muted-foreground" />
          ) : (
            <ChevronDown size={14} className="text-muted-foreground" />
          )}
        </div>
      </div>

      {expanded && (
        <div className="px-4 py-3 space-y-2 bg-background/50">
          {group.trades.map((t) => (
            <TradeDetail key={t.id} trade={t} />
          ))}
        </div>
      )}
    </div>
  );
}

type FilterType = 'ALL' | 'BUY' | 'SELL' | 'STOP' | 'TRAILING_STOP' | 'LOSSES';

export function HistoryTab() {
  const trades = useStore((s) => s.trades);
  const [history, setHistory] = useState<any[]>([]);
  const [stats, setStats] = useState({ wins: 0, losses: 0, total: 0, winRate: 0, totalLoss: 0, totalGain: 0 });
  const [filter, setFilter] = useState<FilterType>('ALL');

  useEffect(() => {
    apiFetch('/api/trades?limit=200')
      .then((data) => {
        setHistory(data);
        const wins = data.filter((t: any) => t.pnl > 0).length;
        const losses = data.filter((t: any) => t.pnl < 0).length;
        const totalLoss = data.filter((t: any) => t.pnl < 0).reduce((s: number, t: any) => s + t.pnl, 0);
        const totalGain = data.filter((t: any) => t.pnl > 0).reduce((s: number, t: any) => s + t.pnl, 0);
        const total = data.length;
        setStats({
          wins,
          losses,
          total,
          winRate: wins + losses > 0 ? Math.round((wins / (wins + losses)) * 100) : 0,
          totalLoss: Math.abs(totalLoss),
          totalGain,
        });
      })
      .catch(() => {});
  }, [trades.length]);

  const allTrades: TradeLog[] = history.length > 0 ? history : trades;

  // Apply filter
  const filtered =
    filter === 'ALL'
      ? allTrades
      : filter === 'LOSSES'
      ? allTrades.filter((t) => t.pnl < 0)
      : allTrades.filter((t) => t.side === filter);

  const groups = groupConsecutiveTrades(filtered);

  const filters: { label: string; value: FilterType; color: string }[] = [
    { label: 'All', value: 'ALL', color: '' },
    { label: 'Buys', value: 'BUY', color: 'text-emerald-400' },
    { label: 'Sells', value: 'SELL', color: 'text-blue-400' },
    { label: 'Stops', value: 'STOP', color: 'text-red-400' },
    { label: 'Trail', value: 'TRAILING_STOP', color: 'text-amber-400' },
    { label: 'Losses', value: 'LOSSES', color: 'text-red-400' },
  ];

  return (
    <div className="space-y-6" data-testid="history-tab">
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard label="Total Trades" value={stats.total.toString()} />
        <StatCard label="Wins" value={stats.wins.toString()} color="text-emerald-400" icon={<TrendingUp size={14} />} />
        <StatCard label="Losses" value={stats.losses.toString()} color="text-red-400" icon={<TrendingDown size={14} />} />
        <StatCard label="Total Gained" value={`$${stats.totalGain.toFixed(2)}`} color="text-emerald-400" icon={<DollarSign size={14} />} />
        <StatCard
          label="Total Lost"
          value={`-$${stats.totalLoss.toFixed(2)}`}
          color="text-red-400"
          icon={<AlertTriangle size={14} />}
        />
        <div className="glass rounded-xl border border-border p-4">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Win Rate</p>
          <div className="flex items-center gap-2 mt-1">
            <BarChart3 size={14} className="text-primary" />
            <span className="font-mono text-lg font-bold text-foreground">{stats.winRate}%</span>
          </div>
          <div className="w-full h-1 bg-secondary rounded-full mt-2 overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all"
              style={{ width: `${stats.winRate}%` }}
            />
          </div>
        </div>
      </div>

      {/* Filter pills */}
      <div className="flex items-center gap-2 flex-wrap">
        {filters.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
              filter === f.value
                ? 'bg-primary/20 border-primary text-primary'
                : 'border-border bg-secondary/30 text-muted-foreground hover:bg-secondary/60'
            }`}
            data-testid={`filter-${f.value.toLowerCase()}`}
          >
            {f.label}
            {f.value === 'LOSSES' && stats.losses > 0 && (
              <span className="ml-1.5 bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded-full text-[10px]">
                {stats.losses}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Trade count */}
      {filtered.length > 0 && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono text-primary">{filtered.length}</span> trades
          {groups.length < filtered.length && (
            <>
              {' '}condensed into <span className="font-mono text-primary">{groups.length}</span> groups
            </>
          )}
          <span className="text-muted-foreground/50">— click any row to see full details</span>
        </div>
      )}

      {/* Trade list */}
      <div className="glass rounded-xl border border-border overflow-hidden" data-testid="history-table">
        {groups.map((g) => (
          <GroupedRow key={g.key} group={g} />
        ))}
        {filtered.length === 0 && (
          <div
            className="flex flex-col items-center justify-center h-32 text-muted-foreground text-xs"
            data-testid="no-history"
          >
            <p>{filter === 'LOSSES' ? 'No losing trades found' : 'No trade history yet'}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
  icon,
}: {
  label: string;
  value: string;
  color?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="glass rounded-xl border border-border p-4" data-testid={`stat-${label.toLowerCase().replace(/\s+/g, '-')}`}>
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <div className="flex items-center gap-2 mt-1">
        {icon && <span className={color || 'text-foreground'}>{icon}</span>}
        <span className={`font-mono text-lg font-bold tracking-tight ${color || 'text-foreground'}`}>
          {value}
        </span>
      </div>
    </div>
  );
}
