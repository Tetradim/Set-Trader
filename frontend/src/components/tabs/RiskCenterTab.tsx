"""Risk Center Dashboard Tab.

Displays live exposure ladder, limits panel, kill switches, and risk controls.
"""
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { Shield, AlertTriangle, Activity, Crosshair, ToggleLeft, ToggleRight, RefreshCw, Users, DollarSign, TrendingDown } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface ExposureLimit {
  limit_id: string;
  level: string;
  level_id: string;
  max_notional: number;
  max_daily_loss: number;
  max_position_size: number;
  soft_limit: number;
  current_notional: number;
  current_position: number;
  daily_pnl: number;
  is_enabled: boolean;
}

interface KillSwitch {
  switch_id: string;
  level: string;
  target_id: string;
  is_active: boolean;
  triggered_by: string;
  triggered_at: string | null;
  reason: string;
}

export function RiskCenterTab() {
  const [limits, setLimits] = useState<ExposureLimit[]>([]);
  const [killSwitches, setKillSwitches] = useState<KillSwitch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRiskData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [limitsRes, switchesRes] = await Promise.all([
        apiFetch('/api/risk/limits'),
        apiFetch('/api/risk/kill-switches')
      ]);
      setLimits(limitsRes.limits || []);
      setKillSwitches(switchesRes.kill_switches || []);
    } catch (err) {
      setError('Failed to load risk data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRiskData();
    const interval = setInterval(fetchRiskData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  const toggleKillSwitch = async (switchId: string, currentState: boolean) => {
    try {
      const newState = !currentState;
      await apiFetch(`/api/risk/kill-switches/${switchId}`, {
        method: newState ? 'POST' : 'DELETE',
        body: JSON.stringify({ reason: newState ? 'Manual toggle' : 'Manual reset' })
      });
      fetchRiskData();
    } catch (err) {
      console.error('Failed to toggle kill switch:', err);
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(value);
  };

  const getUtilization = (current: number, max: number) => {
    if (max <= 0) return 0;
    return Math.min((current / max) * 100, 100);
  };

  const getUtilizationColor = (utilization: number) => {
    if (utilization >= 90) return 'text-red-500';
    if (utilization >= 70) return 'text-yellow-500';
    return 'text-green-500';
  };

  if (loading && limits.length === 0) {
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
          <Shield className="h-8 w-8 text-red-500" />
          <div>
            <h2 className="text-2xl font-bold">Risk Center</h2>
            <p className="text-muted-foreground">Real-time exposure monitoring and controls</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchRiskData}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
          <AlertTriangle className="h-5 w-5 text-red-500" />
          <span className="text-red-500">{error}</span>
        </div>
      )}

      {/* Kill Switches Panel */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Kill Switches
          </CardTitle>
        </CardHeader>
        <CardContent>
          {killSwitches.length === 0 ? (
            <p className="text-muted-foreground text-sm">No kill switches configured</p>
          ) : (
            <div className="space-y-3">
              {killSwitches.map((ks) => (
                <div
                  key={ks.switch_id}
                  className={`flex items-center justify-between p-3 rounded-lg border ${
                    ks.is_active 
                      ? 'bg-red-500/10 border-red-500/30' 
                      : 'bg-green-500/10 border-green-500/30'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    {ks.is_active ? (
                      <AlertTriangle className="h-5 w-5 text-red-500" />
                    ) : (
                      <Shield className="h-5 w-5 text-green-500" />
                    )}
                    <div>
                      <p className="font-medium">
                        {ks.level.toUpperCase()}: {ks.target_id}
                      </p>
                      {ks.is_active && (
                        <p className="text-sm text-red-400">
                          {ks.reason} (by {ks.triggered_by})
                        </p>
                      )}
                    </div>
                  </div>
                  <Button
                    variant={ks.is_active ? "destructive" : "default"}
                    size="sm"
                    onClick={() => toggleKillSwitch(ks.switch_id, ks.is_active)}
                  >
                    {ks.is_active ? (
                      <>
                        <ToggleRight className="h-4 w-4 mr-1" />
                        Active
                      </>
                    ) : (
                      <>
                        <ToggleLeft className="h-4 w-4 mr-1" />
                        Inactive
                      </>
                    )}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Exposure Limits Panel */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <Crosshair className="h-5 w-5" />
            Exposure Limits
          </CardTitle>
        </CardHeader>
        <CardContent>
          {limits.length === 0 ? (
            <p className="text-muted-foreground text-sm">No exposure limits configured</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {limits.map((limit) => {
                const notionalUtil = getUtilization(limit.current_notional, limit.max_notional);
                const lossUtil = getUtilization(Math.abs(limit.daily_pnl), limit.max_daily_loss);
                
                return (
                  <div
                    key={limit.limit_id}
                    className={`p-4 rounded-lg border ${
                      !limit.is_enabled 
                        ? 'bg-muted/30 opacity-60' 
                        : 'bg-card'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <Badge variant={limit.is_enabled ? "default" : "secondary"}>
                        {limit.level}
                      </Badge>
                      <span className="text-sm font-medium">{limit.level_id}</span>
                    </div>
                    
                    <div className="space-y-3">
                      {/* Notional */}
                      <div>
                        <div className="flex items-center justify-between text-sm mb-1">
                          <span className="text-muted-foreground flex items-center gap-1">
                            <DollarSign className="h-3 w-3" />
                            Notional
                          </span>
                          <span className={getUtilizationColor(notionalUtil)}>
                            {formatCurrency(limit.current_notional)} / {formatCurrency(limit.max_notional)}
                          </span>
                        </div>
                        <div className="h-2 bg-secondary rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all ${
                              notionalUtil >= 90 ? 'bg-red-500' : notionalUtil >= 70 ? 'bg-yellow-500' : 'bg-green-500'
                            }`}
                            style={{ width: `${notionalUtil}%` }}
                          />
                        </div>
                      </div>
                      
                      {/* Daily Loss */}
                      {limit.max_daily_loss > 0 && (
                        <div>
                          <div className="flex items-center justify-between text-sm mb-1">
                            <span className="text-muted-foreground flex items-center gap-1">
                              <TrendingDown className="h-3 w-3" />
                              Daily Loss
                            </span>
                            <span className={getUtilizationColor(lossUtil)}>
                              {formatCurrency(limit.daily_pnl)} / -{formatCurrency(limit.max_daily_loss)}
                            </span>
                          </div>
                          <div className="h-2 bg-secondary rounded-full overflow-hidden">
                            <div
                              className={`h-full transition-all ${
                                lossUtil >= 90 ? 'bg-red-500' : lossUtil >= 70 ? 'bg-yellow-500' : 'bg-green-500'
                              }`}
                              style={{ width: `${lossUtil}%` }}
                            />
                          </div>
                        </div>
                      )}
                      
                      {/* Position Size */}
                      {limit.max_position_size > 0 && (
                        <div>
                          <div className="flex items-center justify-between text-sm mb-1">
                            <span className="text-muted-foreground flex items-center gap-1">
                              <Users className="h-3 w-3" />
                              Position
                            </span>
                            <span>
                              {limit.current_position.toLocaleString()} / {limit.max_position_size.toLocaleString()}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}