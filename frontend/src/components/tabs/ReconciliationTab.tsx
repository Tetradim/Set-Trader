/**
 * Reconciliation Dashboard Tab.
 *
 * Displays internal ledger vs broker statements, break detection, and EOD sign-off.
 */
import { useState, useEffect } from 'react';

interface ReconciliationRecord {
  symbol: string;
  internalQty: number;
  brokerQty: number;
  drift: number;
  lastChecked: string;
}

export default function ReconciliationTab() {
  const [records, setRecords] = useState<ReconciliationRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchReconciliation();
  }, []);

  const fetchReconciliation = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/reconciliation');
      if (!response.ok) throw new Error('Failed to fetch reconciliation data');
      const data = await response.json();
      setRecords(data.records || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const hasDrift = records.some(r => r.drift !== 0);

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">Reconciliation Dashboard</h2>
        <button
          onClick={fetchReconciliation}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          disabled={loading}
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
          {error}
        </div>
      )}

      {hasDrift && (
        <div className="mb-4 p-3 bg-yellow-100 border border-yellow-400 text-yellow-700 rounded">
          ⚠️ Position drift detected! Internal ledger doesn't match broker statements.
        </div>
      )}

      <table className="min-w-full bg-white border border-gray-300">
        <thead>
          <tr className="bg-gray-100">
            <th className="px-4 py-2 border">Symbol</th>
            <th className="px-4 py-2 border">Internal Qty</th>
            <th className="px-4 py-2 border">Broker Qty</th>
            <th className="px-4 py-2 border">Drift</th>
            <th className="px-4 py-2 border">Last Checked</th>
          </tr>
        </thead>
        <tbody>
          {records.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-4 py-2 text-center text-gray-500">
                No reconciliation data available
              </td>
            </tr>
          ) : (
            records.map((record, idx) => (
              <tr key={idx} className={record.drift !== 0 ? 'bg-red-50' : ''}>
                <td className="px-4 py-2 border">{record.symbol}</td>
                <td className="px-4 py-2 border text-right">{record.internalQty}</td>
                <td className="px-4 py-2 border text-right">{record.brokerQty}</td>
                <td className={`px-4 py-2 border text-right font-bold ${record.drift !== 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {record.drift}
                </td>
                <td className="px-4 py-2 border">{record.lastChecked}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}