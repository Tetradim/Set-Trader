import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { AlertTriangle, ExternalLink, CheckCircle2, Lock, Plug, FlaskConical, X, Loader2, DollarSign } from 'lucide-react';
import { toast } from 'sonner';

interface BrokerRiskWarning {
  level: 'low' | 'medium' | 'high';
  message: string;
}

interface BrokerData {
  id: string;
  name: string;
  description: string;
  supported: boolean;
  auth_fields: string[];
  docs_url: string;
  color: string;
  risk_warning: BrokerRiskWarning | null;
}

interface TestCheck {
  name: string;
  status: 'pass' | 'fail' | 'warn';
  message: string;
}

interface TestResult {
  broker_id: string;
  broker_name: string;
  checks: TestCheck[];
  overall: 'pass' | 'fail' | 'partial';
}

const RISK_COLORS: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  low: { bg: 'bg-emerald-500/5', border: 'border-emerald-500/20', text: 'text-emerald-400', badge: 'bg-emerald-500/15 text-emerald-400' },
  medium: { bg: 'bg-amber-500/5', border: 'border-amber-500/20', text: 'text-amber-400', badge: 'bg-amber-500/15 text-amber-400' },
  high: { bg: 'bg-red-500/5', border: 'border-red-500/20', text: 'text-red-400', badge: 'bg-red-500/15 text-red-400' },
};

const CHECK_STATUS_STYLES: Record<string, string> = {
  pass: 'text-emerald-400',
  fail: 'text-red-400',
  warn: 'text-amber-400',
};

const FIELD_LABELS: Record<string, string> = {
  username: 'Username',
  password: 'Password',
  mfa_code: 'MFA Code (6-digit)',
  email: 'Email',
  api_key: 'API Key',
  api_secret: 'API Secret',
  paper: 'Paper Trading (true/false)',
  gateway_url: 'TWS/Gateway URL',
  account_id: 'Account ID',
  client_id: 'Client ID (Schwab App Key)',
  refresh_token: 'Refresh Token',
  access_token: 'Access Token',
  device_id: 'Device ID',
  trade_token: 'Trade Token / PIN',
  ts_client_id: 'TradeStation Client ID',
  ts_client_secret: 'TradeStation Client Secret',
  ts_refresh_token: 'TradeStation Refresh Token',
  tos_consumer_key: 'Consumer Key (Schwab)',
  tos_refresh_token: 'Refresh Token (Schwab)',
  tos_account_id: 'Account ID',
  ws_email: 'Wealthsimple Email',
  ws_password: 'Wealthsimple Password',
  ws_otp_code: 'One-Time Password',
};

export function BrokersTab() {
  const [brokers, setBrokers] = useState<BrokerData[]>([]);
  const [loading, setLoading] = useState(true);
  const [testBroker, setTestBroker] = useState<BrokerData | null>(null);
  const [connectedInfo, setConnectedInfo] = useState<Record<string, { buyingPower: number; balance: number }>>({});

  useEffect(() => {
    apiFetch('/api/brokers')
      .then((data) => setBrokers(data))
      .catch(() => {})
      .finally(() => setLoading(false));
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

  return (
    <div className={`border rounded-xl overflow-hidden transition-all ${colors.border} ${colors.bg}`} data-testid={`broker-card-${broker.id}`}>
      <div className="flex">
        <div className="w-1 shrink-0" style={{ backgroundColor: broker.color }} />
        <div className="flex-1 p-4">
          <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <h3 className="text-sm font-semibold text-foreground">{broker.name}</h3>
            {broker.supported ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-full bg-emerald-500/15 text-emerald-400" data-testid={`broker-status-${broker.id}`}>
                <CheckCircle2 size={10} /> Available
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-full bg-secondary text-muted-foreground" data-testid={`broker-status-${broker.id}`}>
                <Lock size={10} /> Coming Soon
              </span>
            )}
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
            disabled={!broker.supported}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              broker.supported ? 'bg-primary text-primary-foreground hover:bg-primary/90' : 'bg-secondary text-muted-foreground/50 cursor-not-allowed'
            }`}
            data-testid={`broker-connect-${broker.id}`}
          >
            {broker.supported ? 'Connect' : 'Unavailable'}
          </button>
        </div>
      </div>
        </div>
      </div>
    </div>
  );
}

function TestConnectionModal({ broker, onClose, onConnected }: { broker: BrokerData; onClose: () => void; onConnected: (brokerId: string, buyingPower: number, balance: number) => void }) {
  const [creds, setCreds] = useState<Record<string, string>>(() =>
    Object.fromEntries(broker.auth_fields.map((f) => [f, '']))
  );
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult | null>(null);

  const updateCred = (field: string, value: string) => {
    setCreds((prev) => ({ ...prev, [field]: value }));
  };

  const runTest = async (e: React.FormEvent) => {
    e.preventDefault();
    setTesting(true);
    setResult(null);
    try {
      const res = await apiFetch(`/api/brokers/${broker.id}/test`, {
        method: 'POST',
        body: JSON.stringify({ credentials: creds }),
      });
      setResult(res);
      if (res.overall === 'pass') {
        toast.success('Connection test passed!');
        // Extract buying power from account_access check
        const acctCheck = (res.checks || []).find((c: TestCheck) => c.name === 'account_access' && c.status === 'pass');
        if (acctCheck) {
          const bpMatch = acctCheck.message.match(/Buying Power: \$([\d,.]+)/);
          const balMatch = acctCheck.message.match(/Balance: \$([\d,.]+)/);
          const bp = bpMatch ? parseFloat(bpMatch[1].replace(/,/g, '')) : 0;
          const bal = balMatch ? parseFloat(balMatch[1].replace(/,/g, '')) : 0;
          onConnected(broker.id, bp, bal);
        }
      } else if (res.overall === 'partial') toast.info('Partial pass — see details below.');
      else toast.error('Connection test failed.');
    } catch (err: any) {
      toast.error(err.message || 'Test failed.');
    } finally {
      setTesting(false);
    }
  };

  const isPassword = (f: string) => ['password', 'mfa_code', 'api_secret', 'trade_token', 'ts_client_secret', 'ts_refresh_token', 'tos_refresh_token', 'ws_password', 'ws_otp_code', 'refresh_token', 'access_token'].includes(f);

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/70 backdrop-blur-sm" data-testid="broker-test-modal-overlay">
      <div className="glass border border-border rounded-2xl w-full max-w-md max-h-[90vh] flex flex-col shadow-2xl mx-4" data-testid="broker-test-modal">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Test Connection — {broker.name}</h2>
            <p className="text-[10px] text-muted-foreground">Full credential validation dry-run</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors" data-testid="broker-test-close-btn">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={runTest} className="flex-1 overflow-auto px-5 py-4 space-y-3">
          {broker.auth_fields.map((field) => (
            <div key={field}>
              <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium block mb-1">
                {FIELD_LABELS[field] || field}
              </label>
              <input
                data-testid={`broker-cred-${field}`}
                type={isPassword(field) ? 'password' : 'text'}
                value={creds[field] || ''}
                onChange={(e) => updateCred(field, e.target.value)}
                placeholder={field === 'port' ? '7497' : field === 'client_id' ? '1' : ''}
                className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1 focus:ring-offset-background text-foreground placeholder:text-muted-foreground/30"
              />
            </div>
          ))}

          {broker.risk_warning && broker.risk_warning.level === 'high' && (
            <div className="flex items-start gap-2 text-xs text-red-400 bg-red-500/5 border border-red-500/20 rounded-lg px-3 py-2">
              <AlertTriangle size={14} className="shrink-0 mt-0.5" />
              <span>This broker has a high risk of banning automated trading accounts. Proceed with caution.</span>
            </div>
          )}

          <button
            type="submit"
            disabled={testing}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg font-semibold text-sm bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg shadow-primary/20"
            data-testid="broker-test-run-btn"
          >
            {testing ? <><Loader2 size={13} className="animate-spin" /> Testing...</> : <><FlaskConical size={13} /> Run Test</>}
          </button>

          {result && (
            <div className="border border-border rounded-lg overflow-hidden" data-testid="broker-test-results">
              <div className={`px-4 py-2 text-xs font-semibold ${
                result.overall === 'pass' ? 'bg-emerald-500/10 text-emerald-400' :
                result.overall === 'partial' ? 'bg-amber-500/10 text-amber-400' :
                'bg-red-500/10 text-red-400'
              }`}>
                {result.overall === 'pass' ? 'All checks passed' : result.overall === 'partial' ? 'Partial pass' : 'Test failed'}
              </div>
              <div className="divide-y divide-border">
                {result.checks.map((check, i) => (
                  <div key={i} className="px-4 py-2.5 flex items-start gap-2">
                    <span className={`text-xs font-bold mt-0.5 ${CHECK_STATUS_STYLES[check.status] || 'text-muted-foreground'}`}>
                      {check.status === 'pass' ? 'PASS' : check.status === 'warn' ? 'WARN' : 'FAIL'}
                    </span>
                    <div className="flex-1">
                      <p className="text-xs font-medium text-foreground">{check.name.replace(/_/g, ' ')}</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">{check.message}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
