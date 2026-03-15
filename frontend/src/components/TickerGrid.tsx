import React from 'react';
import { useStore } from '@/stores/useStore';
import { TickerCard } from './TickerCard';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Checkbox } from '@/components/ui/checkbox';
import { motion, AnimatePresence } from 'framer-motion';

export const TickerGrid = () => {
  // Pulling everything needed from the store
  const tickers = useStore((state) => Object.values(state.tickers));
  const isPaused = useStore((state) => state.paused);
  const connected = useStore((state) => state.connected); // Added this line
  const { sendMessage } = useWebSocket();

  // Split tickers into two groups
  const activeTickers = tickers.filter(t => t.enabled);
  const storedTickers = tickers.filter(t => !t.enabled);

  const handleGlobalPause = (checked: boolean) => {
    sendMessage("GLOBAL_PAUSE", { pause: checked });
  };

  return (
    <div className="space-y-10">
      {/* Global Control Bar */}
      <div className="flex items-center justify-between p-4 bg-secondary/30 rounded-lg border border-orange-500/20">
        <div className="flex items-center space-x-2">
          <Checkbox 
            id="pause" 
            checked={isPaused} 
            onCheckedChange={handleGlobalPause} 
          />
          <label htmlFor="pause" className="text-sm font-medium leading-none cursor-pointer">
            Emergency Global Pause (Halts all execution)
          </label>
        </div>

        {/* Connection Heartbeat */}
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${connected ? 'bg-green-500 shadow-[0_0_8px_#22c55e]' : 'bg-red-500 animate-ping'}`} />
          <span className="text-[10px] uppercase font-bold text-muted-foreground tracking-widest">
            {connected ? 'Engine Live' : 'Engine Offline'}
          </span>
        </div>
      </div>

      {/* Active Section */}
      <section>
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-foreground">
          <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          Live Tickers
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <AnimatePresence mode="popLayout">
            {activeTickers.map((t) => (
              <motion.div
                key={t.symbol}
                layout
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.2 }}
              >
                <TickerCard ticker={t} />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </section>

      {/* Stored Partition */}
      {storedTickers.length > 0 && (
        <section className="pt-10 border-t border-dashed border-muted">
          <h2 className="text-lg font-semibold mb-4 text-muted-foreground">Stored / Inactive</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <AnimatePresence mode="popLayout">
              {storedTickers.map((t) => (
                <motion.div
                  key={t.symbol}
                  layout
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ duration: 0.2 }}
                  className="grayscale opacity-70 hover:grayscale-0 hover:opacity-100 transition-all"
                >
                  <TickerCard ticker={t} />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </section>
      )}
    </div>
  );
};