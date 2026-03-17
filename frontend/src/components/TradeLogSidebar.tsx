import { useState } from 'react';
import { useStore, TradeLog } from '@/stores/useStore';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react';

interface TradeGroup {
  key: string;
  symbol: string;
  side: string;
  trades: TradeLog[];
  avgPrice: number;
  totalQty: number;
  totalPnl: number;
  firstTime: string;
}

function groupTrades(trades: TradeLog[]): TradeGroup[] {
  const groups: TradeGroup[] = [];
  let current: TradeGroup | null = null;

  for (const t of trades) {
    if (current && current.symbol === t.symbol && current.side === t.side) {
      current.trades.push(t);
      current.totalQty += t.quantity;
      current.totalPnl += t.pnl;
      current.avgPrice =
        current.trades.reduce((s, tr) => s + tr.price * tr.quantity, 0) / current.totalQty;
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
      };
      groups.push(current);
    }
  }
  return groups;
}

const sideColors: Record<string, string> = {
  BUY: 'text-emerald-400',
  SELL: 'text-blue-400',
  STOP: 'text-red-400',
  TRAILING_STOP: 'text-amber-400',
};

const sideBg: Record<string, string> = {
  BUY: 'bg-emerald-400/5',
  SELL: 'bg-blue-400/5',
  STOP: 'bg-red-400/5',
  TRAILING_STOP: 'bg-amber-400/5',
};

function SideLabel({ side }: { side: string }) {
  return (
    <span className={`font-bold w-5 shrink-0 ${sideColors[side] || 'text-foreground'}`}>
      {side === 'TRAILING_STOP' ? 'TS' : side.charAt(0)}
    </span>
  );
}

function TradeDetailMini({ trade }: { trade: TradeLog }) {
  const isSell = trade.side !== 'BUY';
  const isLoss = trade.pnl < 0;

  return (
    <div className={`rounded px-2 py-1.5 text-[10px] font-mono space-y-1 ${isLoss ? 'bg-red-500/5' : 'bg-secondary/20'}`}>
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground/70">{new Date(trade.timestamp).toLocaleTimeString()}</span>
        <div className="flex items-center gap-1.5">
          {trade.order_type && (
            <span className={`text-[8px] font-bold px-1 rounded ${trade.order_type === 'MARKET' ? 'bg-orange-500/15 text-orange-400' : 'bg-cyan-500/15 text-cyan-400'}`}>
              {trade.order_type === 'MARKET' ? 'MKT' : 'LMT'}
            </span>
          )}
          {trade.rule_mode && (
            <span className={`text-[8px] px-1 rounded ${trade.rule_mode === 'PERCENT' ? 'bg-violet-500/15 text-violet-400' : 'bg-teal-500/15 text-teal-400'}`}>
              {trade.rule_mode === 'PERCENT' ? '%' : '$'}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground">Fill ${trade.price.toFixed(2)} x{trade.quantity.toFixed(4)}</span>
        {trade.pnl !== 0 && (
          <span className={isLoss ? 'text-red-400 font-bold' : 'text-emerald-400'}>
            {trade.pnl > 0 ? '+' : ''}{trade.pnl.toFixed(2)}
          </span>
        )}
      </div>
      {isSell && trade.entry_price > 0 && (
        <div className="flex items-center justify-between text-muted-foreground/60">
          <span>Entry ${trade.entry_price.toFixed(2)} → Target ${(trade.target_price || 0).toFixed(2)}</span>
        </div>
      )}
      {isLoss && trade.entry_price > 0 && (
        <div className="flex items-center gap-1 text-red-400/80">
          <AlertTriangle size={8} />
          <span>Loss {((trade.price / trade.entry_price - 1) * 100).toFixed(2)}%</span>
        </div>
      )}
    </div>
  );
}

function GroupRow({ group }: { group: TradeGroup }) {
  const [expanded, setExpanded] = useState(false);
  const count = group.trades.length;
  const isSingle = count === 1;
  const isLoss = group.totalPnl < 0;

  return (
    <div className={`rounded-md ${!isSingle ? sideBg[group.side] : ''} ${isLoss ? 'ring-1 ring-red-500/20' : ''}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className={`w-full flex items-center justify-between px-3 py-2 rounded-md hover:bg-secondary/50 transition-colors font-mono text-xs cursor-pointer`}
        data-testid={`trade-group-${group.key}`}
      >
        <div className="flex items-center gap-2 min-w-0">
          <SideLabel side={group.side} />
          <span className="font-semibold text-foreground truncate">{group.symbol}</span>
          {!isSingle && (
            <span className="text-[10px] text-muted-foreground bg-secondary px-1.5 py-0.5 rounded-full">
              x{count}
            </span>
          )}
          {/* Show badges for single trades */}
          {isSingle && group.trades[0]?.order_type && (
            <span className={`text-[8px] font-bold px-1 rounded ${group.trades[0].order_type === 'MARKET' ? 'bg-orange-500/15 text-orange-400' : 'bg-cyan-500/15 text-cyan-400'}`}>
              {group.trades[0].order_type === 'MARKET' ? 'MKT' : 'LMT'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-muted-foreground">${group.avgPrice.toFixed(2)}</span>
          {group.totalPnl !== 0 && (
            <span className={`font-bold ${group.totalPnl > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {group.totalPnl > 0 ? '+' : ''}
              {group.totalPnl.toFixed(2)}
            </span>
          )}
          {expanded ? (
            <ChevronUp size={10} className="text-muted-foreground" />
          ) : (
            <ChevronDown size={10} className="text-muted-foreground" />
          )}
        </div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="px-2 pb-2 space-y-1">
              {group.trades.map((t) => (
                <TradeDetailMini key={t.id} trade={t} />
              ))}
              {!isSingle && (
                <div className="flex items-center justify-between text-[10px] font-mono text-foreground/70 pt-1 px-2 border-t border-border/30">
                  <span>Total</span>
                  <div className="flex items-center gap-2">
                    <span>avg ${group.avgPrice.toFixed(2)}</span>
                    <span>x{group.totalQty.toFixed(4)}</span>
                    {group.totalPnl !== 0 && (
                      <span className={group.totalPnl > 0 ? 'text-emerald-400' : 'text-red-400'}>
                        {group.totalPnl > 0 ? '+' : ''}{group.totalPnl.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function TradeLogSidebar() {
  const trades = useStore((s) => s.trades);
  const groups = groupTrades(trades);
  const lossCount = trades.filter((t) => t.pnl < 0).length;

  return (
    <aside
      className="hidden xl:flex flex-col w-80 border-l border-border glass"
      data-testid="trade-log-sidebar"
    >
      <div className="px-4 py-3 border-b border-border flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-widest font-semibold text-muted-foreground">
          Live Activity
        </h2>
        <div className="flex items-center gap-2">
          {lossCount > 0 && (
            <span className="text-[10px] bg-red-500/15 text-red-400 px-1.5 py-0.5 rounded-full font-mono" data-testid="loss-count-badge">
              {lossCount} loss{lossCount !== 1 ? 'es' : ''}
            </span>
          )}
          {trades.length > 0 && (
            <span className="text-[10px] text-muted-foreground/60 font-mono">
              {trades.length} trades / {groups.length} groups
            </span>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-auto px-2 py-2 space-y-0.5">
        {groups.map((g) => (
          <GroupRow key={g.key} group={g} />
        ))}
        {trades.length === 0 && (
          <div className="flex flex-col items-center justify-center h-40 text-muted-foreground text-xs">
            <p>No activity yet</p>
            <p className="mt-1 text-muted-foreground/60">Trades will appear here in real-time</p>
          </div>
        )}
      </div>
    </aside>
  );
}
