"""Reconciliation Dashboard Tab.

Displays internal ledger vs broker statements, break detection, and EOD sign-off.
"""
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { Scale, AlertTriangle, CheckCircle, RefreshCw, FileText, Clock, ArrowRightLeft } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface ReconciliationRecord {
  record_id: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
  broker: string;
  internal_timestamp: string;
  broker_timestamp: string;
  status: 'matched' | 'break' | 'pending';
  break_reason?: string;
  pnl?: number;
}

interface ReconciliationSummary {
  total_records: number;
  matched: number;
  breaks: number;
  pending: number;
  total_pnl: number;
  last_sync: string;
}

const STATUS_CONFIG = {
  matched: { color: 'text-green-500', bg: 'bg-green-500/10', icon: CheckCircle },
  break: { color: 'text-red-500', bg: 'bg-red-500/10', icon: AlertTriangle },
  pending: { color: 'text-yellow-500', bg: 'bg-yellow-500/10', icon: Clock }
};

export function ReconciliationTab() {
  const [records, setRecords] = useState<ReconciliationRecord[]>([]);
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('all');
  const [signingOff, setSigningOff] = useState(false);

  const fetchReconciliation = async () => {
    setLoading(true);
    try {
      const [recsRes, sumRes] = await Promise.all([
        apiFetch('/api/reconciliation/records?limit=100'),
        apiFetch('/api/reconciliation/summary')
      ]);
      setRecords(recsRes.records || []);
      setSummary(sumRes);
    } catch (err) {
      console.error('Failed to fetch reconciliation:', err);
/**
 * Reconciliation Dashboard Tab.
 *
 * Displays internal ledger vs broker statements, break detection, and EOD sign-off.
 */
import { useState, useEffect } from 'react';

interface ReconciliationRecord {
  symbol: string;
  internalQty: number;
  brokerQty: number;
  drift: number;
  lastChecked: string;
}

export default function ReconciliationTab() {
  const [records, setRecords] = useState<ReconciliationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchReconciliation();
  }, []);

  const fetchReconciliation = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/reconciliation');
      if (!response.ok) throw new Error('Failed to fetch reconciliation data');
      const data = await response.json();
      setRecords(data.records || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReconciliation();
    const interval = setInterval(fetchReconciliation, 60000); // Refresh every minute
    return () => clearInterval(interval);
  }, []);

  const handleEodSignoff = async () => {
    setSigningOff(true);
    try {
      await apiFetch('/api/reconciliation/signoff', {
        method: 'POST',
        body: JSON.stringify({ timestamp: new Date().toISOString() })
      });
      await fetchReconciliation();
    } catch (err) {
      console.error('Failed to sign off:', err);
    } finally {
      setSigningOff(false);
    }
  };

  const filteredRecords = records.filter(record => {
    if (filter === 'all') return true;
    return record.status === filter;
  });

  const formatTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(value);
  };

  const getTimeDiff = (t1: string, t2: string) => {
    const diff = Math.abs(new Date(t1).getTime() - new Date(t2).getTime());
    return `${(diff / 1000).toFixed(1)}s`;
  };

  if (loading && records.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Scale className="h-8 w-8 text-purple-500" />
          <div>
            <h2 className="text-2xl font-bold">Reconciliation</h2>
            <p className="text-muted-foreground">Internal ledger vs broker statements</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchReconciliation}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button 
            variant="default" 
            size="sm" 
            onClick={handleEodSignoff}
            disabled={signingOff || (summary?.breaks || 0) > 0}
          >
            <CheckCircle className="h-4 w-4 mr-2" />
            EOD Sign-off
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{summary.total_records}</div>
              <div className="text-sm text-muted-foreground">Total Records</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-green-500">{summary.matched}</div>
              <div className="text-sm text-muted-foreground">Matched</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-red-500">{summary.breaks}</div>
              <div className="text-sm text-muted-foreground">Breaks</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-yellow-500">{summary.pending}</div>
              <div className="text-sm text-muted-foreground">Pending</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className={`text-2xl font-bold ${summary.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {formatCurrency(summary.total_pnl)}
              </div>
              <div className="text-sm text-muted-foreground">Total P&L</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-sm font-medium">Last Sync</div>
              <div className="text-xs text-muted-foreground">
                {summary.last_sync ? formatTime(summary.last_sync) : 'Never'}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-4">
        <span className="text-sm font-medium">Filter:</span>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm"
        >
          <option value="all">All</option>
          <option value="matched">Matched</option>
          <option value="break">Breaks</option>
          <option value="pending">Pending</option>
        </select>
      </div>

      {/* Records Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Symbol</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Side</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">Qty</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">Price</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Broker</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Internal Time</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Broker Time</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Diff</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">P&L</th>
                </tr>
              </thead>
              <tbody>
                {filteredRecords.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="px-4 py-8 text-center text-muted-foreground">
                      No reconciliation records found
                    </td>
                  </tr>
                ) : (
                  filteredRecords.map((record) => {
                    const statusConfig = STATUS_CONFIG[record.status as keyof typeof STATUS_CONFIG];
                    const StatusIcon = statusConfig?.icon || Clock;
                    
                    return (
                      <tr key={record.record_id} className="border-b hover:bg-muted/30">
                        <td className="px-4 py-3">
                          <div className={`flex items-center gap-2 ${statusConfig?.bg || ''} p-2 rounded`}>
                            <StatusIcon className={`h-4 w-4 ${statusConfig?.color || ''}`} />
                            <span className="capitalize">{record.status}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 font-medium">{record.symbol}</td>
                        <td className="px-4 py-3">
                          <Badge variant={record.side === 'buy' ? 'default' : 'destructive'}>
                            {record.side.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-right">{record.quantity}</td>
                        <td className="px-4 py-3 text-right">{formatCurrency(record.price)}</td>
                        <td className="px-4 py-3 text-muted-foreground">{record.broker}</td>
                        <td className="px-4 py-3 text-sm">{formatTime(record.internal_timestamp)}</td>
                        <td className="px-4 py-3 text-sm">{formatTime(record.broker_timestamp)}</td>
                        <td className="px-4 py-3 text-sm">
                          {getTimeDiff(record.internal_timestamp, record.broker_timestamp)}
                        </td>
                        <td className={`px-4 py-3 text-right ${(record.pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                          {record.pnl !== undefined ? formatCurrency(record.pnl) : '-'}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Breaks Alert */}
      {summary && summary.breaks > 0 && (
        <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
          <AlertTriangle className="h-5 w-5 text-red-500" />
          <div>
            <p className="font-medium text-red-400">
              {summary.breaks} reconciliation {summary.breaks === 1 ? 'break' : 'breaks'} detected
            </p>
            <p className="text-sm text-muted-foreground">
              Review and resolve before EOD sign-off
            </p>
          </div>
        </div>
      )}
  const hasDrift = records.some(r => r.drift !== 0);

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">Reconciliation Dashboard</h2>
        <button
          onClick={fetchReconciliation}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          disabled={loading}
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      {hasDrift && (
        <div className="mb-4 p-3 bg-yellow-100 border border-yellow-400 text-yellow-700 rounded">
          ⚠️ Position drift detected! Internal ledger doesn't match broker statements.
        </div>
      )}

      <table className="min-w-full bg-white border border-gray-300">
        <thead>
          <tr className="bg-gray-100">
            <th className="px-4 py-2 border">Symbol</th>
            <th className="px-4 py-2 border">Internal Qty</th>
            <th className="px-4 py-2 border">Broker Qty</th>
            <th className="px-4 py-2 border">Drift</th>
            <th className="px-4 py-2 border">Last Checked</th>
          </tr>
        </thead>
        <tbody>
          {records.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-4 py-2 text-center text-gray-500">
                No reconciliation data available
              </td>
            </tr>
          ) : (
            records.map((record, idx) => (
              <tr key={idx} className={record.drift !== 0 ? 'bg-red-50' : ''}>
                <td className="px-4 py-2 border">{record.symbol}</td>
                <td className="px-4 py-2 border text-right">{record.internalQty}</td>
                <td className="px-4 py-2 border text-right">{record.brokerQty}</td>
                <td className={`px-4 py-2 border text-right font-bold ${record.drift !== 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {record.drift}
                </td>
                <td className="px-4 py-2 border">{record.lastChecked}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}