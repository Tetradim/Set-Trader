import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { useStore } from '@/stores/useStore';
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  RefreshCw,
  Settings,
  ShieldCheck,
  XCircle,
} from 'lucide-react';

type PreflightStatus = 'pass' | 'warn' | 'fail';

type PreflightCheck = {
  id: string;
  label: string;
  status: PreflightStatus;
  detail: string;
  action: string;
};

type PreflightResponse = {
  ready_to_trade: boolean;
  summary: Record<PreflightStatus, number>;
  checks: PreflightCheck[];
  context: {
    trading_mode: string;
    account_balance: number;
    allocated: number;
    available: number;
    enabled_tickers: number;
    connected_brokers: number;
    running: boolean;
    paused: boolean;
  };
};

const STATUS_STYLES: Record<PreflightStatus, string> = {
  pass: 'border-emerald-500/30 bg-emerald-500/8 text-emerald-300',
  warn: 'border-amber-500/30 bg-amber-500/8 text-amber-300',
  fail: 'border-red-500/30 bg-red-500/8 text-red-300',
};

function StatusIcon({ status }: { status: PreflightStatus }) {
  if (status === 'pass') return <CheckCircle2 size={16} />;
  if (status === 'warn') return <AlertTriangle size={16} />;
  return <XCircle size={16} />;
}

export function PreflightTab() {
  const setActiveTab = useStore((state) => state.setActiveTab);
  const [data, setData] = useState<PreflightResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadPreflight = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await apiFetch('/api/preflight');
      setData(response);
    } catch (err: any) {
      setError(err.message || 'Unable to load preflight checks');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPreflight();
  }, [loadPreflight]);

  const blockingChecks = useMemo(
    () => data?.checks.filter((check) => check.status === 'fail') ?? [],
    [data],
  );

  const warningChecks = useMemo(
    () => data?.checks.filter((check) => check.status === 'warn') ?? [],
    [data],
  );

  return (
    <div className="space-y-5" data-testid="preflight-tab">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <ShieldCheck size={20} className="text-primary" />
          <div>
            <h2 className="text-base font-semibold text-foreground">Beta Preflight</h2>
            <p className="text-xs text-muted-foreground">Release checks before testers start or connect live accounts</p>
          </div>
        </div>
        <button
          type="button"
          onClick={loadPreflight}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-secondary px-3 py-2 text-xs font-semibold text-foreground hover:border-primary/50 disabled:opacity-60"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {data && (
        <>
          <section className={`rounded-xl border p-5 ${data.ready_to_trade ? 'border-emerald-500/25 bg-emerald-500/8' : 'border-red-500/25 bg-red-500/8'}`}>
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  {data.ready_to_trade ? <CheckCircle2 size={18} className="text-emerald-300" /> : <CircleAlert size={18} className="text-red-300" />}
                  <h3 className="text-sm font-bold text-foreground">
                    {data.ready_to_trade ? 'Ready to trade' : 'Preflight blocked'}
                  </h3>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {data.ready_to_trade
                    ? `${data.summary.warn} warning(s) remain. Review before live trading.`
                    : `${blockingChecks.length} required check(s) need attention.`}
                </p>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <Metric label="Pass" value={data.summary.pass} tone="text-emerald-300" />
                <Metric label="Warn" value={data.summary.warn} tone="text-amber-300" />
                <Metric label="Fail" value={data.summary.fail} tone="text-red-300" />
              </div>
            </div>
          </section>

          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Mode" value={data.context.trading_mode.toUpperCase()} />
            <MetricCard label="Balance" value={`$${data.context.account_balance.toLocaleString()}`} />
            <MetricCard label="Available" value={`$${data.context.available.toLocaleString()}`} />
            <MetricCard label="Brokers" value={data.context.connected_brokers} />
          </section>

          {(blockingChecks.length > 0 || warningChecks.length > 0) && (
            <section className="rounded-xl border border-border bg-card/60 p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <Settings size={15} className="text-primary" />
                Next actions
              </div>
              <div className="space-y-2">
                {[...blockingChecks, ...warningChecks].map((check) => (
                  <div key={`action-${check.id}`} className="rounded-lg border border-border bg-secondary/40 px-3 py-2">
                    <div className="text-xs font-semibold text-foreground">{check.label}</div>
                    <div className="mt-0.5 text-xs text-muted-foreground">{check.action}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button type="button" onClick={() => setActiveTab('settings')} className="rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground">
                  Open Settings
                </button>
                <button type="button" onClick={() => setActiveTab('brokers')} className="rounded-lg border border-border bg-secondary px-3 py-2 text-xs font-semibold text-foreground">
                  Open Brokers
                </button>
                <button type="button" onClick={() => setActiveTab('watchlist')} className="rounded-lg border border-border bg-secondary px-3 py-2 text-xs font-semibold text-foreground">
                  Open Watchlist
                </button>
              </div>
            </section>
          )}

          <section className="grid gap-3 md:grid-cols-2">
            {data.checks.map((check) => (
              <div key={check.id} className={`rounded-xl border p-4 ${STATUS_STYLES[check.status]}`}>
                <div className="flex items-start gap-3">
                  <StatusIcon status={check.status} />
                  <div>
                    <div className="text-sm font-semibold text-foreground">{check.label}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{check.detail}</div>
                  </div>
                </div>
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="min-w-[60px] rounded-lg border border-border bg-background/40 px-3 py-2">
      <div className={`font-mono text-lg font-bold ${tone}`}>{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-4">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-lg font-bold text-foreground">{value}</div>
    </div>
  );
}
