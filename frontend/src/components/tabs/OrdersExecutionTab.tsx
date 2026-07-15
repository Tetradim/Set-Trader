// Orders & Execution Dashboard Tab.
// Displays broker child orders, parent strategy orders, and completed cycle capital.
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { uiLog } from '@/lib/clientLogger';
import { List, Clock, CheckCircle, XCircle, AlertCircle, RefreshCw, Link2, Repeat2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface Order {
  order_id: string;
  durable_order_id?: string;
  parent_order_id?: string;
  symbol: string;
  side: string;
  order_type: string;
  quantity: number;
  requested_quantity?: number;
  price: number;
  status: string;
  filled_quantity: number;
  remaining_quantity?: number;
  applied_quantity?: number;
  unapplied_quantity?: number;
  avg_fill_price: number;
  created_at: string;
  updated_at: string;
  reject_reason?: string;
  error?: string;
  broker?: string;
  account_id?: string;
  external_id?: string;
  execution_lag_ms?: number;
  valid_until_epoch?: number | null;
  cancel_requested_at?: string | null;
  reconciliation_required?: boolean;
}

interface ParentOrder {
  parent_order_id: string;
  symbol: string;
  side: string;
  order_type: string;
  policy: string;
  target_quantity: number;
  filled_quantity: number;
  remaining_quantity: number;
  state: string;
  child_order_ids: string[];
  valid_until_epoch?: number | null;
  updated_at?: string;
}

interface StrategyCycle {
  symbol?: string;
  cycle_number?: number;
  gross_pnl?: number;
  fees?: number;
  net_pnl?: number;
  prior_cycle_capital?: number;
  cycle_capital?: number;
  state?: string;
  completed_at?: string;
}

interface ExecutionStats {
  total_orders: number;
  filled_orders: number;
  rejected_orders: number;
  pending_orders: number;
  reconciliation_required?: number;
  working_parent_orders?: number;
  partial_parent_orders?: number;
  avg_slippage: number;
  avg_execution_lag_ms: number;
  fill_rate: number;
}

interface LiveLedgerResponse {
  orders: Order[];
  parent_orders: ParentOrder[];
  strategy_cycles: StrategyCycle[];
  stats: ExecutionStats;
  source: string;
  generated_at: string;
}

const STATUS_CONFIG: Record<string, { color: string; icon: typeof Clock }> = {
  pending: { color: 'bg-yellow-500', icon: Clock },
  submitted: { color: 'bg-yellow-500', icon: Clock },
  working: { color: 'bg-yellow-500', icon: Clock },
  working_unconfirmed: { color: 'bg-orange-500', icon: AlertCircle },
  filled: { color: 'bg-green-500', icon: CheckCircle },
  partial: { color: 'bg-blue-500', icon: List },
  partially_filled: { color: 'bg-blue-500', icon: List },
  rejected: { color: 'bg-red-500', icon: XCircle },
  error: { color: 'bg-red-500', icon: XCircle },
  failed: { color: 'bg-red-500', icon: XCircle },
  canceled: { color: 'bg-gray-500', icon: AlertCircle },
  cancelled: { color: 'bg-gray-500', icon: AlertCircle },
  expired: { color: 'bg-gray-500', icon: AlertCircle },
};

function statusLabel(status: string) {
  return String(status || 'unknown').replaceAll('_', ' ');
}

function formatTime(dateStr?: string) {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}

function formatExpiry(epoch?: number | null) {
  if (!epoch) return '-';
  const remaining = epoch * 1000 - Date.now();
  if (remaining <= 0) return 'Expired';
  if (remaining < 60_000) return `${Math.ceil(remaining / 1000)}s`;
  return `${Math.ceil(remaining / 60_000)}m`;
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', minimumFractionDigits: 2
  }).format(Number(value || 0));
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0, maximumFractionDigits: 8
  }).format(Number(value || 0));
}

export function OrdersExecutionTab() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [parents, setParents] = useState<ParentOrder[]>([]);
  const [cycles, setCycles] = useState<StrategyCycle[]>([]);
  const [stats, setStats] = useState<ExecutionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'created_at' | 'symbol'>('created_at');

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const response = await apiFetch('/api/orders/live?limit=250') as LiveLedgerResponse;
      setOrders(Array.isArray(response?.orders) ? response.orders : []);
      setParents(Array.isArray(response?.parent_orders) ? response.parent_orders : []);
      setCycles(Array.isArray(response?.strategy_cycles) ? response.strategy_cycles : []);
      setStats(response?.stats || null);
      setError('');
    } catch (err: any) {
      uiLog.error('orders.fetch_failed', err);
      setError(err?.message || 'Live order ledger could not be loaded.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
    const interval = setInterval(fetchOrders, 10_000);
    return () => clearInterval(interval);
  }, []);

  const filteredOrders = orders.filter((order) => {
    if (filter === 'all') return true;
    if (filter === 'reconciliation') return Boolean(order.reconciliation_required);
    return order.status === filter;
  }).sort((a, b) => {
    if (sortBy === 'symbol') return a.symbol.localeCompare(b.symbol);
    return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <List className="h-8 w-8 text-blue-500" />
          <div>
            <h2 className="text-2xl font-bold">Orders & Execution</h2>
            <p className="text-muted-foreground">Broker child orders, strategy parents, fills, expiry, and cycle capital</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchOrders}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-300">
          <AlertCircle className="h-5 w-5" />
          <span>{error}</span>
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
          {[
            ['Total', stats.total_orders, ''],
            ['Filled', stats.filled_orders, 'text-green-500'],
            ['Rejected', stats.rejected_orders, 'text-red-500'],
            ['Working', stats.pending_orders, 'text-yellow-500'],
            ['Reconcile', stats.reconciliation_required || 0, 'text-orange-500'],
            ['Parents', stats.working_parent_orders || 0, 'text-blue-500'],
            ['Fill Rate', `${stats.fill_rate || 0}%`, ''],
          ].map(([label, value, color]) => (
            <Card key={String(label)}>
              <CardContent className="pt-4">
                <div className={`text-2xl font-bold ${color}`}>{value}</div>
                <div className="text-sm text-muted-foreground">{label}</div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2"><Link2 className="h-5 w-5" />Parent Strategy Orders</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left text-sm">Symbol</th>
                <th className="px-4 py-3 text-left text-sm">Side</th>
                <th className="px-4 py-3 text-left text-sm">State</th>
                <th className="px-4 py-3 text-left text-sm">Policy</th>
                <th className="px-4 py-3 text-right text-sm">Target</th>
                <th className="px-4 py-3 text-right text-sm">Filled</th>
                <th className="px-4 py-3 text-right text-sm">Remaining</th>
                <th className="px-4 py-3 text-right text-sm">Children</th>
                <th className="px-4 py-3 text-right text-sm">TTL</th>
              </tr></thead>
              <tbody>
                {parents.length === 0 ? <tr><td colSpan={9} className="px-4 py-6 text-center text-muted-foreground">No parent orders recorded</td></tr> : parents.map((parent) => (
                  <tr key={parent.parent_order_id} className="border-b hover:bg-muted/30">
                    <td className="px-4 py-3 font-medium">{parent.symbol}</td>
                    <td className="px-4 py-3">{parent.side}</td>
                    <td className="px-4 py-3"><Badge variant="outline">{statusLabel(parent.state)}</Badge></td>
                    <td className="px-4 py-3">{parent.policy || '-'}</td>
                    <td className="px-4 py-3 text-right">{formatNumber(parent.target_quantity)}</td>
                    <td className="px-4 py-3 text-right">{formatNumber(parent.filled_quantity)}</td>
                    <td className="px-4 py-3 text-right">{formatNumber(parent.remaining_quantity)}</td>
                    <td className="px-4 py-3 text-right">{parent.child_order_ids?.length || 0}</td>
                    <td className="px-4 py-3 text-right">{formatExpiry(parent.valid_until_epoch)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Status:</span>
          <select value={filter} onChange={(e) => setFilter(e.target.value)} className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm">
            <option value="all">All</option>
            <option value="submitted">Submitted</option>
            <option value="working">Working</option>
            <option value="partially_filled">Partial</option>
            <option value="filled">Filled</option>
            <option value="rejected">Rejected</option>
            <option value="canceled">Canceled</option>
            <option value="reconciliation">Needs reconciliation</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Sort:</span>
          <select value={sortBy} onChange={(e) => setSortBy(e.target.value as 'created_at' | 'symbol')} className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm">
            <option value="created_at">Time</option>
            <option value="symbol">Symbol</option>
          </select>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-lg">Broker Child Orders</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr className="border-b bg-muted/50">
                <th className="px-4 py-3 text-left text-sm">Time</th>
                <th className="px-4 py-3 text-left text-sm">Symbol</th>
                <th className="px-4 py-3 text-left text-sm">Broker</th>
                <th className="px-4 py-3 text-left text-sm">Side</th>
                <th className="px-4 py-3 text-left text-sm">Status</th>
                <th className="px-4 py-3 text-right text-sm">Requested</th>
                <th className="px-4 py-3 text-right text-sm">Filled</th>
                <th className="px-4 py-3 text-right text-sm">Applied</th>
                <th className="px-4 py-3 text-right text-sm">Avg Fill</th>
                <th className="px-4 py-3 text-right text-sm">TTL</th>
              </tr></thead>
              <tbody>
                {loading && orders.length === 0 ? <tr><td colSpan={10} className="px-4 py-8 text-center"><RefreshCw className="h-6 w-6 animate-spin mx-auto" /></td></tr> : filteredOrders.length === 0 ? <tr><td colSpan={10} className="px-4 py-8 text-center text-muted-foreground">No live broker orders found</td></tr> : filteredOrders.map((order) => {
                  const config = STATUS_CONFIG[order.status] || STATUS_CONFIG.pending;
                  const StatusIcon = config.icon;
                  return (
                    <tr key={`${order.broker}-${order.durable_order_id || order.order_id}`} className={`border-b hover:bg-muted/30 ${order.reconciliation_required ? 'bg-orange-500/5' : ''}`}>
                      <td className="px-4 py-3 text-sm">{formatTime(order.created_at)}</td>
                      <td className="px-4 py-3 font-medium">{order.symbol}</td>
                      <td className="px-4 py-3">{order.broker || '-'}</td>
                      <td className="px-4 py-3"><Badge variant={order.side.toUpperCase() === 'BUY' ? 'default' : 'destructive'}>{order.side.toUpperCase()}</Badge></td>
                      <td className="px-4 py-3"><div className="flex items-center gap-2"><StatusIcon className={`h-4 w-4 ${config.color.replace('bg-', 'text-')}`} /><span className="capitalize">{statusLabel(order.status)}</span>{order.reconciliation_required && <Badge variant="outline" className="text-orange-400">reconcile</Badge>}</div></td>
                      <td className="px-4 py-3 text-right">{formatNumber(order.requested_quantity ?? order.quantity)}</td>
                      <td className="px-4 py-3 text-right">{formatNumber(order.filled_quantity)}</td>
                      <td className="px-4 py-3 text-right">{formatNumber(order.applied_quantity || 0)}</td>
                      <td className="px-4 py-3 text-right">{order.avg_fill_price > 0 ? formatCurrency(order.avg_fill_price) : '-'}</td>
                      <td className="px-4 py-3 text-right">{order.cancel_requested_at ? 'Cancel requested' : formatExpiry(order.valid_until_epoch)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {orders.some((order) => order.reject_reason || order.error) && (
        <Card><CardHeader><CardTitle className="text-lg flex items-center gap-2"><AlertCircle className="h-5 w-5 text-red-500" />Order Errors</CardTitle></CardHeader><CardContent className="space-y-2">
          {orders.filter((order) => order.reject_reason || order.error).slice(0, 10).map((order) => (
            <div key={`error-${order.broker}-${order.order_id}`} className="flex items-center justify-between gap-4 p-3 bg-red-500/10 rounded-lg">
              <span className="font-medium">{order.symbol} · {order.broker || 'broker'} · {order.order_id || order.durable_order_id}</span>
              <span className="text-sm text-red-300">{order.reject_reason || order.error}</span>
            </div>
          ))}
        </CardContent></Card>
      )}

      <Card>
        <CardHeader><CardTitle className="text-lg flex items-center gap-2"><Repeat2 className="h-5 w-5" />Completed Strategy Cycles</CardTitle></CardHeader>
        <CardContent>
          {cycles.length === 0 ? <p className="text-sm text-muted-foreground">No completed cycle-capital records.</p> : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {cycles.slice(0, 12).map((cycle, index) => (
                <div key={`${cycle.symbol}-${cycle.cycle_number}-${index}`} className="rounded-lg border p-3">
                  <div className="flex items-center justify-between"><strong>{cycle.symbol || 'Unknown'}</strong><Badge variant="outline">Cycle {cycle.cycle_number || '-'}</Badge></div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
                    <span className="text-muted-foreground">Gross</span><span className="text-right">{formatCurrency(cycle.gross_pnl || 0)}</span>
                    <span className="text-muted-foreground">Fees</span><span className="text-right">{formatCurrency(cycle.fees || 0)}</span>
                    <span className="text-muted-foreground">Net</span><span className={`text-right ${(cycle.net_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>{formatCurrency(cycle.net_pnl || 0)}</span>
                    <span className="text-muted-foreground">Next capital</span><span className="text-right">{formatCurrency(cycle.cycle_capital || 0)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
