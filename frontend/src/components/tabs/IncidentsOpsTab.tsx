/**
 * Incidents & Operations Console Tab.
 *
 * Displays service health topology, alert feed, and runbook links.
 */
import { useState, useEffect } from 'react';

interface Incident {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  message: string;
  timestamp: string;
  acknowledged: boolean;
}

interface ServiceHealth {
  name: string;
  status: 'healthy' | 'degraded' | 'down';
  lastCheck: string;
}

export default function IncidentsOpsTab() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [services, setServices] = useState<ServiceHealth[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [incidentsRes, healthRes] = await Promise.all([
        fetch('/api/incidents'),
        fetch('/api/health')
      ]);
      if (incidentsRes.ok) {
        const data = await incidentsRes.json();
        setIncidents(data.incidents || []);
      }
      if (healthRes.ok) {
        const health = await healthRes.json();
        setServices([
          { name: 'MongoDB', status: health.db_status || 'healthy', lastCheck: new Date().toISOString() },
          { name: 'WebSocket', status: health.ws_clients > 0 ? 'healthy' : 'degraded', lastCheck: new Date().toISOString() },
          { name: 'Trading Engine', status: health.running ? 'healthy' : 'down', lastCheck: new Date().toISOString() },
        ]);
      }
    } catch (err) {
      console.error('Failed to fetch ops data:', err);
    } finally {
      setLoading(false);
    }
  };

  const acknowledgeIncident = async (id: string) => {
    try {
      await fetch(`/api/incidents/${id}/acknowledge`, { method: 'POST' });
      setIncidents(incidents.map(i => i.id === id ? { ...i, acknowledged: true } : i));
    } catch (err) {
      console.error('Failed to acknowledge incident:', err);
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'bg-red-100 border-red-400 text-red-700';
      case 'warning': return 'bg-yellow-100 border-yellow-400 text-yellow-700';
      default: return 'bg-blue-100 border-blue-400 text-blue-700';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy': return '✓';
      case 'degraded': return '⚠';
      case 'down': return '✗';
      default: return '?';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-green-600';
      case 'degraded': return 'text-yellow-600';
      case 'down': return 'text-red-600';
      default: return 'text-gray-600';
    }
  };

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">Incidents & Operations</h2>
        <button
          onClick={fetchData}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          disabled={loading}
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Service Health Topology */}
      <div className="mb-6">
        <h3 className="text-lg font-semibold mb-3">Service Health</h3>
        <div className="grid grid-cols-3 gap-4">
          {services.map((service) => (
            <div key={service.name} className="bg-white p-4 rounded shadow border">
              <div className="flex items-center justify-between">
                <span className="font-medium">{service.name}</span>
                <span className={`text-2xl ${getStatusColor(service.status)}`}>
                  {getStatusIcon(service.status)}
                </span>
              </div>
              <div className="text-sm text-gray-500 mt-1">
                Last check: {new Date(service.lastCheck).toLocaleTimeString()}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Alert Feed */}
      <div>
        <h3 className="text-lg font-semibold mb-3">Alert Feed</h3>
        {incidents.length === 0 ? (
          <div className="bg-green-100 border border-green-400 text-green-700 p-4 rounded">
            ✓ No active incidents
          </div>
        ) : (
          <div className="space-y-2">
            {incidents.map((incident) => (
              <div
                key={incident.id}
                className={`p-3 rounded border ${getSeverityColor(incident.severity)}`}
              >
                <div className="flex justify-between items-start">
                  <div>
                    <span className="font-bold uppercase">{incident.severity}:</span>
                    <span className="ml-2">{incident.message}</span>
                  </div>
                  {!incident.acknowledged && (
                    <button
                      onClick={() => acknowledgeIncident(incident.id)}
                      className="px-2 py-1 bg-white border rounded text-sm hover:bg-gray-100"
                    >
                      Acknowledge
                    </button>
                  )}
                </div>
                <div className="text-sm mt-1">
                  {new Date(incident.timestamp).toLocaleString()}
                  {incident.acknowledged && <span className="ml-2 text-green-600">✓ Acknowledged</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}