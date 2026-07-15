// Reconciliation Dashboard Tab.
// Displays statement reconciliation, break resolution, and sign-off history.
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { uiLog } from '@/lib/clientLogger';
import { Scale, AlertTriangle, CheckCircle, RefreshCw, Clock, History } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { TabLoadingState } from './TabStates';

interface ReconciliationRecord {
  record_id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  broker: string;
  internal_timestamp: string;
  broker_timestamp: string;
  status: 'matched' | 'break' | 'pending' | 'resolved';
  break_reason?: string;
  pnl?: number;
  resolution?: string;
  resolved_by?: string;
  resolved_at?: string;
}

interface ReconciliationSummary {
  total_records: number;
  matched: number;
  breaks: number;
  pending: number;
  total_pnl: number;
  last_sync: string;
}

interface Signoff {
  signoff_id: string;
  timestamp: string;
  username?: string;
  record_count: number;
  total_pnl: number;
  created_at: string;
}

const STATUS_CONFIG = {
  matched: { color: 'text-green-500', bg: 'bg-green-500/10', icon: CheckCircle },
  resolved: { color: 'text-blue-500', bg: 'bg-blue-500/10', icon: CheckCircle },
  break: { color: 'text-red-500', bg: 'bg-red-500/10', icon: AlertTriangle },
  pending: { color: 'text-yellow-500', bg: 'bg-yellow-500/10', icon: Clock },
};

function asArray<T>(value: unknown, key: string): T[] {
  if (Array.isArray(value)) return value as T[];
  if (value && typeof value === 'object' && Array.isArray((value as Record<string, unknown>)[key])) {
    return (value as Record<string, T[]>)[key];
  }
  return [];
}

function formatTime(dateStr?: string) {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value || 0));
}

export function ReconciliationTab() {
  const [records, setRecords] = useState<ReconciliationRecord[]>([]);
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null);
  const [signoffs, setSignoffs] = useState<Signoff[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<string>('all');
  const [signingOff, setSigningOff] = useState(false);
  const [resolvingId, setResolvingId] = useState('');

  const fetchReconciliation = async () => {
    setLoading(true);
    try {
      const [recordsResponse, summaryResponse, signoffResponse] = await Promise.all([
        apiFetch('/api/reconciliation/records?limit=250'),
        apiFetch('/api/reconciliation/summary'),
        apiFetch('/api/reconciliation/signoffs'),
      ]);
      setRecords(asArray<ReconciliationRecord>(recordsResponse, 'records'));
      setSummary(summaryResponse as ReconciliationSummary);
      setSignoffs(asArray<Signoff>(signoffResponse, 'signoffs'));
      setError('');
    } catch (err: any) {
      uiLog.error('reconciliation.fetch_failed', err);
      setError(err?.message || 'Reconciliation data could not be loaded.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReconciliation();
    const interval = setInterval(fetchReconciliation, 30_000);
    return () => clearInterval(interval);
  }, []);

  const handleEodSignoff = async () => {
    setSigningOff(true);
    try {
      const result = await apiFetch('/api/reconciliation/signoff', {
        method: 'POST',
        body: JSON.stringify({ timestamp: new Date().toISOString() }),
      });
      if (result?.success === false) throw new Error(result.message || 'Sign-off was rejected.');
      await fetchReconciliation();
    } catch (err: any) {
      uiLog.error('reconciliation.signoff_failed', err);
      setError(err?.message || 'End-of-day sign-off failed.');
    } finally {
      setSigningOff(false);
    }
  };

  const resolveBreak = async (record: ReconciliationRecord) => {
    const proposed = window.prompt(
      `Resolution for ${record.record_id} (${record.symbol}):`,
      record.break_reason ? `Reviewed: ${record.break_reason}` : 'Reviewed against broker statement',
    );
    if (!proposed?.trim()) return;
    setResolvingId(record.record_id);
    try {
      await apiFetch(
        `/api/reconciliation/resolve-break/${encodeURIComponent(record.record_id)}?resolution=${encodeURIComponent(proposed.trim())}`,
        { method: 'POST' },
      );
      await fetchReconciliation();
    } catch (err: any) {
      uiLog.error('reconciliation.resolve_failed', err);
      setError(err?.message || 'Break resolution failed.');
    } finally {
      setResolvingId('');
    }
  };

  const filteredRecords = records.filter((record) => filter === 'all' || record.status === filter);

  if (loading && records.length === 0 && !error) {
    return <TabLoadingState title="Loading reconciliation" detail="Fetching broker records, ledger status, and sign-off history." />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Scale className="h-8 w-8 text-purple-500" />
          <div>
            <h2 className="text-2xl font-bold">Reconciliation</h2>
            <p className="text-muted-foreground">Internal records versus broker statements</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchReconciliation}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />Refresh
          </Button>
          <Button size="sm" onClick={handleEodSignoff} disabled={signingOff || (summary?.breaks || 0) > 0}>
            <CheckCircle className="h-4 w-4 mr-2" />EOD Sign-off
          </Button>
        </div>
      </div>

      {error && <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-300">{error}</div>}

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          {[
            ['Total', summary.total_records, ''],
            ['Matched', summary.matched, 'text-green-500'],
            ['Breaks', summary.breaks, 'text-red-500'],
            ['Pending', summary.pending, 'text-yellow-500'],
            ['P&L', formatCurrency(summary.total_pnl), summary.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'],
            ['Last Sync', summary.last_sync ? formatTime(summary.last_sync) : 'Never', 'text-sm'],
          ].map(([label, value, color]) => (
            <Card key={String(label)}><CardContent className="pt-4"><div className={`text-2xl font-bold ${color}`}>{value}</div><div className="text-sm text-muted-foreground">{label}</div></CardContent></Card>
          ))}
        </div>
      )}

      <div className="flex items-center gap-4">
        <span className="text-sm font-medium">Filter:</span>
        <select value={filter} onChange={(e) => setFilter(e.target.value)} className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm">
          <option value="all">All</option><option value="matched">Matched</option><option value="break">Breaks</option><option value="pending">Pending</option><option value="resolved">Resolved</option>
        </select>
      </div>

      <Card><CardContent className="p-0"><div className="overflow-x-auto"><table className="w-full">
        <thead><tr className="border-b bg-muted/50">
          <th className="px-4 py-3 text-left text-sm">Status</th><th className="px-4 py-3 text-left text-sm">Symbol</th><th className="px-4 py-3 text-left text-sm">Side</th><th className="px-4 py-3 text-right text-sm">Qty</th><th className="px-4 py-3 text-right text-sm">Price</th><th className="px-4 py-3 text-left text-sm">Broker</th><th className="px-4 py-3 text-left text-sm">Broker Time</th><th className="px-4 py-3 text-left text-sm">Details</th><th className="px-4 py-3 text-right text-sm">Action</th>
        </tr></thead>
        <tbody>{filteredRecords.length === 0 ? <tr><td colSpan={9} className="px-4 py-8 text-center text-muted-foreground">No reconciliation records found</td></tr> : filteredRecords.map((record) => {
          const config = STATUS_CONFIG[record.status] || STATUS_CONFIG.pending;
          const Icon = config.icon;
          return <tr key={record.record_id} className="border-b hover:bg-muted/30">
            <td className="px-4 py-3"><div className={`flex items-center gap-2 ${config.bg} p-2 rounded`}><Icon className={`h-4 w-4 ${config.color}`} /><span className="capitalize">{record.status}</span></div></td>
            <td className="px-4 py-3 font-medium">{record.symbol}</td>
            <td className="px-4 py-3"><Badge variant={record.side.toUpperCase() === 'BUY' ? 'default' : 'destructive'}>{record.side.toUpperCase()}</Badge></td>
            <td className="px-4 py-3 text-right">{record.quantity}</td><td className="px-4 py-3 text-right">{formatCurrency(record.price)}</td><td className="px-4 py-3">{record.broker}</td><td className="px-4 py-3 text-sm">{formatTime(record.broker_timestamp)}</td>
            <td className="px-4 py-3 text-sm max-w-md">{record.break_reason || record.resolution || '-'}</td>
            <td className="px-4 py-3 text-right">{record.status === 'break' ? <Button size="sm" variant="outline" onClick={() => resolveBreak(record)} disabled={resolvingId === record.record_id}>{resolvingId === record.record_id ? 'Saving…' : 'Resolve'}</Button> : '-'}</td>
          </tr>;
        })}</tbody>
      </table></div></CardContent></Card>

      <Card><CardHeader><CardTitle className="text-lg flex items-center gap-2"><History className="h-5 w-5" />Sign-off History</CardTitle></CardHeader><CardContent>
        {signoffs.length === 0 ? <p className="text-sm text-muted-foreground">No completed sign-offs.</p> : <div className="space-y-2">{signoffs.slice(0, 20).map((signoff) => <div key={signoff.signoff_id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"><div><strong>{signoff.signoff_id}</strong><div className="text-xs text-muted-foreground">{formatTime(signoff.created_at || signoff.timestamp)} · {signoff.username || 'operator'}</div></div><div className="text-right"><div>{signoff.record_count} records</div><div className={signoff.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}>{formatCurrency(signoff.total_pnl)}</div></div></div>)}</div>}
      </CardContent></Card>

      {summary && summary.breaks > 0 && <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-lg"><AlertTriangle className="h-5 w-5 text-red-500" /><div><p className="font-medium text-red-400">{summary.breaks} unresolved reconciliation {summary.breaks === 1 ? 'break' : 'breaks'}</p><p className="text-sm text-muted-foreground">Resolve each break before end-of-day sign-off.</p></div></div>}
    </div>
  );
}
