import { useCallback, useEffect, useMemo, useState } from 'react';
import { Activity, CheckCircle2, FlaskConical, Pause, Play, RefreshCw, Square, UploadCloud } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { useStore } from '@/stores/useStore';

type ReplaySession = {
  session_id: string;
  name: string;
  source: string;
  symbols: string[];
  trading_date: string;
  interval: string;
  bar_count: number;
  imported_at: string;
};

type ReplayStatus = {
  active: boolean;
  session_id?: string;
  symbols?: string[];
  speed?: number;
  loop?: boolean;
  first_timestamp?: string;
  last_timestamp?: string;
};

const COMMON_SYMBOLS = 'SPY,TSLA';

export function TestLabTab() {
  const tickers = useStore((s) => s.tickers);
  const running = useStore((s) => s.running);
  const paused = useStore((s) => s.paused);
  const simulate247 = useStore((s) => s.simulate247);

  const [sessions, setSessions] = useState<ReplaySession[]>([]);
  const [status, setStatus] = useState<ReplayStatus>({ active: false });
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [selectedSymbols, setSelectedSymbols] = useState<Record<string, boolean>>({});
  const [speed, setSpeed] = useState(30);
  const [loopReplay, setLoopReplay] = useState(false);
  const [disableUnselected, setDisableUnselected] = useState(true);
  const [startBots, setStartBots] = useState(true);
  const [importSymbols, setImportSymbols] = useState(COMMON_SYMBOLS);
  const [importDate, setImportDate] = useState(() => new Date(Date.now() - 86400000).toISOString().slice(0, 10));
  const [importSource, setImportSource] = useState<'yfinance' | 'alpaca'>('yfinance');
  const [busy, setBusy] = useState(false);

  const selectedSession = useMemo(
    () => sessions.find((session) => session.session_id === selectedSessionId) || null,
    [sessions, selectedSessionId],
  );

  const activeSymbols = useMemo(
    () => Object.entries(selectedSymbols).filter(([, active]) => active).map(([symbol]) => symbol),
    [selectedSymbols],
  );

  const loadReplayState = useCallback(async () => {
    const [sessionData, statusData] = await Promise.all([
      apiFetch('/api/replay/sessions?limit=100'),
      apiFetch('/api/replay/status'),
    ]);
    const nextSessions = sessionData.sessions || [];
    setSessions(nextSessions);
    setStatus(statusData.replay || { active: false });

    if (!selectedSessionId && nextSessions.length > 0) {
      const first = nextSessions[0];
      setSelectedSessionId(first.session_id);
      setSelectedSymbols(Object.fromEntries((first.symbols || []).map((symbol: string) => [symbol, true])));
    }
  }, [selectedSessionId]);

  useEffect(() => {
    loadReplayState().catch((error) => toast.error(error.message || 'Failed to load replay sessions'));
  }, [loadReplayState]);

  const chooseSession = (session: ReplaySession) => {
    setSelectedSessionId(session.session_id);
    setSelectedSymbols(Object.fromEntries((session.symbols || []).map((symbol) => [symbol, true])));
  };

  const ensureSelectedTickers = async () => {
    const current = useStore.getState().tickers;
    for (const symbol of activeSymbols) {
      if (!current[symbol]) {
        const created = await apiFetch('/api/tickers', {
          method: 'POST',
          body: JSON.stringify({ symbol, base_power: 100 }),
        });
        useStore.getState().addTicker(created);
      }
    }

    const latest = useStore.getState().tickers;
    const selectedSet = new Set(activeSymbols);
    for (const symbol of Object.keys(latest)) {
      const inSelection = selectedSet.has(symbol);
      if (inSelection || disableUnselected) {
        const updated = await apiFetch(`/api/tickers/${symbol}`, {
          method: 'PUT',
          body: JSON.stringify({ enabled: inSelection }),
        });
        useStore.getState().updateTicker(symbol, updated);
      }
    }
  };

  const startTest = async () => {
    if (!selectedSession) {
      toast.error('Choose a recorded market day first.');
      return;
    }
    if (activeSymbols.length === 0) {
      toast.error('Select at least one ticker to test.');
      return;
    }

    setBusy(true);
    try {
      if (!simulate247) {
        await apiFetch('/api/settings', { method: 'POST', body: JSON.stringify({ simulate_24_7: true }) });
        useStore.getState().setSimulate247(true);
        useStore.getState().setTradingMode('paper');
      }
      await ensureSelectedTickers();
      const replay = await apiFetch(`/api/replay/sessions/${selectedSession.session_id}/start`, {
        method: 'POST',
        body: JSON.stringify({ speed, loop: loopReplay }),
      });
      setStatus(replay.replay);
      if (startBots) {
        const bot = await apiFetch('/api/bot/start', {
          method: 'POST',
          body: JSON.stringify({ enable_all: false }),
        });
        useStore.getState().setRunning(Boolean(bot.running));
        useStore.getState().setPaused(Boolean(bot.paused));
      }
      toast.success('Replay test started.');
    } catch (error: any) {
      toast.error(error.message || 'Failed to start replay test');
    } finally {
      setBusy(false);
    }
  };

  const pauseBots = async () => {
    setBusy(true);
    try {
      const bot = await apiFetch('/api/bot/pause', { method: 'POST' });
      useStore.getState().setRunning(Boolean(bot.running));
      useStore.getState().setPaused(Boolean(bot.paused));
    } catch (error: any) {
      toast.error(error.message || 'Failed to pause bots');
    } finally {
      setBusy(false);
    }
  };

  const stopTest = async () => {
    setBusy(true);
    try {
      await apiFetch('/api/replay/stop', { method: 'POST' });
      const bot = await apiFetch('/api/bot/stop', {
        method: 'POST',
        body: JSON.stringify({ disable_all: true }),
      });
      useStore.getState().setRunning(Boolean(bot.running));
      useStore.getState().setPaused(Boolean(bot.paused));
      if (Array.isArray(bot.tickers)) useStore.getState().setTickers(bot.tickers);
      await loadReplayState();
      toast.success('Replay test stopped.');
    } catch (error: any) {
      toast.error(error.message || 'Failed to stop replay test');
    } finally {
      setBusy(false);
    }
  };

  const importReplay = async () => {
    const symbols = importSymbols.split(',').map((symbol) => symbol.trim().toUpperCase()).filter(Boolean);
    if (symbols.length === 0) {
      toast.error('Enter at least one symbol.');
      return;
    }

    setBusy(true);
    try {
      const path = importSource === 'alpaca' ? '/api/replay/import/alpaca' : '/api/replay/import/yfinance';
      const result = await apiFetch(path, {
        method: 'POST',
        body: JSON.stringify({
          symbols,
          trading_date: importDate,
          interval: '1m',
          name: `${importSource} ${importDate} ${symbols.join(', ')}`,
        }),
      });
      await loadReplayState();
      if (result.session) chooseSession(result.session);
      toast.success('Market day imported.');
    } catch (error: any) {
      toast.error(error.message || 'Import failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5" data-testid="test-lab-tab">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <FlaskConical size={18} className="text-primary" />
          <div>
            <h2 className="text-base font-semibold text-foreground">Bot Test Lab</h2>
            <p className="text-xs text-muted-foreground">Replay recorded market days against selected ticker bots.</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => loadReplayState().catch((error) => toast.error(error.message || 'Refresh failed'))}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-border bg-secondary/50 text-muted-foreground hover:text-foreground"
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]">
        <section className="glass rounded-lg border border-border p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">Recorded Market Days</h3>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{sessions.length} sessions</span>
          </div>
          <div className="max-h-[360px] space-y-2 overflow-auto pr-1">
            {sessions.map((session) => {
              const active = selectedSessionId === session.session_id;
              return (
                <button
                  key={session.session_id}
                  type="button"
                  onClick={() => chooseSession(session)}
                  className={`w-full rounded-md border p-3 text-left transition-colors ${
                    active ? 'border-primary bg-primary/10' : 'border-border bg-secondary/20 hover:bg-secondary/40'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-foreground">{session.name}</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {session.trading_date} | {session.interval} | {session.source} | {session.bar_count.toLocaleString()} bars
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {(session.symbols || []).map((symbol) => (
                          <span key={symbol} className="rounded border border-border bg-background/40 px-2 py-0.5 text-[10px] text-muted-foreground">
                            {symbol}
                          </span>
                        ))}
                      </div>
                    </div>
                    {active && <CheckCircle2 size={16} className="text-primary" />}
                  </div>
                </button>
              );
            })}
            {sessions.length === 0 && (
              <div className="rounded-md border border-dashed border-border p-6 text-center text-xs text-muted-foreground">
                No recorded market days yet. Import one from yfinance or Alpaca.
              </div>
            )}
          </div>
        </section>

        <section className="glass rounded-lg border border-border p-4">
          <h3 className="text-sm font-semibold text-foreground">Import Market Day</h3>
          <div className="mt-3 space-y-3">
            <div>
              <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Symbols</label>
              <input
                value={importSymbols}
                onChange={(event) => setImportSymbols(event.target.value)}
                className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm text-foreground"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Trading Date</label>
                <input
                  type="date"
                  value={importDate}
                  onChange={(event) => setImportDate(event.target.value)}
                  className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm text-foreground"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wider text-muted-foreground">Source</label>
                <select
                  value={importSource}
                  onChange={(event) => setImportSource(event.target.value as 'yfinance' | 'alpaca')}
                  className="mt-1 w-full rounded border border-border bg-background px-3 py-2 text-sm text-foreground"
                >
                  <option value="yfinance">yfinance</option>
                  <option value="alpaca">Alpaca</option>
                </select>
              </div>
            </div>
            <button
              type="button"
              disabled={busy}
              onClick={importReplay}
              className="flex w-full items-center justify-center gap-2 rounded bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground disabled:opacity-60"
            >
              <UploadCloud size={13} /> Import Recording
            </button>
          </div>
        </section>
      </div>

      <section className="glass rounded-lg border border-border p-4">
        <div className="grid gap-4 lg:grid-cols-[1fr_.9fr]">
          <div>
            <h3 className="text-sm font-semibold text-foreground">Ticker Activation</h3>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {(selectedSession?.symbols || []).map((symbol) => (
                <label key={symbol} className="flex items-center justify-between rounded border border-border bg-secondary/20 px-3 py-2">
                  <span>
                    <span className="block text-sm font-medium text-foreground">{symbol}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {tickers[symbol] ? 'Configured ticker' : 'Will be created for test'}
                    </span>
                  </span>
                  <input
                    type="checkbox"
                    checked={Boolean(selectedSymbols[symbol])}
                    onChange={(event) => setSelectedSymbols((current) => ({ ...current, [symbol]: event.target.checked }))}
                    className="h-4 w-4 accent-primary"
                  />
                </label>
              ))}
              {!selectedSession && <div className="text-xs text-muted-foreground">Choose a recorded market day to see ticker controls.</div>}
            </div>
          </div>

          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-foreground">Run Options</h3>
            <div className="grid grid-cols-2 gap-3">
              <label className="rounded border border-border bg-secondary/20 p-3">
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Replay Speed</span>
                <input
                  type="number"
                  min={0.01}
                  max={240}
                  value={speed}
                  onChange={(event) => setSpeed(Number(event.target.value) || 1)}
                  className="mt-1 w-full rounded border border-border bg-background px-2 py-1.5 text-sm text-foreground"
                />
              </label>
              {[
                ['Loop replay', loopReplay, setLoopReplay],
                ['Disable unselected', disableUnselected, setDisableUnselected],
                ['Start bots immediately', startBots, setStartBots],
              ].map(([label, value, setter]) => (
                <label key={label as string} className="flex items-center justify-between rounded border border-border bg-secondary/20 p-3">
                  <span className="text-xs text-foreground">{label as string}</span>
                  <input
                    type="checkbox"
                    checked={value as boolean}
                    onChange={(event) => (setter as (checked: boolean) => void)(event.target.checked)}
                    className="h-4 w-4 accent-primary"
                  />
                </label>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="glass rounded-lg border border-border p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className={`rounded px-2 py-1 ${status.active ? 'bg-emerald-500/15 text-emerald-300' : 'bg-secondary text-muted-foreground'}`}>
              Replay {status.active ? 'active' : 'idle'}
            </span>
            <span className={`rounded px-2 py-1 ${running ? 'bg-emerald-500/15 text-emerald-300' : 'bg-secondary text-muted-foreground'}`}>
              Bots {running ? (paused ? 'paused' : 'running') : 'stopped'}
            </span>
            <span className={`rounded px-2 py-1 ${simulate247 ? 'bg-primary/15 text-primary' : 'bg-red-500/15 text-red-300'}`}>
              Simulation {simulate247 ? 'enabled' : 'off'}
            </span>
            {status.session_id && <span className="rounded bg-secondary px-2 py-1 text-muted-foreground">{status.session_id}</span>}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={startTest}
              className="flex items-center gap-1.5 rounded bg-emerald-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-60"
            >
              <Play size={13} fill="currentColor" /> Start Test
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={pauseBots}
              className="flex items-center gap-1.5 rounded border border-border bg-secondary px-3 py-2 text-xs font-semibold text-foreground disabled:opacity-60"
            >
              <Pause size={13} /> Pause Bots
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={stopTest}
              className="flex items-center gap-1.5 rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-300 disabled:opacity-60"
            >
              <Square size={13} fill="currentColor" /> Stop Test
            </button>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground">
          <Activity size={12} />
          Start Test enables simulation, activates only selected ticker bots, starts the replay, and optionally starts bot evaluation.
        </div>
      </section>
    </div>
  );
}
