import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { RefreshCw, Filter } from 'lucide-react';

export function LogsTab() {
  const [logs, setLogs] = useState<any[]>([]);
  const [filter, setFilter] = useState('ALL');
  const [loading, setLoading] = useState(false);

  const fetchLogs = () => {
    setLoading(true);
    apiFetch(`/api/logs?limit=200&level=${filter}`)
      .then(setLogs)
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, [filter]);

  const levelColors: Record<string, string> = {
    INFO: 'text-blue-400',
    WARNING: 'text-amber-400',
    ERROR: 'text-red-400',
    DEBUG: 'text-muted-foreground',
  };

  return (
    <div className="space-y-4" data-testid="logs-tab">
      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-muted-foreground" />
          {['ALL', 'INFO', 'WARNING', 'ERROR'].map((level) => (
            <button
              key={level}
              data-testid={`log-filter-${level.toLowerCase()}`}
              onClick={() => setFilter(level)}
              className={`text-[10px] uppercase font-semibold px-2.5 py-1 rounded-full border transition-all ${
                filter === level
                  ? 'bg-primary/20 text-primary border-primary/40'
                  : 'text-muted-foreground border-border hover:border-primary/30'
              }`}
            >
              {level}
            </button>
          ))}
        </div>
        <button
          data-testid="refresh-logs-btn"
          onClick={fetchLogs}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Log output */}
      <div className="glass rounded-xl border border-border overflow-hidden" data-testid="logs-container">
        <div className="max-h-[600px] overflow-auto p-3 font-mono text-xs space-y-0.5">
          {logs.length > 0 ? (
            logs.map((log, i) => (
              <div
                key={i}
                className="flex gap-3 px-2 py-1 rounded hover:bg-secondary/30 transition-colors"
              >
                <span className="text-muted-foreground/60 shrink-0 w-36">
                  {new Date(log.timestamp).toLocaleString()}
                </span>
                <span className={`shrink-0 w-16 font-bold ${levelColors[log.level] || 'text-foreground'}`}>
                  {log.level}
                </span>
                <span className="text-foreground/80">{log.message}</span>
              </div>
            ))
          ) : (
            <div className="flex flex-col items-center justify-center h-32 text-muted-foreground">
              <p>No logs available</p>
              <p className="mt-1 text-muted-foreground/60 text-[10px]">
                Logs will populate as the bot runs
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
