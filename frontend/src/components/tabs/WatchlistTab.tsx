import { useStore } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { TickerCard } from '../TickerCard';
import { Checkbox } from '@/components/ui/checkbox';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';

export function WatchlistTab() {
  const { send } = useWebSocket();
  const tickers = useStore((s) => Object.values(s.tickers));
  const paused = useStore((s) => s.paused);
  const running = useStore((s) => s.running);
  const connected = useStore((s) => s.connected);
  const simulate247 = useStore((s) => s.simulate247);

  const activeTickers = tickers.filter((t) => t.enabled);
  const inactiveTickers = tickers.filter((t) => !t.enabled);

  return (
    <div className="space-y-8" data-testid="watchlist-tab">
      {/* Control bar */}
      <div className="flex items-center justify-between p-3 rounded-lg glass border border-border">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Checkbox
              data-testid="global-pause-checkbox"
              checked={paused}
              onCheckedChange={(checked: boolean) => send('GLOBAL_PAUSE', { pause: checked })}
              className="data-[state=checked]:bg-amber-500 data-[state=checked]:border-amber-500"
            />
            <label className="text-xs font-medium text-muted-foreground cursor-pointer flex items-center gap-1.5">
              <AlertTriangle size={12} className="text-amber-400" />
              Emergency Pause
            </label>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              data-testid="simulate-247-checkbox"
              checked={simulate247}
              onCheckedChange={(checked: boolean) => {
                useStore.getState().setSimulate247(checked as boolean);
              }}
            />
            <label className="text-xs text-muted-foreground cursor-pointer">Simulate 24/7</label>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-muted-foreground">
            {activeTickers.length} active / {tickers.length} total
          </span>
          <div className={`h-2 w-2 rounded-full ${
            connected
              ? running && !paused ? 'bg-emerald-400 animate-pulse shadow-[0_0_6px_#34d399]' : 'bg-emerald-400'
              : 'bg-red-400 animate-ping'
          }`} />
        </div>
      </div>

      {/* Active tickers */}
      {activeTickers.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold mb-4 flex items-center gap-2 text-foreground" data-testid="live-tickers-section">
            <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            Live Tickers
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            <AnimatePresence mode="popLayout">
              {activeTickers.map((t) => (
                <motion.div
                  key={t.symbol}
                  layout
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.2 }}
                >
                  <TickerCard ticker={t} />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </section>
      )}

      {/* Inactive tickers */}
      {inactiveTickers.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold mb-4 text-muted-foreground" data-testid="inactive-tickers-section">
            Stored / Inactive
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            <AnimatePresence mode="popLayout">
              {inactiveTickers.map((t) => (
                <motion.div
                  key={t.symbol}
                  layout
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  className="opacity-60 hover:opacity-100 transition-opacity"
                >
                  <TickerCard ticker={t} />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </section>
      )}

      {tickers.length === 0 && (
        <div className="flex flex-col items-center justify-center h-64 text-muted-foreground" data-testid="empty-watchlist">
          <p className="text-sm font-medium">No tickers yet</p>
          <p className="text-xs mt-1 text-muted-foreground/60">
            Click "Add Stock" to begin tracking your first symbol
          </p>
        </div>
      )}
    </div>
  );
}
