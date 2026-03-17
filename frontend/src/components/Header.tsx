import { useStore } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { AddTickerDialog } from './AddTickerDialog';
import {
  Activity,
  Wifi,
  WifiOff,
  Play,
  Square,
  TrendingUp,
  TrendingDown,
  Zap,
  Command,
  Banknote,
  Wallet,
  PiggyBank,
} from 'lucide-react';

export function Header() {
  const { send } = useWebSocket();
  const connected = useStore((s) => s.connected);
  const running = useStore((s) => s.running);
  const marketOpen = useStore((s) => s.marketOpen);
  const profits = useStore((s) => s.profits);
  const tickers = useStore((s) => s.tickers);
  const cashReserve = useStore((s) => s.cashReserve);
  const accountBalance = useStore((s) => s.accountBalance);
  const allocated = useStore((s) => s.allocated);
  const available = useStore((s) => s.available);

  const totalPnl = Object.values(profits).reduce((a, b) => a + b, 0);
  const tickerCount = Object.keys(tickers).length;
  const activeTickers = Object.values(tickers).filter((t) => t.enabled).length;

  // Compute allocated from local ticker state (real-time)
  const localAllocated = Object.values(tickers).reduce((s, t) => s + (t.base_power ?? 0), 0);
  const effectiveAllocated = localAllocated || allocated;
  const effectiveAvailable = accountBalance - effectiveAllocated;

  return (
    <header className="glass border-b border-border px-6 py-3" data-testid="header">
      <div className="flex items-center justify-between">
        {/* Left: Brand + Status */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <div className="relative">
              <Activity className="w-7 h-7 text-primary" />
              {running && (
                <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
              )}
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-foreground" data-testid="app-title">
                BracketBot
              </h1>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium">
                Terminal v3.0
              </p>
            </div>
          </div>

          {/* Status pills */}
          <div className="flex items-center gap-3">
            <span
              data-testid="connection-status"
              className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${
                connected
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  : 'bg-red-500/10 text-red-400 border border-red-500/20'
              }`}
            >
              {connected ? <Wifi size={12} /> : <WifiOff size={12} />}
              {connected ? 'Connected' : 'Offline'}
            </span>
            <span
              data-testid="market-status"
              className={`text-xs font-medium px-2.5 py-1 rounded-full border ${
                marketOpen
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
              }`}
            >
              {marketOpen ? 'Market Open' : 'Market Closed'}
            </span>
          </div>
        </div>

        {/* Center: Metrics */}
        <div className="hidden lg:flex items-center gap-6">
          {accountBalance > 0 && (
            <>
              <MetricPill
                testId="metric-balance"
                label="Account"
                value={`$${accountBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                icon={Wallet}
              />
              <MetricPill
                testId="metric-allocated"
                label="Allocated"
                value={`$${effectiveAllocated.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                icon={Zap}
              />
              <MetricPill
                testId="metric-available"
                label="Available"
                value={`$${effectiveAvailable.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                positive={effectiveAvailable >= 0}
                icon={PiggyBank}
              />
            </>
          )}
          <MetricPill
            testId="metric-pnl"
            label="Total P&L"
            value={`${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`}
            positive={totalPnl >= 0}
            icon={totalPnl >= 0 ? TrendingUp : TrendingDown}
          />
          {cashReserve > 0 && (
            <MetricPill
              testId="metric-cash"
              label="Cash Reserve"
              value={`$${cashReserve.toFixed(2)}`}
              positive={true}
              icon={Banknote}
            />
          )}
        </div>

        {/* Right: Controls */}
        <div className="flex items-center gap-3">
          <div className="hidden md:flex items-center gap-1 text-[10px] text-muted-foreground border border-border rounded px-2 py-1">
            <Command size={10} /> K
          </div>

          <AddTickerDialog />

          {!running ? (
            <button
              data-testid="start-bot-btn"
              onClick={() => send('START_BOT')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all"
            >
              <Play size={13} fill="currentColor" /> Start Bot
            </button>
          ) : (
            <button
              data-testid="stop-bot-btn"
              onClick={() => send('STOP_BOT')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-all"
            >
              <Square size={13} fill="currentColor" /> Stop Bot
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

function MetricPill({
  label,
  value,
  positive,
  icon: Icon,
  testId,
}: {
  label: string;
  value: string;
  positive?: boolean;
  icon: any;
  testId: string;
}) {
  return (
    <div className="flex items-center gap-2" data-testid={testId}>
      <Icon
        size={14}
        className={
          positive === undefined
            ? 'text-primary'
            : positive
            ? 'text-emerald-400'
            : 'text-red-400'
        }
      />
      <div>
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
        <p
          className={`font-mono text-sm font-bold tracking-tight ${
            positive === undefined
              ? 'text-foreground'
              : positive
              ? 'text-emerald-400'
              : 'text-red-400'
          }`}
        >
          {value}
        </p>
      </div>
    </div>
  );
}
