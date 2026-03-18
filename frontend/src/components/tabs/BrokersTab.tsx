import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { AlertTriangle, ExternalLink, CheckCircle2, Lock, Plug } from 'lucide-react';

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
  risk_warning: BrokerRiskWarning | null;
}

const RISK_COLORS: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  low: { bg: 'bg-emerald-500/5', border: 'border-emerald-500/20', text: 'text-emerald-400', badge: 'bg-emerald-500/15 text-emerald-400' },
  medium: { bg: 'bg-amber-500/5', border: 'border-amber-500/20', text: 'text-amber-400', badge: 'bg-amber-500/15 text-amber-400' },
  high: { bg: 'bg-red-500/5', border: 'border-red-500/20', text: 'text-red-400', badge: 'bg-red-500/15 text-red-400' },
};

export function BrokersTab() {
  const [brokers, setBrokers] = useState<BrokerData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch('/api/brokers')
      .then((data) => setBrokers(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="text-muted-foreground text-sm animate-pulse p-4" data-testid="brokers-loading">Loading brokers...</div>;
  }

  return (
    <div className="space-y-4" data-testid="brokers-tab">
      <div className="flex items-center gap-3 mb-2">
        <Plug size={18} className="text-primary" />
        <div>
          <h2 className="text-base font-semibold text-foreground">Broker Connections</h2>
          <p className="text-xs text-muted-foreground">Connect a live broker to enable real trading. Review risk warnings carefully.</p>
        </div>
      </div>

      <div className="grid gap-3">
        {brokers.map((broker) => (
          <BrokerCard key={broker.id} broker={broker} />
        ))}
      </div>
    </div>
  );
}

function BrokerCard({ broker }: { broker: BrokerData }) {
  const risk = broker.risk_warning;
  const colors = risk ? RISK_COLORS[risk.level] || RISK_COLORS.medium : RISK_COLORS.low;

  return (
    <div
      className={`border rounded-xl p-4 transition-all ${colors.border} ${colors.bg}`}
      data-testid={`broker-card-${broker.id}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
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
            <a
              href={broker.docs_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
              data-testid={`broker-docs-${broker.id}`}
            >
              <ExternalLink size={12} /> Docs
            </a>
          )}
          <button
            disabled={!broker.supported}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              broker.supported
                ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                : 'bg-secondary text-muted-foreground/50 cursor-not-allowed'
            }`}
            data-testid={`broker-connect-${broker.id}`}
          >
            {broker.supported ? 'Connect' : 'Unavailable'}
          </button>
        </div>
      </div>
    </div>
  );
}
