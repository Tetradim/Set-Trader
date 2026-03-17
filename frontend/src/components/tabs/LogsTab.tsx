import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { RefreshCw, Filter, FileText, FolderOpen, ChevronDown, ChevronUp, AlertTriangle, X } from 'lucide-react';

interface LossLogDate {
  date: string;
  count: number;
  files: string[];
}

function LossLogViewer() {
  const [dates, setDates] = useState<LossLogDate[]>([]);
  const [expandedDate, setExpandedDate] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<{ date: string; file: string; content: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchDates = () => {
    setLoading(true);
    apiFetch('/api/loss-logs')
      .then((data) => setDates(data.dates || []))
      .catch(() => setDates([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchDates();
  }, []);

  const viewFile = (date: string, file: string) => {
    apiFetch(`/api/loss-logs/${date}/${file}`, { rawText: true })
      .then((content) => setViewingFile({ date, file, content }))
      .catch(() => setViewingFile({ date, file, content: 'Failed to load file.' }));
  };

  const totalLosses = dates.reduce((s, d) => s + d.count, 0);

  return (
    <div className="space-y-3" data-testid="loss-logs-section">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle size={14} className="text-red-400" />
          <span className="text-sm font-semibold text-foreground">Loss Trade Logs</span>
          {totalLosses > 0 && (
            <span className="text-[10px] bg-red-500/15 text-red-400 px-2 py-0.5 rounded-full font-mono" data-testid="total-loss-log-count">
              {totalLosses} file{totalLosses !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <button
          onClick={fetchDates}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          data-testid="refresh-loss-logs-btn"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {dates.length === 0 && !loading && (
        <div className="glass rounded-xl border border-border p-6 text-center text-muted-foreground text-xs">
          <p>No loss log files yet</p>
          <p className="mt-1 text-muted-foreground/60">Loss logs are created automatically when losing trades occur</p>
        </div>
      )}

      {/* Date folders */}
      <div className="space-y-1">
        {dates.map((d) => (
          <div key={d.date} className="glass rounded-lg border border-border overflow-hidden">
            <button
              onClick={() => setExpandedDate(expandedDate === d.date ? null : d.date)}
              className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-secondary/30 transition-colors"
              data-testid={`loss-log-date-${d.date}`}
            >
              <div className="flex items-center gap-2">
                <FolderOpen size={14} className="text-amber-400" />
                <span className="font-mono text-sm text-foreground">{d.date}</span>
                <span className="text-[10px] bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded-full font-mono">
                  {d.count} loss{d.count !== 1 ? 'es' : ''}
                </span>
              </div>
              {expandedDate === d.date ? (
                <ChevronUp size={14} className="text-muted-foreground" />
              ) : (
                <ChevronDown size={14} className="text-muted-foreground" />
              )}
            </button>

            {expandedDate === d.date && (
              <div className="border-t border-border/50 px-4 py-2 space-y-1 bg-background/50">
                {d.files.map((file) => (
                  <button
                    key={file}
                    onClick={() => viewFile(d.date, file)}
                    className="w-full flex items-center gap-2 px-3 py-1.5 rounded hover:bg-secondary/50 transition-colors text-left"
                    data-testid={`loss-log-file-${file}`}
                  >
                    <FileText size={12} className="text-red-400 shrink-0" />
                    <span className="font-mono text-xs text-foreground truncate">{file}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* File viewer modal */}
      {viewingFile && (
        <div className="glass rounded-xl border border-red-500/30 overflow-hidden" data-testid="loss-log-viewer">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-red-500/5">
            <div className="flex items-center gap-2">
              <FileText size={14} className="text-red-400" />
              <span className="font-mono text-xs text-foreground">{viewingFile.date}/{viewingFile.file}</span>
            </div>
            <button
              onClick={() => setViewingFile(null)}
              className="text-muted-foreground hover:text-foreground transition-colors"
              data-testid="close-loss-log-viewer"
            >
              <X size={14} />
            </button>
          </div>
          <pre className="p-4 font-mono text-xs text-foreground/90 whitespace-pre-wrap overflow-auto max-h-[400px]">
            {viewingFile.content}
          </pre>
        </div>
      )}
    </div>
  );
}

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
    <div className="space-y-6" data-testid="logs-tab">
      {/* Loss Logs Section */}
      <LossLogViewer />

      {/* Separator */}
      <div className="border-t border-border" />

      {/* System Logs Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter size={14} className="text-muted-foreground" />
          <span className="text-sm font-semibold text-foreground mr-2">System Logs</span>
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
