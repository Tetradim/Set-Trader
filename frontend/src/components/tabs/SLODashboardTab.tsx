"""SLO Dashboard Tab.

Displays Service Level Objectives, error budgets, and incident management.
"""
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { Target, AlertTriangle, CheckCircle, RefreshCw, TrendingDown, Activity, Bell } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface SLOData {
  name: string;
  description: string;
  target: number;
  window: string;
  current_value: number;
  error_budget_remaining: number;
  is_burned: boolean;
}

interface AlertData {
  name: string;
  description: string;
  severity: string;
  condition: string;
  is_enabled: boolean;
}

interface IncidentData {
  incident_id: string;
  alert_rule: string;
  severity: string;
  title: string;
  status: string;
  created_at: string;
}

export function SLODashboardTab() {
  const [slos, setSlos] = useState<SLOData[]>([]);
  const [alerts, setAlerts] = useState<AlertData[]>([]);
  const [incidents, setIncidents] = useState<IncidentData[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'slos' | 'alerts' | 'incidents'>('slos');

  const fetchSLOData = async () => {
    setLoading(true);
    try {
      const [slosRes, alertsRes, incidentsRes, sumRes] = await Promise.all([
        apiFetch('/api/slo'),
        apiFetch('/api/slo/alerts'),
        apiFetch('/api/slo/incidents'),
        apiFetch('/api/slo/summary')
      ]);
      setSlos(slosRes.slos || []);
      setAlerts(alertsRes.alerts || []);
      setIncidents(incidentsRes.incidents || []);
      setSummary(sumRes);
    } catch (err) {
      console.error('Failed to fetch SLO data:', err);
/**
 * SLO Dashboard Tab.
 *
 * Displays Service Level Objectives, error budgets, and incident management.
 */
import { useState, useEffect } from 'react';

interface SLOTarget {
  name: string;
  target: number;      // e.g., 99.9 for 99.9% uptime
  current: number;
  errorBudget: number; // percentage remaining
  period: string;
}

export default function SLODashboardTab() {
  const [sloTargets, setSloTargets] = useState<SLOTarget[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchSLOData();
  }, []);

  const fetchSLOData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/slo');
      if (!res.ok) throw new Error('Failed to fetch SLO data');
      const data = await res.json();
      setSloTargets(data.targets || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSLOData();
    const interval = setInterval(fetchSLOData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading && slos.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const getSLOStatusColor = (slo: SLOData) => {
    if (slo.is_burned) return 'text-red-500';
    if (slo.error_budget_remaining < 10) return 'text-yellow-500';
    return 'text-green-500';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Target className="h-8 w-8 text-blue-500" />
          <div>
            <h2 className="text-2xl font-bold">SLO Dashboard</h2>
            <p className="text-muted-foreground">Service Level Objectives and alerting</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchSLOData}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{summary.total_slos}</div>
              <div className="text-sm text-muted-foreground">Total SLOs</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-red-500">{summary.burned_slos}</div>
              <div className="text-sm text-muted-foreground">Burned</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-yellow-500">{summary.at_risk_slos}</div>
              <div className="text-sm text-muted-foreground">At Risk</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className={`text-2xl font-bold ${summary.critical_incidents > 0 ? 'text-red-500' : 'text-green-500'}`}>
                {summary.critical_incidents}
              </div>
              <div className="text-sm text-muted-foreground">Critical Incidents</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex items-center gap-2 border-b">
        <button
          onClick={() => setTab('slos')}
          className={`px-4 py-2 font-medium border-b-2 transition-colors ${
            tab === 'slos'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground'
          }`}
        >
          <Target className="h-4 w-4 inline mr-2" />
          SLOs
        </button>
        <button
          onClick={() => setTab('alerts')}
          className={`px-4 py-2 font-medium border-b-2 transition-colors ${
            tab === 'alerts'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground'
          }`}
        >
          <Bell className="h-4 w-4 inline mr-2" />
          Alerts
        </button>
        <button
          onClick={() => setTab('incidents')}
          className={`px-4 py-2 font-medium border-b-2 transition-colors ${
            tab === 'incidents'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground'
          }`}
        >
          <AlertTriangle className="h-4 w-4 inline mr-2" />
          Incidents
        </button>
      </div>

      {/* SLOs Tab */}
      {tab === 'slos' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {slos.map((slo) => (
            <Card key={slo.name}>
              <CardContent className="pt-4">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <h4 className="font-medium">{slo.name}</h4>
                    <p className="text-sm text-muted-foreground">{slo.description}</p>
                  </div>
                  {slo.is_burned ? (
                    <Badge variant="destructive">Burned</Badge>
                  ) : slo.error_budget_remaining < 10 ? (
                    <Badge variant="secondary" className="bg-yellow-500/20 text-yellow-500">At Risk</Badge>
                  ) : (
                    <Badge variant="default" className="bg-green-500/20 text-green-500">Healthy</Badge>
                  )}
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Current</span>
                    <span className={getSLOStatusColor(slo)}>{slo.current_value.toFixed(2)}%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Target</span>
                    <span>{slo.target}%</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Error Budget</span>
                    <span className={getSLOStatusColor(slo)}>
                      {slo.error_budget_remaining > 0 ? '+' : ''}{slo.error_budget_remaining.toFixed(1)}%
                    </span>
                  </div>
                  <div className="h-2 bg-secondary rounded-full overflow-hidden">
                    <div
                      className={`h-full ${getSLOStatusColor(slo).replace('text-', 'bg-')}`}
                      style={{ width: `${Math.min(slo.current_value, 100)}%` }}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Alerts Tab */}
      {tab === 'alerts' && (
        <div className="space-y-3">
          {alerts.map((alert) => (
            <div key={alert.name} className="p-4 border rounded-lg">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="font-medium">{alert.name}</h4>
                    <Badge variant={alert.severity === 'critical' ? 'destructive' : 'secondary'}>
                      {alert.severity}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{alert.description}</p>
                  <p className="text-sm font-mono mt-1">When: {alert.condition}</p>
                </div>
                <div className="flex items-center gap-2">
                  {alert.is_enabled ? (
                    <CheckCircle className="h-5 w-5 text-green-500" />
                  ) : (
                    <AlertTriangle className="h-5 w-5 text-gray-500" />
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Incidents Tab */}
      {tab === 'incidents' && (
        <div className="space-y-3">
          {incidents.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">No active incidents</p>
          ) : (
            incidents.map((incident) => (
              <div key={incident.incident_id} className="p-4 border rounded-lg bg-red-500/5">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge variant={incident.severity === 'critical' ? 'destructive' : 'secondary'}>
                      {incident.severity}
                    </Badge>
                    <h4 className="font-medium">{incident.title}</h4>
                  </div>
                  <Badge variant="outline">{incident.status}</Badge>
                </div>
                <p className="text-sm text-muted-foreground">{incident.description}</p>
                <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                  <span>ID: {incident.incident_id}</span>
                  <span>Alert: {incident.alert_rule}</span>
                  <span>Created: {incident.created_at}</span>
                </div>
              </div>
            ))
          )}
  const getStatusColor = (current: number, target: number) => {
    const ratio = current / target;
    if (ratio >= 1) return 'text-green-600 bg-green-100';
    if (ratio >= 0.95) return 'text-yellow-600 bg-yellow-100';
    return 'text-red-600 bg-red-100';
  };

  const getBudgetStatus = (budget: number) => {
    if (budget >= 50) return 'text-green-600';
    if (budget >= 20) return 'text-yellow-600';
    return 'text-red-600';
  };

  const formatPercent = (val: number) => `${val.toFixed(3)}%`;

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-bold">SLO Dashboard</h2>
        <div className="flex gap-2">
          <button
            onClick={fetchSLOData}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
            disabled={loading}
          >
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
          Error: {error}
        </div>
      )}

      {/* SLO Overview Cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white p-4 rounded shadow border">
          <div className="text-sm text-gray-500">Total SLOs</div>
          <div className="text-3xl font-bold">{sloTargets.length}</div>
        </div>
        <div className="bg-white p-4 rounded shadow border">
          <div className="text-sm text-gray-500">Meeting Target</div>
          <div className="text-3xl font-bold text-green-600">
            {sloTargets.filter(s => s.current >= s.target).length}
          </div>
        </div>
        <div className="bg-white p-4 rounded shadow border">
          <div className="text-sm text-gray-500">Breaching</div>
          <div className="text-3xl font-bold text-red-600">
            {sloTargets.filter(s => s.current < s.target).length}
          </div>
        </div>
      </div>

      {/* SLO Targets Table */}
      <div className="bg-white rounded shadow border overflow-hidden">
        <table className="min-w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">SLO Name</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Target</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Current</th>
              <th className="px-4 py-3 text-center text-sm font-medium text-gray-500">Status</th>
              <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Error Budget</th>
              <th className="px-4 py-3 text-center text-sm font-medium text-gray-500">Period</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {sloTargets.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                  No SLO data available. Configure SLOs in the system settings.
                </td>
              </tr>
            ) : (
              sloTargets.map((slo, idx) => {
                const budgetUsed = 100 - slo.errorBudget;
                return (
                  <tr key={idx}>
                    <td className="px-4 py-3 font-medium">{slo.name}</td>
                    <td className="px-4 py-3 text-right">{formatPercent(slo.target)}</td>
                    <td className={`px-4 py-3 text-right font-bold ${slo.current >= slo.target ? 'text-green-600' : 'text-red-600'}`}>
                      {formatPercent(slo.current)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-1 rounded text-sm ${getStatusColor(slo.current, slo.target)}`}>
                        {slo.current >= slo.target ? 'Healthy' : 'At Risk'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-20 h-2 bg-gray-200 rounded overflow-hidden">
                          <div
                            className={`h-full ${budgetUsed > 50 ? 'bg-green-500' : budgetUsed > 20 ? 'bg-yellow-500' : 'bg-red-500'}`}
                            style={{ width: `${Math.min(budgetUsed, 100)}%` }}
                          />
                        </div>
                        <span className={`text-sm font-medium ${getBudgetStatus(slo.errorBudget)}`}>
                          {slo.errorBudget.toFixed(1)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center text-sm text-gray-500">{slo.period}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Error Budget Burn Rate Alert */}
      {sloTargets.some(s => s.errorBudget < 20) && (
        <div className="mt-6 p-4 bg-red-50 border border-red-300 rounded">
          <div className="flex items-center">
            <span className="text-2xl mr-3">⚠️</span>
            <div>
              <h3 className="font-bold text-red-700">Error Budget Burn Rate Alert</h3>
              <p className="text-red-600 text-sm">
                Some SLOs are burning through their error budget faster than expected.
                Review recent incidents and take corrective action.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}