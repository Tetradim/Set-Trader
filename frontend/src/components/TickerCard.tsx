import React, { memo, useState, useCallback, useMemo } from 'react';
import { useStore, TickerConfig, PricePoint } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Trash2,
  TrendingUp,
  TrendingDown,
  Zap,
  ShieldAlert,
  Banknote,
  Activity,
  GripVertical,
  Settings2,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

interface Props {
  ticker: TickerConfig;
  onConfigOpen: (symbol: string) => void;
}

export const TickerCard = memo(function TickerCard({ ticker, onConfigOpen }: Props) {
  const { send } = useWebSocket();
  const price = useStore((s) => s.prices[ticker.symbol] ?? 0);
  const pnl = useStore((s) => s.profits[ticker.symbol] ?? 0);
  const position = useStore((s) => s.positions[ticker.symbol]);
  const chartEnabled = useStore((s) => s.chartEnabled[ticker.symbol] ?? false);
  const toggleChart = useStore((s) => s.toggleChart);
  const priceHistory = useStore((s) => s.priceHistory[ticker.symbol] ?? []);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmTP, setConfirmTP] = useState(false);

  const isPositive = pnl >= 0;
  const isActive = ticker.enabled;

  // Budget awareness
  const accountBalance = useStore((s) => s.accountBalance);
  const allTickers = useStore((s) => s.tickers);
  const localAllocated = Object.values(allTickers).reduce((s, t) => s + (t.base_power ?? 0), 0);
  const effectiveAvailable = accountBalance - localAllocated;
  const isOverAllocated = accountBalance > 0 && effectiveAvailable < 0;

  const handleToggle = (checked: boolean) => {
    send('UPDATE_TICKER', { symbol: ticker.symbol, enabled: checked });
  };

  const handleDelete = () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 4000);
      return;
    }
    send('DELETE_TICKER', { symbol: ticker.symbol });
  };

  const hasPosition = position && position.quantity > 0;

  const handleTakeProfit = () => {
    if (!confirmTP) {
      setConfirmTP(true);
      setTimeout(() => setConfirmTP(false), 4000);
      return;
    }
    send('TAKE_PROFIT', { symbol: ticker.symbol });
    setConfirmTP(false);
    toast.success(`Took profit for ${ticker.symbol}: $${pnl.toFixed(2)} moved to cash`);
  };

  const avgPrice = price > 0 ? price : 100;
  const entryPrice = position?.avg_entry || 0;

  const buyTarget = ticker.buy_percent
    ? (avgPrice * (1 + ticker.buy_offset / 100)).toFixed(2)
    : ticker.buy_offset.toFixed(2);

  const sellAnchor = (entryPrice > 0 && ticker.sell_percent) ? entryPrice : avgPrice;
  const sellTarget = ticker.sell_percent
    ? (sellAnchor * (1 + ticker.sell_offset / 100)).toFixed(2)
    : ticker.sell_offset.toFixed(2);

  /* dnd-kit sortable */
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: ticker.symbol });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 50 : 'auto' as any,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      data-testid={`ticker-card-${ticker.symbol}`}
      className={`
        relative overflow-hidden rounded-xl border transition-all duration-300
        ${isActive
          ? isPositive
            ? 'border-emerald-500/30 glow-success'
            : 'border-red-500/30 glow-danger'
          : 'border-border opacity-60'
        }
        glass hover:border-primary/40
      `}
      onDoubleClick={() => onConfigOpen(ticker.symbol)}
    >
      {isActive && (
        <div className={`absolute -right-8 -top-8 h-24 w-24 rounded-full blur-3xl opacity-20 ${
          isPositive ? 'bg-emerald-500' : 'bg-red-500'
        }`} />
      )}

      <div className="relative p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {/* Drag handle */}
            <button
              {...attributes}
              {...listeners}
              className="cursor-grab active:cursor-grabbing text-muted-foreground/40 hover:text-muted-foreground transition-colors touch-none"
              data-testid={`drag-handle-${ticker.symbol}`}
              title="Drag to reorder"
            >
              <GripVertical size={14} />
            </button>

            <Checkbox
              data-testid={`chart-toggle-${ticker.symbol}`}
              checked={chartEnabled}
              onCheckedChange={() => toggleChart(ticker.symbol)}
              className="h-3.5 w-3.5 data-[state=checked]:bg-accent data-[state=checked]:border-accent"
            />
            <h3 className={`text-lg font-bold tracking-tight ${
              ticker.auto_stopped ? 'text-red-500 animate-pulse' : 'text-foreground'
            }`}>{ticker.symbol}</h3>
            {ticker.auto_stopped && (
              <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-red-500/20 text-red-500 border border-red-500/40 tracking-wider" data-testid={`auto-stopped-badge-${ticker.symbol}`}>
                AUTO-STOPPED
              </span>
            )}
            <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
              isActive ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-secondary text-muted-foreground'
            }`}>
              {isActive ? 'LIVE' : 'OFF'}
            </span>
            {ticker.trailing_enabled && (
              <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-accent/20 text-accent border border-accent/30" data-testid={`trail-badge-${ticker.symbol}`}>TRAIL</span>
            )}
            {ticker.auto_rebracket && (
              <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-400 border border-orange-500/30" data-testid={`rebracket-badge-${ticker.symbol}`}>REBRACKET</span>
            )}
          </div>
          <Switch
            data-testid={`ticker-toggle-${ticker.symbol}`}
            checked={isActive}
            onCheckedChange={handleToggle}
            className="data-[state=checked]:bg-primary data-[state=checked]:glow-primary"
          />
        </div>

        {/* Price + P&L */}
        <div className="grid grid-cols-2 gap-4 mb-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Price</p>
            <p className="font-mono text-xl font-bold tracking-tight text-foreground">${price.toFixed(2)}</p>
          </div>
          <div className="text-right">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Net P&L</p>
            <p className={`font-mono text-xl font-bold tracking-tight ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
              {isPositive ? '+' : ''}${pnl.toFixed(2)}
            </p>
          </div>
        </div>

        {/* Quick stats */}
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground font-mono">
          <span className="flex items-center gap-1">
            <TrendingDown size={10} className="text-emerald-400" /> Buy: ${buyTarget}
          </span>
          <span className="flex items-center gap-1">
            <TrendingUp size={10} className="text-blue-400" /> Sell: ${sellTarget}
          </span>
          <span className="flex items-center gap-1">
            <Zap size={10} className="text-primary" /> ${ticker.base_power.toFixed(0)}
          </span>
        </div>

        {/* Position indicator */}
        {position && position.quantity > 0 && (
          <div className="mt-2 px-2 py-1 rounded bg-primary/10 border border-primary/20 text-xs font-mono">
            <span className="text-muted-foreground">Holding: </span>
            <span className="text-foreground font-bold">{position.quantity.toFixed(4)}</span>
            <span className="text-muted-foreground"> @ </span>
            <span className="text-foreground">${position.avg_entry.toFixed(2)}</span>
            <span className={`ml-2 font-bold ${position.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {position.unrealized_pnl >= 0 ? '+' : ''}${position.unrealized_pnl.toFixed(2)}
            </span>
          </div>
        )}

        {/* Live Price Chart */}
        {chartEnabled && <LivePriceChart ticker={ticker} priceHistory={priceHistory} />}

        {/* Controls row */}
        <div className="flex items-center justify-between mt-3">
          <button
            data-testid={`ticker-expand-${ticker.symbol}`}
            onClick={() => onConfigOpen(ticker.symbol)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <Settings2 size={14} />
            Configure
          </button>

          <div className="flex items-center gap-3">
            {pnl !== 0 && (
              <button
                data-testid={`take-profit-${ticker.symbol}`}
                onClick={handleTakeProfit}
                className={`flex items-center gap-1 text-xs transition-all ${
                  confirmTP ? 'text-amber-400 font-bold animate-pulse' : 'text-emerald-400 hover:text-emerald-300'
                }`}
              >
                <Banknote size={12} />
                {confirmTP ? `Take $${pnl.toFixed(2)}?` : 'Take Profit'}
              </button>
            )}

            <button
              data-testid={`ticker-delete-${ticker.symbol}`}
              onClick={handleDelete}
              className={`flex items-center gap-1 text-xs transition-all ${
                confirmDelete ? 'text-red-400 font-bold animate-pulse' : 'text-muted-foreground hover:text-red-400'
              }`}
            >
              <Trash2 size={12} />
              {confirmDelete
                ? (hasPosition ? `Delete with position? (${position!.quantity} shares)` : 'Confirm delete?')
                : 'Remove'
              }
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});

/* --- LivePriceChart --- */
function LivePriceChart({ ticker, priceHistory }: { ticker: TickerConfig; priceHistory: PricePoint[] }) {
  const chartData = useMemo(() => {
    if (priceHistory.length < 2) return [];
    let runningHigh = 0;
    return priceHistory.map((p) => {
      if (p.price > runningHigh) runningHigh = p.price;
      const trailMode = ticker.trailing_percent_mode ?? true;
      const trailVal = ticker.trailing_percent;
      const trailStop = ticker.trailing_enabled
        ? trailMode ? runningHigh * (1 - trailVal / 100) : runningHigh - trailVal
        : undefined;
      return {
        time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        price: p.price,
        trailStop: trailStop ? Math.round(trailStop * 100) / 100 : undefined,
      };
    });
  }, [priceHistory, ticker.trailing_enabled, ticker.trailing_percent, ticker.trailing_percent_mode]);

  if (chartData.length < 2) {
    return (
      <div className="mt-3 flex items-center justify-center h-24 rounded-lg bg-secondary/30 border border-border/30">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Activity size={12} className="animate-pulse" />
          Collecting price data...
        </div>
      </div>
    );
  }

  const prices = chartData.map((d) => d.price);
  const minP = Math.min(...prices) * 0.9995;
  const maxP = Math.max(...prices) * 1.0005;

  return (
    <div className="mt-3 rounded-lg bg-secondary/20 border border-border/30 p-2" data-testid={`chart-${ticker.symbol}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1">
          <Activity size={10} /> Live Chart
        </span>
        <span className="text-[10px] font-mono text-muted-foreground">{chartData.length} pts</span>
      </div>
      <ResponsiveContainer width="100%" height={140}>
        <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
          <XAxis dataKey="time" tick={false} axisLine={false} />
          <YAxis domain={[minP, maxP]} tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} width={50} tickFormatter={(v: number) => `$${v.toFixed(1)}`} />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '11px' }}
            labelStyle={{ color: '#94a3b8' }}
            formatter={(v: number, name: string) => [`$${v.toFixed(2)}`, name === 'price' ? 'Price' : 'Trail Stop']}
          />
          <Line type="monotone" dataKey="price" stroke="#6366f1" strokeWidth={2} dot={false} isAnimationActive={false} />
          {ticker.trailing_enabled && (
            <Line type="monotone" dataKey="trailStop" stroke="#f59e0b" strokeWidth={1} strokeDasharray="4 2" dot={false} isAnimationActive={false} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
