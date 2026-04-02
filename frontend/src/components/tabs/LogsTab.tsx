import { useState, useEffect, useCallback, useRef } from 'react';
import { apiFetch } from '@/lib/api';
import {
  RefreshCw, Filter, FileText, FolderOpen, ChevronDown, ChevronUp,
  AlertTriangle, X, Search, CheckCircle, XCircle, Activity,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Event type metadata
// ---------------------------------------------------------------------------

type Category = 'all' | 'trading' | 'broker' | 'config' | 'engine' | 'system';

const CATEGORY_EVENTS: Record<Exclude<Category, 'all'>, string[]> = {
  trading: ['BUY_EXECUTED', 'SELL_EXECUTED', 'STOP_TRIGGERED', 'TRAILING_STOP_TRIGGERED', 'MANUAL_SELL', 'REBRACKET_TRIGGERED'],
  broker:  ['BROKER_CONNECTED', 'BROKER_DISCONNECTED', 'BROKER_API_CALL', 'BROKER_API_ERROR', 'BROKER_RATE_LIMITED', 'BROKER_CIRCUIT_OPEN', 'BROKER_CIRCUIT_CLOSED'],
  config:  ['SETTING_CHANGED', 'TICKER_CREATED', 'TICKER_UPDATED', 'TICKER_DELETED'],
  engine:  ['ENGINE_STARTED', 'ENGINE_STOPPED', 'ENGINE_PAUSED', 'ENGINE_RESUMED', 'MODE_SWITCHED'],
  system:  ['SYSTEM_ERROR', 'PRICE_FEED_SWITCHED', 'TELEGRAM_SENT', 'TELEGRAM_FAILED'],
};

type BadgeStyle = { bg: string; text: string; border: string };

const EVENT_STYLES: Record<string, BadgeStyle> = {
  BUY_EXECUTED:             { bg: 'bg-emerald-500/15', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  SELL_EXECUTED:            { bg: 'bg-blue-500/15',    text: 'text-blue-400',    border: 'border-blue-500/30'    },
  STOP_TRIGGERED:           { bg: 'bg-red-500/15',     text: 'text-red-400',     border: 'border-red-500/30'     },
  TRAILING_STOP_TRIGGERED:  { bg: 'bg-amber-500/15',   text: 'text-amber-400',   border: 'border-amber-500/30'   },
  MANUAL_SELL:              { bg: 'bg-cyan-500/15',    text: 'text-cyan-400',    border: 'border-cyan-500/30'    },
  REBRACKET_TRIGGERED:      { bg: 'bg-orange-500/15',  text: 'text-orange-400',  border: 'border-orange-500/30'  },
  BROKER_CONNECTED:         { bg: 'bg-emerald-500/15', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  BROKER_DISCONNECTED:      { bg: 'bg-red-500/15',     text: 'text-red-400',     border: 'border-red-500/30'     },
  BROKER_API_CALL:          { bg: 'bg-blue-500/10',    text: 'text-blue-300',    border: 'border-blue-500/20'    },
  BROKER_API_ERROR:         { bg: 'bg-red-500/15',     text: 'text-red-400',     border: 'border-red-500/30'     },
  BROKER_RATE_LIMITED:      { bg: 'bg-amber-500/15',   text: 'text-amber-400',   border: 'border-amber-500/30'   },
  BROKER_CIRCUIT_OPEN:      { bg: 'bg-red-500/20',     text: 'text-red-300',     border: 'border-red-500/40'     },
  BROKER_CIRCUIT_CLOSED:    { bg: 'bg-emerald-500/15', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  SETTING_CHANGED:          { bg: 'bg-purple-500/15',  text: 'text-purple-400',  border: 'border-purple-500/30'  },
  TICKER_CREATED:           { bg: 'bg-violet-500/15',  text: 'text-violet-400',  border: 'border-violet-500/30'  },
  TICKER_UPDATED:           { bg: 'bg-violet-500/10',  text: 'text-violet-300',  border: 'border-violet-500/20'  },
  TICKER_DELETED:           { bg: 'bg-red-500/15',     text: 'text-red-400',     border: 'border-red-500/30'     },
  ENGINE_STARTED:           { bg: 'bg-emerald-500/15', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  ENGINE_STOPPED:           { bg: 'bg-red-500/15',     text: 'text-red-400',     border: 'border-red-500/30'     },
  ENGINE_PAUSED:            { bg: 'bg-amber-500/15',   text: 'text-amber-400',   border: 'border-amber-500/30'   },
  ENGINE_RESUMED:           { bg: 'bg-blue-500/15',    text: 'text-blue-400',    border: 'border-blue-500/30'    },
  MODE_SWITCHED:            { bg: 'bg-indigo-500/15',  text: 'text-indigo-400',  border: 'border-indigo-500/30'  },
  TELEGRAM_SENT:            { bg: 'bg-sky-500/15',     text: 'text-sky-400',     border: 'border-sky-500/30'     },
  TELEGRAM_FAILED:          { bg: 'bg-red-500/15',     text: 'text-red-400',     border: 'border-red-500/30'     },
  SYSTEM_ERROR:             { bg: 'bg-red-500/20',     text: 'text-red-300',     border: 'border-red-500/40'     },
  PRICE_FEED_SWITCHED:      { bg: 'bg-teal-500/15',    text: 'text-teal-400',    border: 'border-teal-500/30'    },
};

const DEFAULT_STYLE: BadgeStyle = { bg: 'bg-secondary', text: 'text-muted-foreground', border: 'border-border' };

function eventStyle(type: string): BadgeStyle {
  return EVENT_STYLES[type] ?? DEFAULT_STYLE;
}

function shortLabel(type: string): string {
  return type.replace(/_/g, ' ');
}

// ---------------------------------------------------------------------------
// Audit log row
// ---------------------------------------------------------------------------

type AuditEntry = {
  timestamp: string;
  event_type: string;
  symbol?: string;
  broker_id?: string;
  success: boolean;
  error_message?: string;
  details?: Record<string, unknown>;
};

function AuditRow({ entry }: { entry: AuditEntry }) {
  const [expanded, setExpanded] = useState(false);
  const s = eventStyle(entry.event_type);
  const ts = new Date(entry.timestamp);
  const timeStr = ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const dateStr = ts.toLocaleDateString([], { month: 'short', day: 'numeric' });

  return (
    <div className="border-b border-border/40 last:border-0" data-testid={`audit-row-${entry.event_type}`}>
      <button
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-secondary/30 transition-colors text-left"
        onClick={() => setExpanded((e) => !e)}
      >
        {/* Timestamp */}
        <span className="font-mono text-[10px] text-muted-foreground/60 w-32 shrink-0 text-right leading-tight">
          <span className="block">{dateStr}</span>
          <span className="block">{timeStr}</span>
        </span>

        {/* Event type badge */}
        <span className={`font-mono text-[9px] font-bold uppercase px-2 py-0.5 rounded border whitespace-nowrap ${s.bg} ${s.text} ${s.border}`}>
          {shortLabel(entry.event_type)}
        </span>

        {/* Symbol + broker */}
        <span className="flex items-center gap-1.5 min-w-0 flex-1">
          {entry.symbol && (
            <span className="font-mono text-xs text-foreground/80 font-semibold shrink-0">{entry.symbol}</span>
          )}
          {entry.broker_id && (
            <span className="font-mono text-[10px] text-muted-foreground/70 bg-secondary/60 px-1.5 py-0.5 rounded shrink-0">
              {entry.broker_id}
            </span>
          )}
          {entry.error_message && (
            <span className="text-[10px] text-red-400/80 truncate min-w-0">{entry.error_message}</span>
          )}
        </span>

        {/* Success indicator */}
        <span className="shrink-0">
          {entry.success
            ? <CheckCircle size={12} className="text-emerald-400/70" />
            : <XCircle    size={12} className="text-red-400/80" />
          }
        </span>

        {/* Expand chevron */}
        <span className="shrink-0 text-muted-foreground/40">
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </span>
      </button>

      {/* Expanded details */}
      {expanded && entry.details && Object.keys(entry.details).length > 0 && (
        <div className="px-3 pb-2.5 pt-0">
          <pre className="ml-32 text-[10px] font-mono text-muted-foreground/80 bg-secondary/30 rounded-lg px-3 py-2 overflow-x-auto whitespace-pre-wrap border border-border/40">
            {JSON.stringify(entry.details, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit log viewer (main section)
// ---------------------------------------------------------------------------

const CATEGORIES: { id: Category; label: string }[] = [
  { id: 'all',     label: 'All'     },
  { id: 'trading', label: 'Trading' },
  { id: 'broker',  label: 'Broker'  },
  { id: 'config',  label: 'Config'  },
  { id: 'engine',  label: 'Engine'  },
  { id: 'system',  label: 'System'  },
];

function AuditLogViewer() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [category, setCategory] = useState<Category>('all');
  const [symbolFilter, setSymbolFilter] = useState('');
  const [brokerFilter, setBrokerFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'ok' | 'fail'>('all');
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const PAGE = 100;

  const buildParams = useCallback((pageSkip = 0) => {
    const p = new URLSearchParams({ limit: String(PAGE), skip: String(pageSkip) });
    if (category !== 'all') {
      // Send each event type in the category as separate params
      for (const et of CATEGORY_EVENTS[category]) p.append('event_type', et);
    }
    if (symbolFilter.trim()) p.set('symbol', symbolFilter.trim().toUpperCase());
    if (brokerFilter.trim()) p.set('broker_id', brokerFilter.trim().toLowerCase());
    if (statusFilter === 'ok')   p.set('success', 'true');
    if (statusFilter === 'fail') p.set('success', 'false');
    return p.toString();
  }, [category, symbolFilter, brokerFilter, statusFilter]);

  const fetch = useCallback(async (pageSkip = 0, append = false) => {
    setLoading(true);
    try {
      const params = buildParams(pageSkip);
      // For category filtering we send multiple event_type params —
      // backend /api/audit-logs supports a single event_type param,
      // so for category we pass the first event type as a filter grouping.
      // We'll do client-side filtering for category since the backend
      // supports one event_type at a time.
      let url = `/api/audit-logs?limit=${PAGE}&skip=${pageSkip}`;
      if (symbolFilter.trim()) url += `&symbol=${encodeURIComponent(symbolFilter.trim().toUpperCase())}`;
      if (brokerFilter.trim()) url += `&broker_id=${encodeURIComponent(brokerFilter.trim().toLowerCase())}`;
      if (statusFilter === 'ok')   url += '&success=true';
      if (statusFilter === 'fail') url += '&success=false';

      const data = await apiFetch(url);
      let rows: AuditEntry[] = data.logs ?? [];

      // Client-side category filter (backend supports single event_type only)
      if (category !== 'all') {
        const allowed = new Set(CATEGORY_EVENTS[category]);
        rows = rows.filter((e) => allowed.has(e.event_type));
      }

      setHasMore(data.logs?.length === PAGE);
      setEntries(append ? (prev) => [...prev, ...rows] : rows);
      setSkip(pageSkip);
    } catch {
      if (!append) setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [buildParams, category, symbolFilter, brokerFilter, statusFilter]);

  // Reset to page 0 when filters change
  useEffect(() => {
    fetch(0, false);
  }, [category, statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-refresh interval
  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(() => fetch(0, false), 8000);
    return () => clearInterval(t);
  }, [autoRefresh, fetch]);

  const failCount = entries.filter((e) => !e.success).length;

  return (
    <div className="space-y-3" data-testid="audit-log-section">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-primary" />
          <span className="text-sm font-semibold text-foreground">Audit Log</span>
          {entries.length > 0 && (
            <span className="font-mono text-[10px] text-muted-foreground/60">
              {entries.length} event{entries.length !== 1 ? 's' : ''}
              {failCount > 0 && (
                <span className="ml-1.5 text-red-400">{failCount} failed</span>
              )}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Auto-refresh toggle */}
          <button
            data-testid="audit-auto-refresh-toggle"
            onClick={() => setAutoRefresh((a) => !a)}
            className={`text-[10px] font-semibold px-2 py-1 rounded-full border transition-all ${
              autoRefresh
                ? 'bg-primary/20 text-primary border-primary/40'
                : 'text-muted-foreground border-border hover:border-primary/30'
            }`}
          >
            Auto
          </button>
          <button
            data-testid="refresh-audit-logs-btn"
            onClick={() => fetch(0, false)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Category pills */}
        <div className="flex items-center gap-1">
          {CATEGORIES.map(({ id, label }) => (
            <button
              key={id}
              data-testid={`audit-category-${id}`}
              onClick={() => setCategory(id)}
              className={`text-[10px] font-semibold px-2.5 py-1 rounded-full border transition-all ${
                category === id
                  ? 'bg-primary/20 text-primary border-primary/40'
                  : 'text-muted-foreground border-border hover:border-primary/30 hover:text-foreground'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Divider */}
        <div className="h-4 w-px bg-border" />

        {/* Symbol search */}
        <div className="relative">
          <Search size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground/50" />
          <input
            data-testid="audit-symbol-filter"
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetch(0, false)}
            placeholder="Symbol"
            className="pl-6 pr-2 py-1 h-6 text-[10px] font-mono bg-secondary border border-border rounded-lg w-24 text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>

        {/* Broker search */}
        <div className="relative">
          <Search size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground/50" />
          <input
            data-testid="audit-broker-filter"
            value={brokerFilter}
            onChange={(e) => setBrokerFilter(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetch(0, false)}
            placeholder="Broker"
            className="pl-6 pr-2 py-1 h-6 text-[10px] font-mono bg-secondary border border-border rounded-lg w-24 text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
        </div>

        {/* Status filter */}
        <div className="flex items-center gap-0.5 bg-secondary/60 border border-border rounded-full p-0.5">
          {(['all', 'ok', 'fail'] as const).map((s) => (
            <button
              key={s}
              data-testid={`audit-status-${s}`}
              onClick={() => setStatusFilter(s)}
              className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded-full transition-all ${
                statusFilter === s
                  ? s === 'fail'
                    ? 'bg-red-500/20 text-red-400'
                    : s === 'ok'
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : 'bg-primary/20 text-primary'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Apply search button (for symbol/broker) */}
        {(symbolFilter || brokerFilter) && (
          <button
            onClick={() => fetch(0, false)}
            className="text-[10px] font-semibold px-2 py-1 rounded-full border bg-primary/20 text-primary border-primary/40"
          >
            Apply
          </button>
        )}
        {(symbolFilter || brokerFilter) && (
          <button
            onClick={() => { setSymbolFilter(''); setBrokerFilter(''); }}
            className="text-muted-foreground hover:text-foreground transition-colors"
            title="Clear filters"
          >
            <X size={12} />
          </button>
        )}
      </div>

      {/* Log rows */}
      <div className="glass rounded-xl border border-border overflow-hidden" data-testid="audit-log-table">
        <div className="max-h-[520px] overflow-auto divide-y divide-border/0">
          {entries.length > 0 ? (
            entries.map((entry, i) => (
              <AuditRow key={`${entry.timestamp}-${i}`} entry={entry} />
            ))
          ) : (
            <div className="flex flex-col items-center justify-center h-32 text-muted-foreground">
              {loading
                ? <RefreshCw size={16} className="animate-spin" />
                : <>
                    <p className="text-sm">No audit events yet</p>
                    <p className="text-[10px] mt-1 text-muted-foreground/50">
                      Events are logged as the bot runs
                    </p>
                  </>
              }
            </div>
          )}
        </div>

        {/* Load more */}
        {hasMore && (
          <div className="border-t border-border px-4 py-2 flex justify-center">
            <button
              data-testid="audit-load-more-btn"
              onClick={() => fetch(skip + PAGE, true)}
              disabled={loading}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5"
            >
              {loading ? <RefreshCw size={11} className="animate-spin" /> : <ChevronDown size={11} />}
              Load more
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loss log file viewer (secondary, collapsible)
// ---------------------------------------------------------------------------

type LossLogDate = { date: string; count: number; files: string[] };

function LossLogViewer() {
  const [open, setOpen] = useState(false);
  const [dates, setDates] = useState<LossLogDate[]>([]);
  const [expandedDate, setExpandedDate] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<{ date: string; file: string; content: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchDates = () => {
    setLoading(true);
    apiFetch('/api/loss-logs')
      .then((data) => setDates(data.dates ?? []))
      .catch(() => setDates([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (open) fetchDates();
  }, [open]);

  const viewFile = (date: string, file: string) => {
    apiFetch(`/api/loss-logs/${date}/${file}`, { rawText: true })
      .then((content) => setViewingFile({ date, file, content }))
      .catch(() => setViewingFile({ date, file, content: 'Failed to load file.' }));
  };

  const totalLosses = dates.reduce((s, d) => s + d.count, 0);

  return (
    <div className="glass rounded-xl border border-border overflow-hidden" data-testid="loss-logs-section">
      {/* Collapsible header */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-secondary/20 transition-colors"
        data-testid="loss-logs-toggle"
      >
        <div className="flex items-center gap-2">
          <AlertTriangle size={13} className="text-amber-400" />
          <span className="text-sm font-semibold text-foreground">Loss Trade Files</span>
          {totalLosses > 0 && open && (
            <span className="text-[10px] bg-red-500/15 text-red-400 px-2 py-0.5 rounded-full font-mono">
              {totalLosses} file{totalLosses !== 1 ? 's' : ''}
            </span>
          )}
          <span className="text-[10px] text-muted-foreground/50">— per-trade .txt loss reports</span>
        </div>
        <div className="flex items-center gap-2">
          {open && (
            <button
              onClick={(e) => { e.stopPropagation(); fetchDates(); }}
              className="text-muted-foreground hover:text-foreground transition-colors"
              data-testid="refresh-loss-logs-btn"
            >
              <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            </button>
          )}
          {open ? <ChevronUp size={14} className="text-muted-foreground" /> : <ChevronDown size={14} className="text-muted-foreground" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-border px-4 pb-4 pt-3 space-y-2">
          {dates.length === 0 && !loading && (
            <p className="text-xs text-muted-foreground/60 text-center py-4">No loss log files yet</p>
          )}

          {dates.map((d) => (
            <div key={d.date} className="rounded-lg border border-border overflow-hidden bg-background/30">
              <button
                onClick={() => setExpandedDate(expandedDate === d.date ? null : d.date)}
                className="w-full flex items-center justify-between px-3 py-2 hover:bg-secondary/30 transition-colors"
                data-testid={`loss-log-date-${d.date}`}
              >
                <div className="flex items-center gap-2">
                  <FolderOpen size={12} className="text-amber-400" />
                  <span className="font-mono text-xs text-foreground">{d.date}</span>
                  <span className="text-[9px] bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded-full font-mono">
                    {d.count} loss{d.count !== 1 ? 'es' : ''}
                  </span>
                </div>
                {expandedDate === d.date ? <ChevronUp size={12} className="text-muted-foreground" /> : <ChevronDown size={12} className="text-muted-foreground" />}
              </button>
              {expandedDate === d.date && (
                <div className="border-t border-border/50 px-3 py-1.5 space-y-0.5 bg-background/50">
                  {d.files.map((file) => (
                    <button
                      key={file}
                      onClick={() => viewFile(d.date, file)}
                      className="w-full flex items-center gap-2 px-2 py-1 rounded hover:bg-secondary/50 transition-colors text-left"
                      data-testid={`loss-log-file-${file}`}
                    >
                      <FileText size={10} className="text-red-400 shrink-0" />
                      <span className="font-mono text-[10px] text-foreground truncate">{file}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}

          {viewingFile && (
            <div className="rounded-xl border border-red-500/30 overflow-hidden" data-testid="loss-log-viewer">
              <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-red-500/5">
                <span className="font-mono text-[10px] text-foreground">{viewingFile.date}/{viewingFile.file}</span>
                <button onClick={() => setViewingFile(null)} className="text-muted-foreground hover:text-foreground" data-testid="close-loss-log-viewer">
                  <X size={12} />
                </button>
              </div>
              <pre className="p-3 font-mono text-[10px] text-foreground/90 whitespace-pre-wrap overflow-auto max-h-72">
                {viewingFile.content}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab root
// ---------------------------------------------------------------------------

export function LogsTab() {
  return (
    <div className="space-y-6" data-testid="logs-tab">
      <AuditLogViewer />
      <LossLogViewer />
    </div>
  );
}
