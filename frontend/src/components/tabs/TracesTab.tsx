import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '@/lib/api';
import { Activity, RefreshCw, Search, Clock, Zap } from 'lucide-react';

interface SpanEvent {
  name: string;
  timestamp: number;
  attributes: Record<string, any>;
}

interface Span {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: string;
  status: string;
  start_time: number;
  end_time: number;
  duration_ms: number;
  attributes: Record<string, any>;
  events: SpanEvent[];
}

const STATUS_COLORS: Record<string, string> = {
  OK: 'text-emerald-400',
  UNSET: 'text-muted-foreground',
  ERROR: 'text-red-400',
};

const KIND_BADGE: Record<string, string> = {
  INTERNAL: 'bg-secondary text-muted-foreground',
  SERVER: 'bg-blue-500/15 text-blue-400',
  CLIENT: 'bg-amber-500/15 text-amber-400',
};

export function TracesTab() {
  const [spans, setSpans] = useState<Span[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ limit: '200' });
    if (filter) params.set('name', filter);
    apiFetch(`/api/traces?${params}`)
      .then((d) => setSpans(d.spans || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const tradeSpans = spans.filter((s) => s.name.startsWith('trade.'));
  const evalSpans = spans.filter((s) => s.name.startsWith('ticker.'));
  const httpSpans = spans.filter((s) => s.name.startsWith('HTTP') || s.name.startsWith('GET') || s.name.startsWith('POST'));

  return (
    <div className="space-y-4" data-testid="traces-tab">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Activity size={18} className="text-primary" />
          <div>
            <h2 className="text-base font-semibold text-foreground">OpenTelemetry Traces</h2>
            <p className="text-xs text-muted-foreground">{spans.length} spans captured in memory</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              data-testid="traces-filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by span name..."
              className="pl-8 pr-3 py-1.5 text-xs bg-secondary border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-foreground placeholder:text-muted-foreground/40 w-48"
            />
          </div>
          <button onClick={load} disabled={loading} className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors" data-testid="traces-refresh">
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Trade Executions" count={tradeSpans.length} icon={Zap} color="text-emerald-400" />
        <StatCard label="Ticker Evaluations" count={evalSpans.length} icon={Activity} color="text-blue-400" />
        <StatCard label="HTTP Requests" count={httpSpans.length} icon={Clock} color="text-amber-400" />
      </div>

      {/* Span list */}
      <div className="border border-border rounded-xl overflow-hidden" data-testid="traces-list">
        <div className="grid grid-cols-[1fr_100px_80px_70px] gap-2 px-4 py-2 text-[10px] uppercase tracking-wider text-muted-foreground font-medium bg-secondary/30 border-b border-border">
          <span>Span Name</span>
          <span>Kind</span>
          <span>Status</span>
          <span className="text-right">Duration</span>
        </div>
        <div className="max-h-[480px] overflow-auto divide-y divide-border">
          {spans.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">
              {loading ? 'Loading...' : 'No spans captured yet. Traces appear as the bot runs.'}
            </div>
          )}
          {spans.map((span) => (
            <SpanRow key={span.span_id} span={span} expanded={expanded === span.span_id} onToggle={() => setExpanded(expanded === span.span_id ? null : span.span_id)} />
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, count, icon: Icon, color }: { label: string; count: number; icon: any; color: string }) {
  return (
    <div className="border border-border rounded-lg px-4 py-3 bg-secondary/20">
      <div className="flex items-center gap-2 mb-1">
        <Icon size={13} className={color} />
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</span>
      </div>
      <span className={`text-xl font-bold font-mono ${color}`}>{count}</span>
    </div>
  );
}

function SpanRow({ span, expanded, onToggle }: { span: Span; expanded: boolean; onToggle: () => void }) {
  const statusColor = STATUS_COLORS[span.status] || STATUS_COLORS.UNSET;
  const kindBadge = KIND_BADGE[span.kind] || KIND_BADGE.INTERNAL;
  const hasAttrs = Object.keys(span.attributes).length > 0;
  const hasEvents = span.events.length > 0;

  return (
    <div>
      <button onClick={onToggle} className="w-full grid grid-cols-[1fr_100px_80px_70px] gap-2 px-4 py-2.5 text-left hover:bg-secondary/30 transition-colors" data-testid={`span-row-${span.span_id}`}>
        <span className="text-xs font-medium text-foreground truncate">{span.name}</span>
        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full w-fit ${kindBadge}`}>{span.kind}</span>
        <span className={`text-xs font-medium ${statusColor}`}>{span.status}</span>
        <span className="text-xs font-mono text-muted-foreground text-right">{span.duration_ms}ms</span>
      </button>
      {expanded && (hasAttrs || hasEvents) && (
        <div className="px-4 pb-3 space-y-2">
          {hasAttrs && (
            <div className="bg-secondary/30 border border-border rounded-lg p-3">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">Attributes</p>
              <div className="grid gap-1">
                {Object.entries(span.attributes).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground font-mono">{k}:</span>
                    <span className="text-foreground font-mono">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {hasEvents && (
            <div className="bg-secondary/30 border border-border rounded-lg p-3">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5">Events</p>
              {span.events.map((ev, i) => (
                <div key={i} className="text-xs text-foreground font-mono">
                  {ev.name} {Object.keys(ev.attributes).length > 0 && `— ${JSON.stringify(ev.attributes)}`}
                </div>
              ))}
            </div>
          )}
          <div className="text-[10px] text-muted-foreground/50 font-mono">
            trace: {span.trace_id.slice(0, 16)}... | span: {span.span_id}
            {span.parent_span_id && ` | parent: ${span.parent_span_id}`}
          </div>
        </div>
      )}
    </div>
  );
}
