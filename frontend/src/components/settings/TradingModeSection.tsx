import { Shield, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { useWebSocket } from '@/hooks/useWebSocket';
import { apiFetch } from '@/lib/api';
import { Switch } from '@/components/ui/switch';
import { useStore } from '@/stores/useStore';

export function TradingModeSection() {
  const simulate247 = useStore((s) => s.simulate247);
  const setSimulate247 = useStore((s) => s.setSimulate247);
  const { send } = useWebSocket();

  const handleToggle = async (checked: boolean) => {
    setSimulate247(checked);
    send('SET_SIMULATE_24_7', { enabled: checked });
    try {
      await apiFetch('/api/settings', {
        method: 'POST',
        body: JSON.stringify({ simulate_24_7: checked }),
      });
      toast.success(checked
        ? 'Paper Trading mode enabled. Market always open, no live orders.'
        : 'Live Trading mode enabled. Real market hours, orders routed to brokers.'
      );
    } catch (error: any) {
      toast.error(error.message || 'Failed to save mode');
    }
  };

  return (
    <section className="glass rounded-xl border border-border p-6 space-y-4" data-testid="trading-mode-section">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {simulate247 ? <Shield size={18} className="text-amber-400" /> : <Zap size={18} className="text-emerald-400" />}
          <h3 className="text-sm font-bold text-foreground">Trading Mode</h3>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${
            simulate247 ? 'bg-amber-500/10 text-amber-400 border-amber-500/30' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
          }`} data-testid="trading-mode-badge">
            {simulate247 ? 'PAPER' : 'LIVE'}
          </span>
          <Switch data-testid="simulation-toggle" checked={simulate247} onCheckedChange={handleToggle} className="data-[state=checked]:bg-amber-500" />
        </div>
      </div>
      <div className={`rounded-lg p-4 border ${simulate247 ? 'bg-amber-500/5 border-amber-500/20' : 'bg-emerald-500/5 border-emerald-500/20'}`}>
        {simulate247 ? (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-amber-400">Paper Trading (Simulation)</p>
            <ul className="text-xs text-muted-foreground space-y-1 list-disc ml-4">
              <li>Market is treated as always open (24/7)</li>
              <li>Trades are logged locally but <strong className="text-foreground">NOT sent to brokers</strong></li>
              <li>Perfect for testing strategies risk-free</li>
              <li>All trade analytics and P&L are tracked normally</li>
            </ul>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-emerald-400">Live Trading</p>
            <ul className="text-xs text-muted-foreground space-y-1 list-disc ml-4">
              <li>Follows market hours for the selected market on each ticker</li>
              <li>Orders are <strong className="text-foreground">routed to connected brokers</strong></li>
              <li>Tickers without assigned brokers still trade in paper mode</li>
              <li>Broker failures are handled gracefully with alerts</li>
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
