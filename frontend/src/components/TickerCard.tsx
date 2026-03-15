import { useStore } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Play, Pause, Trash2 } from 'lucide-react';

export const TickerCard = ({ ticker }: { ticker: any }) => {
  const isPositive = ticker.profit >= 0;
  const isActive = ticker.enabled;

  return (
    <div className={`
      relative overflow-hidden rounded-xl border p-5 transition-all duration-500
      ${isActive 
        ? (isPositive ? 'border-green-500/50 shadow-[0_0_15px_rgba(34,197,94,0.1)]' : 'border-red-500/50 shadow-[0_0_15px_rgba(239,68,68,0.1)]') 
        : 'border-muted bg-muted/20 opacity-60 grayscale'}
    `}>
      {/* Background Pulse for Active Tickers */}
      {isActive && (
        <div className={`absolute -right-4 -top-4 h-20 w-20 blur-3xl opacity-20 animate-pulse ${
          isPositive ? 'bg-green-500' : 'bg-red-500'
        }`} />
      )}

      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-bold tracking-tight">{ticker.symbol}</h3>
        <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
          isActive ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground'
        }`}>
          {ticker.status}
        </span>
      </div>

      <div className="mt-4">
        <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Net Profit</p>
        <p className={`text-2xl font-mono font-bold ${isPositive ? 'text-green-500' : 'text-red-500'}`}>
          {isPositive ? '+$' : '-$'}{Math.abs(ticker.profit).toFixed(2)}
        </p>
      </div>
      
      {/* ... toggle and delete buttons ... */}
    </div>
  );
};