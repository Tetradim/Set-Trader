// Compliance & Audit Dashboard Tab.
// 
// Displays immutable event log explorer, operator attestations, and export bundles.
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { Shield, Search, Download, FileText, User, Clock, Filter, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';

interface AuditEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  user_id: string;
  username: string;
  action: string;
  details: Record<string, any>;
  ip_address?: string;
  user_agent?: string;
}

interface AuditSummary {
  total_events: number;
  unique_users: number;
  events_today: number;
  high_risk_events: number;
}

const EVENT_TYPE_CONFIG: Record<string, { color: string; bg: string }> = {
  SETTING_CHANGED: { color: 'text-blue-500', bg: 'bg-blue-500/10' },
  TICKER_CREATED: { color: 'text-green-500', bg: 'bg-green-500/10' },
  TICKER_UPDATED: { color: 'text-yellow-500', bg: 'bg-yellow-500/10' },
  BUY_EXECUTED: { color: 'text-green-500', bg: 'bg-green-500/10' },
  SELL_EXECUTED: { color: 'text-red-500', bg: 'bg-red-500/10' },
  MANUAL_SELL: { color: 'text-orange-500', bg: 'bg-orange-500/10' },
  STOP_TRIGGERED: { color: 'text-red-500', bg: 'bg-red-500/10' },
  BROKER_CONNECTED: { color: 'text-green-500', bg: 'bg-green-500/10' },
  BROKER_DISCONNECTED: { color: 'text-red-500', bg: 'bg-red-500/10' },
  LOGIN: { color: 'text-purple-500', bg: 'bg-purple-500/10' },
  LOGOUT: { color: 'text-gray-500', bg: 'bg-gray-500/10' },
};

export function ComplianceAuditTab() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [eventTypeFilter, setEventTypeFilter] = useState<string>('all');
  const [userFilter, setUserFilter] = useState<string>('all');

  const fetchAuditLogs = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '200' });
      if (eventTypeFilter !== 'all') params.append('event_type', eventTypeFilter);
      if (userFilter !== 'all') params.append('user_id', userFilter);
      
      const [eventsRes, sumRes] = await Promise.all([
        apiFetch(`/api/audit/events?${params}`),
        apiFetch('/api/audit/summary')
      ]);
      setEvents(eventsRes.events || []);
      setSummary(sumRes);
    } catch (err) {
      console.error('Failed to fetch audit logs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditLogs();
  }, [eventTypeFilter, userFilter]);

  const handleExport = async (format: 'csv' | 'json' | 'pdf') => {
    try {
      const response = await apiFetch(`/api/audit/export?format=${format}`, {
        method: 'GET'
      });
      window.open(response.download_url, '_blank');
    } catch (err) {
      console.error('Failed to export:', err);
    }
  };

  const filteredEvents = events.filter(event => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      event.event_type.toLowerCase().includes(query) ||
      event.username.toLowerCase().includes(query) ||
      event.action.toLowerCase().includes(query)
    );
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

  if (loading && events.length === 0) {
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
          <Shield className="h-8 w-8 text-indigo-500" />
          <div>
            <h2 className="text-2xl font-bold">Compliance & Audit</h2>
            <p className="text-muted-foreground">Immutable event log and operator actions</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchAuditLogs}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={() => handleExport('csv')}>
            <Download className="h-4 w-4 mr-2" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{summary.total_events}</div>
              <div className="text-sm text-muted-foreground">Total Events</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{summary.unique_users}</div>
              <div className="text-sm text-muted-foreground">Unique Users</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-green-500">{summary.events_today}</div>
              <div className="text-sm text-muted-foreground">Events Today</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-red-500">{summary.high_risk_events}</div>
              <div className="text-sm text-muted-foreground">High Risk</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search audit logs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <select
            value={eventTypeFilter}
            onChange={(e) => setEventTypeFilter(e.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm"
          >
            <option value="all">All Events</option>
            <option value="SETTING_CHANGED">Settings</option>
            <option value="TICKER_CREATED">Ticker Created</option>
            <option value="BUY_EXECUTED">Buy</option>
            <option value="SELL_EXECUTED">Sell</option>
            <option value="MANUAL_SELL">Manual Sell</option>
            <option value="LOGIN">Login</option>
          </select>
        </div>
      </div>

      {/* Events Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left text-sm font-medium">Timestamp</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Event Type</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">User</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Action</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">Details</th>
                  <th className="px-4 py-3 text-left text-sm font-medium">IP Address</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                      No audit events found
                    </td>
                  </tr>
                ) : (
                  filteredEvents.map((event) => {
                    const typeConfig = EVENT_TYPE_CONFIG[event.event_type] || { color: 'text-gray-500', bg: 'bg-gray-500/10' };
                    
                    return (
                      <tr key={event.event_id} className="border-b hover:bg-muted/30">
                        <td className="px-4 py-3 text-sm">
                          <div className="flex items-center gap-2">
                            <Clock className="h-4 w-4 text-muted-foreground" />
                            {formatTime(event.timestamp)}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <Badge className={typeConfig.bg}>
                            <span className={typeConfig.color}>{event.event_type}</span>
                          </Badge>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <User className="h-4 w-4 text-muted-foreground" />
                            {event.username}
                          </div>
                        </td>
                        <td className="px-4 py-3 font-medium">{event.action}</td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">
                          <div className="max-w-[200px] truncate">
                            {JSON.stringify(event.details).slice(0, 50)}...
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">
                          {event.ip_address || '-'}
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
    </div>
  );
}