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