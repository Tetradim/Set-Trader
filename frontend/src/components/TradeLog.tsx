import { useStore } from '@/stores/useStore';
import { motion, AnimatePresence } from 'framer-motion';

export const TradeLog = () => {
  const logs = useStore((state) => state.logs);

  return (
    <div className="mt-10 rounded-xl border bg-card/50 overflow-hidden">
      <div className="p-4 border-b bg-muted/30">
        <h2 className="text-sm font-bold uppercase tracking-widest text-muted-foreground">Recent Activity</h2>
      </div>
      <div className="max-h-[300px] overflow-y-auto p-2 font-mono text-xs">
        <AnimatePresence initial={false}>
          {logs.map((log) => (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex justify-between items-center p-2 border-b border-muted last:border-0"
            >
              <div className="flex gap-4">
                <span className="text-muted-foreground">[{log.timestamp}]</span>
                <span className="font-bold">{log.symbol}</span>
                <span className={
                  log.type === 'BUY' ? 'text-green-500' : 
                  log.type === 'SELL' ? 'text-blue-500' : 'text-red-500'
                }>
                  {log.type}
                </span>
              </div>
              <span className="font-bold">${log.price.toFixed(2)}</span>
            </motion.div>
          ))}
        </AnimatePresence>
        {logs.length === 0 && (
          <div className="p-8 text-center text-muted-foreground italic">
            Waiting for market activity...
          </div>
        )}
      </div>
    </div>
  );
};