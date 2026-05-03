// Incidents & Operations Console Tab.
// 
// Displays service health topology, alert feed, and runbook links.
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { AlertTriangle, Server, Activity, RefreshCw, CheckCircle, XCircle, Clock, FileText, Play } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface Service {
  service_id: string;
  name: string;
  status: 'healthy' | 'degraded' | 'down' | 'unknown';
  uptime: number;
  last_check: string;
  dependencies: string[];
  metrics: Record<string, number>;
}

interface Incident {
  incident_id: string;
  severity: 'critical' | 'warning' | 'info';
  title: string;
  description: string;
  status: 'active' | 'investigating' | 'resolved';
  service: string;
  created_at: string;
  updated_at: string;
  owner: string;
}

interface Runbook {
  runbook_id: string;
  title: string;
  service: string;
  description: string;
  steps: string[];
}

const STATUS_CONFIG = {
  healthy: { color: 'text-green-500', bg: 'bg-green-500/10', icon: CheckCircle },
  degraded: { color: 'text-yellow-500', bg: 'bg-yellow-500/10', icon: AlertTriangle },
  down: { color: 'text-red-500', bg: 'bg-red-500/10', icon: XCircle },
  unknown: { color: 'text-gray-500', bg: 'bg-gray-500/10', icon: Clock }
};

const SEVERITY_CONFIG = {
  critical: { color: 'text-red-500', bg: 'bg-red-500/10' },
  warning: { color: 'text-yellow-500', bg: 'bg-yellow-500/10' },
  info: { color: 'text-blue-500', bg: 'bg-blue-500/10' }
};

export function IncidentsOpsTab() {
  const [services, setServices] = useState<Service[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [runbooks, setRunbooks] = useState<Runbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [incidentFilter, setIncidentFilter] = useState<string>('all');

  const fetchOpsData = async () => {
    setLoading(true);
    try {
      const [servicesRes, incidentsRes, runbooksRes] = await Promise.all([
        apiFetch('/api/ops/services'),
        apiFetch('/api/ops/incidents'),
        apiFetch('/api/ops/runbooks')
      ]);
      setServices(servicesRes.services || []);
      setIncidents(incidentsRes.incidents || []);
      setRunbooks(runbooksRes.runbooks || []);
    } catch (err) {
      console.error('Failed to fetch ops data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOpsData();
    const interval = setInterval(fetchOpsData, 30000);
    return () => clearInterval(interval);
  }, []);

  const filteredIncidents = incidents.filter(inc => {
    if (incidentFilter === 'all') return true;
    return inc.status === incidentFilter;
  });

  const formatTime = (dateStr: string) => {
    return new Date(dateStr).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const formatUptime = (uptime: number) => {
    return `${uptime.toFixed(2)}%`;
  };

  if (loading && services.length === 0) {
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
          <Server className="h-8 w-8 text-cyan-500" />
          <div>
            <h2 className="text-2xl font-bold">Incidents & Ops</h2>
            <p className="text-muted-foreground">Service health and incident management</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchOpsData}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Active Incidents Alert */}
      {incidents.some(i => i.status !== 'resolved') && (
        <div className="flex items-center gap-3 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
          <AlertTriangle className="h-5 w-5 text-red-500" />
          <div>
            <p className="font-medium text-red-400">
              {incidents.filter(i => i.status !== 'resolved').length} active incidents
            </p>
          </div>
        </div>
      )}

      {/* Service Health Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {services.map((service) => {
          const statusConfig = STATUS_CONFIG[service.status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.unknown;
          const StatusIcon = statusConfig.icon;
          
          return (
            <Card key={service.service_id} className={service.status === 'down' ? 'border-red-500' : ''}>
              <CardContent className="pt-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <StatusIcon className={`h-5 w-5 ${statusConfig.color}`} />
                    <span className="font-medium">{service.name}</span>
                  </div>
                  <Badge variant={service.status === 'healthy' ? 'default' : 'destructive'}>
                    {service.status}
                  </Badge>
                </div>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Uptime</span>
                    <span className={service.uptime >= 99.9 ? 'text-green-500' : 'text-yellow-500'}>
                      {formatUptime(service.uptime)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Last Check</span>
                    <span className="text-muted-foreground">{formatTime(service.last_check)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Runbooks */}
      {runbooks.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Runbooks
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {runbooks.map((runbook) => (
                <div key={runbook.runbook_id} className="p-4 border rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium">{runbook.title}</h4>
                    <Badge variant="outline">{runbook.service}</Badge>
                  </div>
                  <p className="text-sm text-muted-foreground mb-3">{runbook.description}</p>
                  <Button variant="outline" size="sm">
                    <Play className="h-4 w-4 mr-2" />
                    View Steps
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Incidents Feed */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Incident Feed
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 mb-4">
            <select
              value={incidentFilter}
              onChange={(e) => setIncidentFilter(e.target.value)}
              className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm"
            >
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="investigating">Investigating</option>
              <option value="resolved">Resolved</option>
            </select>
          </div>
          
          <div className="space-y-3">
            {filteredIncidents.length === 0 ? (
              <p className="text-muted-foreground text-center py-8">No incidents found</p>
            ) : (
              filteredIncidents.map((incident) => {
                const severityConfig = SEVERITY_CONFIG[incident.severity as keyof typeof SEVERITY_CONFIG];
                
                return (
                  <div
                    key={incident.incident_id}
                    className={`p-4 border rounded-lg ${incident.status === 'resolved' ? 'opacity-60' : ''}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <Badge className={severityConfig.bg}>
                          <span className={severityConfig.color}>{incident.severity.toUpperCase()}</span>
                        </Badge>
                        <h4 className="font-medium">{incident.title}</h4>
                      </div>
                      <Badge variant={incident.status === 'resolved' ? 'default' : 'destructive'}>
                        {incident.status}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground mb-2">{incident.description}</p>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      <span>Service: {incident.service}</span>
                      <span>Owner: {incident.owner}</span>
                      <span>Created: {formatTime(incident.created_at)}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}