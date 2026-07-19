import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { uiLog } from '@/lib/clientLogger';
import { toast } from 'sonner';
import { TestConnectionModal } from './BrokersTestConnectionModal';
import { AlertTriangle, ExternalLink, CheckCircle2, Lock, Plug, DollarSign, Settings2, Gauge, Activity, ChevronDown, ChevronUp, FlaskConical } from 'lucide-react';
import { GeneralApiSection } from './GeneralApiSection';

interface BrokerRiskWarning {
  level: 'low' | 'medium' | 'high';
  message: string;
}

interface BrokerData {
  id: string;
  name: string;
  description: string;
  supported: boolean;
  readiness?: 'production' | 'beta' | 'experimental' | 'unavailable';
  readiness_note?: string;
  auth_fields: string[];
  docs_url: string;
  color: string;
  risk_warning: BrokerRiskWarning | null;
}

interface RateLimitConfig {
  requests_per_minute: number;
  requests_per_second: number;
  burst_limit: number;
  failure_threshold: number;
  recovery_timeout_seconds: number;
}

interface RateLimitStatus {
  broker_id: string;
  circuit_state: string;
  failure_count: number;
  requests_last_minute: number;
  requests_last_second: number;
  concurrent_requests: number;
  limits: RateLimitConfig;
  recovery_remaining_seconds: number | null;
}


const RISK_COLORS: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  low: { bg: 'bg-emerald-500/5', border: 'border-emerald-500/20', text: 'text-emerald-400', badge: 'bg-emerald-500/15 text-emerald-400' },
  medium: { bg: 'bg-amber-500/5', border: 'border-amber-500/20', text: 'text-amber-400', badge: 'bg-amber-500/15 text-amber-400' },
  high: { bg: 'bg-red-500/5', border: 'border-red-500/20', text: 'text-red-400', badge: 'bg-red-500/15 text-red-400' },
};

const READINESS_STYLES: Record<NonNullable<BrokerData['readiness']>, string> = {
  production: 'bg-emerald-500/15 text-emerald-400',
  beta: 'bg-sky-500/15 text-sky-400',
  experimental: 'bg-amber-500/15 text-amber-400',
  unavailable: 'bg-secondary text-muted-foreground',
};

const READINESS_LABELS: Record<NonNullable<BrokerData['readiness']>, string> = {
  production: 'Official API',
  beta: 'Beta',
  experimental: 'Experimental',
  unavailable: 'Unavailable',
};

export function BrokersTab() {
  const [brokers, setBrokers] = useState<BrokerData[]>([]);
  const [loading, setLoading] = useState(true);
  const [testBroker, setTestBroker] = useState<BrokerData | null>(null);
  const [connectedInfo, setConnectedInfo] = useState<Record<string, { buyingPower: number; balance: number }>>({});

  useEffect(() => {
    async function loadBrokers() {
      try {
        const data = await apiFetch('/api/brokers');
        setBrokers(data);
      } catch (err) {
        uiLog.error('brokers.load_failed', err, { retrying: true });
        // Retry once after 2s in case backend was starting up
        setTimeout(async () => {
          try {
            const data = await apiFetch('/api/brokers');
            setBrokers(data);
          } catch (retryErr) {
            uiLog.error('brokers.load_retry_failed', retryErr);
          }
        }, 2000);
      } finally {
        setLoading(false);
      }
    }
    loadBrokers();
  }, []);

  const handleTestResult = (brokerId: string, buyingPower: number, balance: number) => {
    setConnectedInfo((prev) => ({ ...prev, [brokerId]: { buyingPower, balance } }));
  };

  if (loading) {
    return <div className="text-muted-foreground text-sm animate-pulse p-4" data-testid="brokers-loading">Loading brokers...</div>;
  }

  return (
    <div className="space-y-4" data-testid="brokers-tab">
      <div className="flex items-center gap-3 mb-2">
        <Plug size={18} className="text-primary" />
        <div>
          <h2 className="text-base font-semibold text-foreground">Broker Connections</h2>
          <p className="text-xs text-muted-foreground">Connect a live broker to enable real trading. Use Test Connection to validate credentials.</p>
        </div>
      </div>

      <div className="grid gap-3">
        <GeneralApiSection />
        {brokers.map((broker) => (
          <BrokerCard key={broker.id} broker={broker} onTestClick={() => setTestBroker(broker)} accountInfo={connectedInfo[broker.id]} />
        ))}
      </div>

      {testBroker && (
        <TestConnectionModal broker={testBroker} onClose={() => setTestBroker(null)} onConnected={handleTestResult} />
      )}
    </div>
  );
}

function BrokerCard({ broker, onTestClick, accountInfo }: { broker: BrokerData; onTestClick: () => void; accountInfo?: { buyingPower: number; balance: number } }) {
  const risk = broker.risk_warning;
  const colors = risk ? RISK_COLORS[risk.level] || RISK_COLORS.medium : RISK_COLORS.low;
  const readiness = broker.readiness || (broker.supported ? 'beta' : 'unavailable');
  const readinessClass = READINESS_STYLES[readiness];
  const [showConfig, setShowConfig] = useState(false);
  const [rateLimitStatus, setRateLimitStatus] = useState<RateLimitStatus | null>(null);
  const [useBrokerPrices, setUseBrokerPrices] = useState(false);

  // Load rate limit status when expanded
  useEffect(() => {
    if (showConfig && accountInfo) {
      apiFetch(`/api/rate-limits/${broker.id}`)
        .then((data) => setRateLimitStatus(data))
        .catch(() => {});
    }
  }, [showConfig, accountInfo, broker.id]);

  return (
    <div className={`border rounded-xl overflow-hidden transition-all ${colors.border} ${colors.bg}`} data-testid={`broker-card-${broker.id}`}>
      <div className="flex">
        <div className="w-1 shrink-0" style={{ backgroundColor: broker.color }} />
        <div className="flex-1 p-4">
          <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <h3 className="text-sm font-semibold text-foreground">{broker.name}</h3>
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-full ${readinessClass}`} data-testid={`broker-status-${broker.id}`}>
              {broker.supported ? <CheckCircle2 size={10} /> : <Lock size={10} />}
              {READINESS_LABELS[readiness]}
            </span>
            {risk && (
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-full ${colors.badge}`} data-testid={`broker-risk-badge-${broker.id}`}>
                Risk: {risk.level.toUpperCase()}
              </span>
            )}
            {accountInfo && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-cyan-500/15 text-cyan-400 font-mono" data-testid={`broker-buying-power-${broker.id}`}>
                <DollarSign size={10} /> BP: ${accountInfo.buyingPower.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mb-2">{broker.description}</p>
          {broker.readiness_note && (
            <p className="text-[11px] text-muted-foreground mb-2" data-testid={`broker-readiness-note-${broker.id}`}>
              {broker.readiness_note}
            </p>
          )}
          {risk && (
            <div className={`flex items-start gap-2 text-xs leading-relaxed px-3 py-2 rounded-lg border ${colors.border} ${colors.bg}`} data-testid={`broker-warning-${broker.id}`}>
              <AlertTriangle size={14} className={`shrink-0 mt-0.5 ${colors.text}`} />
              <span className={colors.text}>{risk.message}</span>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2 shrink-0">
          {broker.docs_url && (
            <a href={broker.docs_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors" data-testid={`broker-docs-${broker.id}`}>
              <ExternalLink size={12} /> Docs
            </a>
          )}
          <button
            onClick={onTestClick}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
            data-testid={`broker-test-${broker.id}`}
          >
            <FlaskConical size={12} /> Test
          </button>
          <button
            onClick={onTestClick}
            disabled={!broker.supported}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              broker.supported ? 'bg-primary text-primary-foreground hover:bg-primary/90' : 'bg-secondary text-muted-foreground/50 cursor-not-allowed'
            }`}
            data-testid={`broker-connect-${broker.id}`}
          >
            {broker.supported && readiness === 'experimental' ? 'Connect Experimental' : broker.supported ? 'Connect' : 'Unavailable'}
          </button>
          {accountInfo && (
            <button
              onClick={() => setShowConfig(!showConfig)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              data-testid={`broker-config-toggle-${broker.id}`}
            >
              <Settings2 size={12} /> {showConfig ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
          )}
        </div>
      </div>

      {/* Configuration Panel */}
      {showConfig && accountInfo && (
        <BrokerConfigPanel 
          brokerId={broker.id} 
          brokerName={broker.name}
          rateLimitStatus={rateLimitStatus}
          useBrokerPrices={useBrokerPrices}
          setUseBrokerPrices={setUseBrokerPrices}
          onRateLimitUpdate={(status) => setRateLimitStatus(status)}
        />
      )}
        </div>
      </div>
    </div>
  );
}

function BrokerConfigPanel({ 
  brokerId, 
  brokerName,
  rateLimitStatus, 
  useBrokerPrices,
  setUseBrokerPrices,
  onRateLimitUpdate 
}: { 
  brokerId: string; 
  brokerName: string;
  rateLimitStatus: RateLimitStatus | null;
  useBrokerPrices: boolean;
  setUseBrokerPrices: (v: boolean) => void;
  onRateLimitUpdate: (status: RateLimitStatus) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<RateLimitConfig>({
    requests_per_minute: 60,
    requests_per_second: 5,
    burst_limit: 10,
    failure_threshold: 5,
    recovery_timeout_seconds: 60,
  });

  useEffect(() => {
    if (rateLimitStatus?.limits) {
      setConfig(rateLimitStatus.limits);
    }
  }, [rateLimitStatus]);

  const saveRateLimits = async () => {
    setSaving(true);
    try {
      const params = new URLSearchParams({
        requests_per_minute: String(config.requests_per_minute),
        requests_per_second: String(config.requests_per_second),
        burst_limit: String(config.burst_limit),
        failure_threshold: String(config.failure_threshold),
        recovery_timeout_seconds: String(config.recovery_timeout_seconds),
      });
      const res = await apiFetch(`/api/rate-limits/${brokerId}?${params}`, { method: 'POST' });
      onRateLimitUpdate(res.config);
      toast.success('Rate limits updated');
    } catch (err) {
      toast.error('Failed to update rate limits');
    } finally {
      setSaving(false);
    }
  };

  const toggleBrokerPrices = async () => {
    try {
      await apiFetch(`/api/price-sources/toggle?prefer_broker=${!useBrokerPrices}`, { method: 'POST' });
      setUseBrokerPrices(!useBrokerPrices);
      toast.success(useBrokerPrices ? 'Using yfinance for prices' : `Using ${brokerName} for prices`);
    } catch (err) {
      toast.error('Failed to update price source');
    }
  };

  return (
    <div className="border-t border-border bg-secondary/20 p-4 space-y-4">
      <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
        <Settings2 size={14} className="text-primary" />
        Broker Configuration
      </div>

      {/* Price Feed Toggle */}
      <div className="rounded-lg border border-border bg-background/50 p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity size={12} className="text-accent" />
            <span className="text-xs font-medium">Use {brokerName} Price Feed</span>
          </div>
          <button
            onClick={toggleBrokerPrices}
            className={`relative w-10 h-5 rounded-full transition-colors ${useBrokerPrices ? 'bg-emerald-500' : 'bg-secondary'}`}
            data-testid={`broker-price-toggle-${brokerId}`}
          >
            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${useBrokerPrices ? 'translate-x-5' : 'translate-x-0.5'}`} />
          </button>
        </div>
        <p className="text-[10px] text-muted-foreground">
          {useBrokerPrices 
            ? `Real-time prices from ${brokerName}'s WebSocket feed. Lower latency.`
            : 'Using yfinance for price data. Falls back if broker feed unavailable.'}
        </p>
      </div>

      {/* Rate Limits */}
      <div className="rounded-lg border border-border bg-background/50 p-3 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Gauge size={12} className="text-accent" />
            <span className="text-xs font-medium">Rate Limits</span>
          </div>
          {rateLimitStatus && (
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
              rateLimitStatus.circuit_state === 'closed'
                ? 'bg-emerald-500/10 text-emerald-400'
                : rateLimitStatus.circuit_state === 'open'
                ? 'bg-red-500/10 text-red-400'
                : 'bg-amber-500/10 text-amber-400'
            }`}>
              Circuit: {rateLimitStatus.circuit_state.toUpperCase()}
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="text-[10px] text-muted-foreground block mb-1">Requests/Min</label>
            <select
              value={config.requests_per_minute}
              onChange={(e) => setConfig({ ...config, requests_per_minute: Number(e.target.value) })}
              className="w-full bg-secondary border border-border rounded px-2 py-1 text-xs"
              data-testid={`broker-rpm-${brokerId}`}
            >
              {[10, 20, 30, 60, 100, 200].map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-muted-foreground block mb-1">Requests/Sec</label>
            <select
              value={config.requests_per_second}
              onChange={(e) => setConfig({ ...config, requests_per_second: Number(e.target.value) })}
              className="w-full bg-secondary border border-border rounded px-2 py-1 text-xs"
              data-testid={`broker-rps-${brokerId}`}
            >
              {[1, 2, 3, 5, 10, 20].map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-muted-foreground block mb-1">Burst Limit</label>
            <select
              value={config.burst_limit}
              onChange={(e) => setConfig({ ...config, burst_limit: Number(e.target.value) })}
              className="w-full bg-secondary border border-border rounded px-2 py-1 text-xs"
              data-testid={`broker-burst-${brokerId}`}
            >
              {[3, 5, 10, 15, 20, 30].map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-muted-foreground block mb-1">Failure Threshold</label>
            <select
              value={config.failure_threshold}
              onChange={(e) => setConfig({ ...config, failure_threshold: Number(e.target.value) })}
              className="w-full bg-secondary border border-border rounded px-2 py-1 text-xs"
              data-testid={`broker-failures-${brokerId}`}
            >
              {[2, 3, 5, 10, 15].map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="text-[10px] text-muted-foreground block mb-1">Recovery Timeout (seconds)</label>
          <select
            value={config.recovery_timeout_seconds}
            onChange={(e) => setConfig({ ...config, recovery_timeout_seconds: Number(e.target.value) })}
            className="w-full bg-secondary border border-border rounded px-2 py-1 text-xs"
            data-testid={`broker-recovery-${brokerId}`}
          >
            {[30, 60, 120, 180, 300, 600].map((v) => (
              <option key={v} value={v}>{v}s ({v / 60} min)</option>
            ))}
          </select>
        </div>

        <button
          onClick={saveRateLimits}
          disabled={saving}
          className="w-full py-1.5 text-xs font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          data-testid={`broker-save-limits-${brokerId}`}
        >
          {saving ? 'Saving...' : 'Save Rate Limits'}
        </button>

        {rateLimitStatus && (
          <div className="text-[10px] text-muted-foreground pt-2 border-t border-border/50">
            <span className="font-mono">{rateLimitStatus.requests_last_minute}/{config.requests_per_minute}</span> requests/min -
            <span className="font-mono ml-1">{rateLimitStatus.failure_count}</span> failures
            {rateLimitStatus.recovery_remaining_seconds && (
              <span className="ml-1 text-amber-400">- Recovery in {Math.round(rateLimitStatus.recovery_remaining_seconds)}s</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
