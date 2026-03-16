import { useStore } from '@/stores/useStore';
import { motion, AnimatePresence } from 'framer-motion';

export function TradeLogSidebar() {
  const trades = useStore((s) => s.trades);

  const sideColors: Record<string, string> = {
    BUY: 'text-emerald-400',
    SELL: 'text-blue-400',
    STOP: 'text-red-400',
    TRAILING_STOP: 'text-amber-400',
  };

  return (
    <aside
      className="hidden xl:flex flex-col w-80 border-l border-border glass"
      data-testid="trade-log-sidebar"
    >
      <div className="px-4 py-3 border-b border-border">
        <h2 className="text-xs uppercase tracking-widest font-semibold text-muted-foreground">
          Live Activity
        </h2>
      </div>
      <div className="flex-1 overflow-auto px-2 py-2 space-y-0.5">
        <AnimatePresence initial={false}>
          {trades.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: -10, height: 0 }}
              animate={{ opacity: 1, x: 0, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="flex items-center justify-between px-3 py-2 rounded-md hover:bg-secondary/50 transition-colors font-mono text-xs"
              data-testid={`trade-log-entry-${t.id}`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className={`font-bold w-5 shrink-0 ${sideColors[t.side] || 'text-foreground'}`}>
                  {t.side === 'TRAILING_STOP' ? 'TS' : t.side.charAt(0)}
                </span>
                <span className="font-semibold text-foreground truncate">{t.symbol}</span>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-muted-foreground">${t.price.toFixed(2)}</span>
                {t.pnl !== 0 && (
                  <span className={t.pnl > 0 ? 'text-emerald-400' : 'text-red-400'}>
                    {t.pnl > 0 ? '+' : ''}{t.pnl.toFixed(2)}
                  </span>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
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
