"""Portfolio Analytics Dashboard Tab.

Displays PnL attribution, drawdown, Sharpe-like metrics, and performance analytics.
"""
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { TrendingUp, TrendingDown, DollarSign, BarChart3, Activity, RefreshCw, PieChart } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

interface PortfolioMetrics {
  total_value: number;
  total_pnl: number;
  daily_pnl: number;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  turnover: number;
  trade_count: number;
}

interface AttributionData {
  strategy: string;
  pnl: number;
  allocation: number;
}

interface RegimeData {
  regime: string;
  count: number;
  win_rate: number;
}

export function PortfolioAnalyticsTab() {
  const [metrics, setMetrics] = useState<PortfolioMetrics | null>(null);
  const [attribution, setAttribution] = useState<AttributionData[]>([]);
  const [regimes, setRegimes] = useState<RegimeData[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeframe, setTimeframe] = useState<string>('1d');

  const fetchPortfolioData = async () => {
    setLoading(true);
    try {
      const [metricsRes, attrRes, regimeRes] = await Promise.all([
        apiFetch(`/api/analytics/portfolio?timeframe=${timeframe}`),
        apiFetch('/api/analytics/attribution'),
        apiFetch('/api/analytics/regimes')
      ]);
      setMetrics(metricsRes);
      setAttribution(attrRes.attribution || []);
      setRegimes(regimeRes.regimes || []);
    } catch (err) {
      console.error('Failed to fetch portfolio data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPortfolioData();
  }, [timeframe]);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  if (loading && !metrics) {
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
          <BarChart3 className="h-8 w-8 text-emerald-500" />
          <div>
            <h2 className="text-2xl font-bold">Portfolio Analytics</h2>
            <p className="text-muted-foreground">PnL attribution and performance metrics</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm"
          >
            <option value="1d">Today</option>
            <option value="1w">This Week</option>
            <option value="1m">This Month</option>
            <option value="1y">This Year</option>
            <option value="all">All Time</option>
          </select>
          <Button variant="outline" size="sm" onClick={fetchPortfolioData}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Total Value</div>
            <div className="text-2xl font-bold">{formatCurrency(metrics?.total_value || 0)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Total P&L</div>
            <div className={`text-2xl font-bold ${(metrics?.total_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {formatCurrency(metrics?.total_pnl || 0)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Daily P&L</div>
            <div className={`text-2xl font-bold ${(metrics?.daily_pnl || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {formatCurrency(metrics?.daily_pnl || 0)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Return</div>
            <div className={`text-2xl font-bold ${(metrics?.total_return || 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {formatPercent(metrics?.total_return || 0)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Sharpe Ratio</div>
            <div className="text-2xl font-bold">{(metrics?.sharpe_ratio || 0).toFixed(2)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Max Drawdown</div>
            <div className="text-2xl font-bold text-red-500">
              -{Math.abs(metrics?.max_drawdown || 0).toFixed(1)}%
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Trading Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Win Rate</div>
            <div className="text-2xl font-bold text-green-500">
              {((metrics?.win_rate || 0) * 100).toFixed(1)}%
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Avg Win</div>
            <div className="text-2xl font-bold text-green-500">
              {formatCurrency(metrics?.avg_win || 0)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Avg Loss</div>
            <div className="text-2xl font-bold text-red-500">
              {formatCurrency(metrics?.avg_loss || 0)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <div className="text-sm text-muted-foreground">Turnover</div>
            <div className="text-2xl font-bold">
              {((metrics?.turnover || 0) * 100).toFixed(1)}%
            </div>
          </CardContent>
        </Card>
      </div>

      {/* P&L Attribution */}
      {attribution.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <PieChart className="h-5 w-5" />
              P&L Attribution
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {attribution.map((attr) => (
                <div key={attr.strategy} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{attr.strategy}</span>
                    <span className={attr.pnl >= 0 ? 'text-green-500' : 'text-red-500'}>
                      {formatCurrency(attr.pnl)}
                    </span>
                  </div>
                  <div className="h-2 bg-secondary rounded-full overflow-hidden">
                    <div
                      className={`h-full ${attr.pnl >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                      style={{ width: `${Math.min(Math.abs(attr.pnl) / (metrics?.total_value || 1) * 100, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Regime Analysis */}
      {regimes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Regime Analysis
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {regimes.map((regime) => (
                <div key={regime.regime} className="p-4 border rounded-lg text-center">
                  <div className="text-lg font-bold capitalize">{regime.regime}</div>
                  <div className="text-2xl font-bold text-green-500">
                    {(regime.win_rate * 100).toFixed(0)}%
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {regime.count} trades
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}