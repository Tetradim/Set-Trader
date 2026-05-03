import { useState, useEffect, useCallback } from 'react';
import { useStore, PositionData, TradeLog } from '@/stores/useStore';
import { apiFetch } from '@/lib/api';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  LineChart,
  Line,
} from 'recharts';
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Percent,
  Calendar,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
  Filter,
  Download,
  RefreshCw,
  Target,
  Activity,
} from 'lucide-react';
import { toast } from 'sonner';

interface PortfolioStats {
  totalValue: number;
  totalPnl: number;
  totalPnLPct: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  maxDrawdown: number;
  sharpeRatio: number;
}

interface PositionGroup {
  brokerId: string;
  brokerName: string;
  totalValue: number;
  unrealizedPnl: number;
  positions: PositionData[];
}

interface DailyReturn {
  date: string;
  return: number;
}

export function PortfolioTab() {
  const [stats, setStats] = useState<PortfolioStats | null>(null);
  const [positionGroups, setPositionGroups] = useState<PositionGroup[]>([]);
  const [dailyReturns, setDailyReturns] = useState<DailyReturn[]>([]);
  const [period, setPeriod] = useState<'today' | 'week' | 'month' | 'all'>('month');
  const [loading, setLoading] = useState(true);

  const positions = useStore((s) => s.positions);
  const profits = useStore((s) => s.profits);
  const tradingMode = useStore((s) => s.tradingMode);
  const accountBalance = useStore((s) => s.accountBalance);

  const loadPortfolioData = useCallback(async () => {
    setLoading(true);
    try {
      // Get stats from API
      const data = await apiFetch(`/api/portfolio/stats?period=${period}`);
      setStats(data.stats);

      // Get positions grouped by broker
      const posData = await apiFetch('/api/positions/by-broker');
      setPositionGroups(posData.groups || []);

      // Get daily returns
      const returnsData = await apiFetch(`/api/portfolio/daily-returns?period=${period}`);
      setDailyReturns(returnsData.returns || []);
    } catch (err) {
      // Fall back to local data if API fails
      calculateLocalStats();
    } finally {
      setLoading(false);
    }
  }, [period]);

  const calculateLocalStats = useCallback(() => {
    // Calculate from local Zustand state
    const posValues = Object.values(positions);
    const totalValue = posValues.reduce((sum, p) => sum + (p.market_value ?? 0), 0);
    const totalPnl = posValues.reduce((sum, p) => sum + (p.unrealized_pnl ?? 0), 0);
    const totalPnLPct = accountBalance > 0 ? (totalPnl / accountBalance) * 100 : 0;

    // Mock stats for now (would come from API)
    setStats({
      totalValue,
      totalPnl,
      totalPnLPct,
      winRate: 0,
      avgWin: 0,
      avgLoss: 0,
      profitFactor: 0,
      maxDrawdown: 0,
      sharpeRatio: 0,
    });

    // Group positions by broker (mock for now)
    setPositionGroups([{
      brokerId: 'all',
      brokerName: 'All Accounts',
      totalValue,
      unrealizedPnl: totalPnl,
      positions: posValues,
    }]);

    // Mock daily returns
    const returns: DailyReturn[] = [];
    for (let i = 29; i >= 0; i--) {
      const date = new Date();
      date.setDate(date.getDate() - i);
      returns.push({
        date: date.toISOString().split('T')[0],
        return: (Math.random() - 0.5) * 2,
      });
    }
    setDailyReturns(returns);
  }, [positions, profits, accountBalance]);

  useEffect(() => {
    loadPortfolioData();
  }, [loadPortfolioData]);

  const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6', '#06b6d4'];

  const safeNum = (n: number | undefined | null) => n ?? 0;

  const statsCards = stats ? [
    { label: 'Total Value', value: `$${safeNum(stats.totalValue).toFixed(2)}`, icon: Wallet, color: 'text-primary' },
    { label: 'Unrealized P&L', value: `${safeNum(stats.totalPnl) >= 0 ? '+' : ''}$${safeNum(stats.totalPnl).toFixed(2)}`, icon: safeNum(stats.totalPnl) >= 0 ? TrendingUp : TrendingDown, color: safeNum(stats.totalPnl) >= 0 ? 'text-emerald-400' : 'text-red-400' },
    { label: 'Return %', value: `${safeNum(stats.totalPnLPct) >= 0 ? '+' : ''}${safeNum(stats.totalPnLPct).toFixed(2)}%`, icon: Percent, color: safeNum(stats.totalPnLPct) >= 0 ? 'text-emerald-400' : 'text-red-400' },
    { label: 'Win Rate', value: `${safeNum(stats.winRate).toFixed(1)}%`, icon: Target, color: 'text-primary' },
    { label: 'Profit Factor', value: safeNum(stats.profitFactor).toFixed(2), icon: Activity, color: 'text-primary' },
    { label: 'Sharpe Ratio', value: safeNum(stats.sharpeRatio).toFixed(2), icon: BarChart3, color: 'text-primary' },
  ] : [];

  const exportCSV = async () => {
    try {
      const data = await apiFetch('/api/portfolio/export?format=csv');
      const blob = new Blob([data], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `portfolio-${period}-${new Date().toISOString().split('T')[0]}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success('Portfolio exported');
    } catch (err) {
      toast.error('Export failed');
    }
  };

  return (
    <div className="space-y-6" data-testid="portfolio-tab">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Wallet size={18} className="text-primary" />
          <div>
            <h2 className="text-base font-semibold text-foreground">Portfolio Analytics</h2>
            <p className="text-xs text-muted-foreground">Multi-account performance and allocation</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Period selector */}
          <div className="flex items-center gap-1 bg-secondary/30 rounded-lg p-1">
            {(['today', 'week', 'month', 'all'] as const).map((p) => (
              <button
                key={p}
                data-testid={`period-${p}`}
                onClick={() => setPeriod(p)}
                className={`px-3 py-1 text-xs font-medium rounded ${
                  period === p
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>

          <button
            onClick={exportCSV}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border bg-secondary/50 text-muted-foreground hover:text-foreground transition-colors"
            data-testid="export-portfolio"
          >
            <Download size={12} /> Export
          </button>

          <button
            onClick={loadPortfolioData}
            disabled={loading}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
            data-testid="refresh-portfolio"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {statsCards.map((card) => (
          <div key={card.label} className="glass rounded-xl border border-border p-4">
            <div className="flex items-center gap-2 mb-1">
              <card.icon size={13} className={card.color} />
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">
                {card.label}
              </span>
            </div>
            <span className={`font-mono text-xl font-bold ${card.color}`}>{card.value}</span>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Allocation Pie Chart */}
        <div className="glass rounded-xl border border-border p-4">
          <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <PieChart size={14} className="text-primary" /> Allocation by Account
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={positionGroups}
                  dataKey="totalValue"
                  nameKey="brokerName"
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={2}
                  label={({ brokerName, percent }) => `${brokerName} ${(percent * 100).toFixed(0)}%`}
                >
                  {positionGroups.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: 'hsl(222 47% 4%)', border: '1px solid hsl(215 20% 16%)', borderRadius: '8px' }}
                  formatter={(value: number) => `$${value.toFixed(2)}`}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Daily Returns Bar Chart */}
        <div className="glass rounded-xl border border-border p-4">
          <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
            <BarChart3 size={14} className="text-primary" /> Daily Returns
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dailyReturns}>
                <XAxis
                  dataKey="date"
                  tick={{ fill: 'hsl(215 20% 65%)', fontSize: 10 }}
                  tickFormatter={(v) => v.slice(5)}
                  axisLine={{ stroke: 'hsl(215 20% 16%)' }}
                />
                <YAxis
                  tick={{ fill: 'hsl(215 20% 65%)', fontSize: 10 }}
                  tickFormatter={(v) => `${v.toFixed(1)}%`}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: 'hsl(222 47% 4%)', border: '1px solid hsl(215 20% 16%)', borderRadius: '8px' }}
                  formatter={(value: number) => `${value.toFixed(2)}%`}
                />
                <Bar dataKey="return" fill="#6366f1">
                  {dailyReturns.map((entry, index) => (
                    <Cell key={index} fill={entry.return >= 0 ? '#10b981' : '#f43f5e'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Position Groups Table */}
      <div className="glass rounded-xl border border-border overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="text-sm font-semibold text-foreground">Account Breakdown</h3>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-border text-left text-[10px] uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-2">Broker</th>
              <th className="px-4 py-2 text-right">Value</th>
              <th className="px-4 py-2 text-right">Unrealized P&L</th>
              <th className="px-4 py-2 text-right">Positions</th>
            </tr>
          </thead>
          <tbody>
            {positionGroups.map((group) => (
              <tr key={group.brokerId} className="border-b border-border/50 hover:bg-secondary/30">
                <td className="px-4 py-3 text-sm font-medium text-foreground">{group.brokerName}</td>
                <td className="px-4 py-3 text-sm font-mono text-right text-foreground">
                  ${group.totalValue.toFixed(2)}
                </td>
                <td className={`px-4 py-3 text-sm font-mono text-right ${
                  group.unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-red-400'
                }`}>
                  {group.unrealizedPnl >= 0 ? '+' : ''}${group.unrealizedPnl.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-sm font-mono text-right text-muted-foreground">
                  {group.positions.length}
                </td>
              </tr>
            ))}
          </tbody>
          {positionGroups.length > 1 && (
            <tfoot>
              <tr className="border-t-2 border-border bg-secondary/30">
                <td className="px-4 py-3 text-sm font-bold text-foreground">Total</td>
                <td className="px-4 py-3 text-sm font-mono font-bold text-right text-foreground">
                  ${positionGroups.reduce((s, g) => s + g.totalValue, 0).toFixed(2)}
                </td>
                <td className={`px-4 py-3 text-sm font-mono font-bold text-right ${
                  positionGroups.reduce((s, g) => s + g.unrealizedPnl, 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
                }`}>
                  ${positionGroups.reduce((s, g) => s + g.unrealizedPnl, 0).toFixed(2)}
                </td>
                <td className="px-4 py-3 text-sm font-mono text-right text-muted-foreground">
                  {positionGroups.reduce((s, g) => s + g.positions.length, 0)}
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}