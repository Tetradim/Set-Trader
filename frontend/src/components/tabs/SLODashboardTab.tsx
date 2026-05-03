// SLO Dashboard Tab.
// 
// Displays Service Level Objectives, error budgets, and incident management.
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
        </div>
      )}
    </div>
  );
}