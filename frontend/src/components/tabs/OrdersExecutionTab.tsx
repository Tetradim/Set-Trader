// Orders & Execution Dashboard Tab.
// 
// Displays order state machine, fill timeline, reject reasons, slippage analysis.
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { List, Clock, CheckCircle, XCircle, AlertCircle, RefreshCw, TrendingUp, TrendingDown } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface Order {
  order_id: string;
  symbol: string;
  side: 'buy' | 'sell';
  order_type: string;
  quantity: number;
  price: number;
  status: 'pending' | 'filled' | 'partial' | 'rejected' | 'cancelled';
  filled_quantity: number;
  avg_fill_price: number;
  created_at: string;
  updated_at: string;
  reject_reason?: string;
  broker?: string;
  external_id?: string;
  execution_lag_ms?: number;
}

interface ExecutionStats {
  total_orders: number;
  filled_orders: number;
  rejected_orders: number;
  pending_orders: number;
  avg_slippage: number;
  avg_execution_lag_ms: number;
  fill_rate: number;
}

const STATUS_CONFIG = {
  pending: { color: 'bg-yellow-500', icon: Clock },
  filled: { color: 'bg-green-500', icon: CheckCircle },
  partial: { color: 'bg-blue-500', icon: List },
  rejected: { color: 'bg-red-500', icon: XCircle },
  cancelled: { color: 'bg-gray-500', icon: AlertCircle }
};

export function OrdersExecutionTab() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [stats, setStats] = useState<ExecutionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('all');
  const [sortBy, setSortBy] = useState<'created_at' | 'symbol'>('created_at');

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const [ordersRes, statsRes] = await Promise.all([
        apiFetch('/api/orders?limit=100'),
        apiFetch('/api/orders/stats')
      ]);
      setOrders(ordersRes.orders || []);
      setStats(statsRes);
    } catch (err) {
      console.error('Failed to fetch orders:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
    const interval = setInterval(fetchOrders, 15000);
    return () => clearInterval(interval);
  }, []);

  const filteredOrders = orders.filter(order => {
    if (filter === 'all') return true;
    return order.status === filter;
  }).sort((a, b) => {
    if (sortBy === 'symbol') return a.symbol.localeCompare(b.symbol);
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  const formatTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit' 
    });
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value);
  };

  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2
    }).format(value);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <List className="h-8 w-8 text-blue-500" />
          <div>
            <h2 className="text-2xl font-bold">Orders & Execution</h2>
            <p className="text-muted-foreground">Order state machine and execution quality</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchOrders}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Execution Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{stats.total_orders}</div>
              <div className="text-sm text-muted-foreground">Total Orders</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-green-500">{stats.filled_orders}</div>
              <div className="text-sm text-muted-foreground">Filled</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-red-500">{stats.rejected_orders}</div>
              <div className="text-sm text-muted-foreground">Rejected</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-yellow-500">{stats.pending_orders}</div>
              <div className="text-sm text-muted-foreground">Pending</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{formatNumber(stats.avg_slippage)}</div>
              <div className="text-sm text-muted-foreground">Avg Slippage (bps)</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{stats.avg_execution_lag_ms}ms</div>
              <div className="text-sm text-muted-foreground">Avg Latency</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Status:</span>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm"
          >
            <option value="all">All</option>
            <option value="pending">Pending</option>
            <option value="filled">Filled</option>
            <option value="partial">Partial</option>
            <option value="rejected">Rejected</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Sort:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm"
          >
            <option value="created_at">Time</option>
            <option value="symbol">Symbol</option>
          </select>
        </div>
      </div>

      {/* Orders Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left text-sm font-medium">Time</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Symbol</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Side</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">Qty</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">Price</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">Filled</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">Avg Fill</th>
                  <th className="px-4 py-3 text-right text-sm font-medium">Lag</th>
                </tr>
              </thead>
              <tbody>
                {loading && orders.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center">
                      <RefreshCw className="h-6 w-6 animate-spin mx-auto text-muted-foreground" />
                    </td>
                  </tr>
                ) : filteredOrders.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-muted-foreground">
                      No orders found
                    </td>
                  </tr>
                ) : (
                  filteredOrders.map((order) => {
                    const StatusIcon = STATUS_CONFIG[order.status as keyof typeof STATUS_CONFIG]?.icon || Clock;
                    const statusConfig = STATUS_CONFIG[order.status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.pending;
                    
                    return (
                      <tr key={order.order_id} className="border-b hover:bg-muted/30">
                        <td className="px-4 py-3 text-sm">{formatTime(order.created_at)}</td>
                        <td className="px-4 py-3 font-medium">{order.symbol}</td>
                        <td className="px-4 py-3">
                          <Badge variant={order.side === 'buy' ? 'default' : 'destructive'}>
                            {order.side.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-right">{order.quantity.toLocaleString()}</td>
                        <td className="px-4 py-3 text-right">{formatCurrency(order.price)}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <StatusIcon className={`h-4 w-4 ${statusConfig.color.replace('bg-', 'text-')}`} />
                            <span className="capitalize">{order.status}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right">
                          {order.filled_quantity.toLocaleString()}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {order.avg_fill_price > 0 ? formatCurrency(order.avg_fill_price) : '-'}
                        </td>
                        <td className="px-4 py-3 text-right text-muted-foreground">
                          {order.execution_lag_ms ? `${order.execution_lag_ms}ms` : '-'}
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

      {/* Rejected Orders Details */}
      {orders.some(o => o.status === 'rejected' && o.reject_reason) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-red-500" />
              Rejection Reasons
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {orders
                .filter(o => o.status === 'rejected' && o.reject_reason)
                .slice(0, 5)
                .map((order) => (
                  <div
                    key={order.order_id}
                    className="flex items-center justify-between p-3 bg-red-500/10 rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      <XCircle className="h-4 w-4 text-red-500" />
                      <span className="font-medium">{order.symbol}</span>
                      <Badge variant="outline">Order: {order.order_id.slice(-8)}</Badge>
                    </div>
                    <span className="text-sm text-red-400">{order.reject_reason}</span>
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}