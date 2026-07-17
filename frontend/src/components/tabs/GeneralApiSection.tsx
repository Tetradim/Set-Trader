import { useEffect, useState } from 'react';
import { Activity, CheckCircle2, Database, KeyRound, Loader2, Save, TestTube2 } from 'lucide-react';
import { apiFetch } from '@/lib/api';

interface GeneralApiSettings {
  enabled: boolean;
  base_url: string;
  run_id: string;
  participant_id: string;
  bot_id: string;
  display_name: string;
  roles: string[];
  subscribed_symbols: string[];
  token_configured: boolean;
  timeout_seconds: number;
  starting_cash: number;
  commission_per_order: number;
  slippage_bps: number;
}

const inputClass = 'w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground';

export function GeneralApiSection() {
  const [settings, setSettings] = useState<GeneralApiSettings | null>(null);
  const [token, setToken] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiFetch('/api/general-api')
      .then((data) => setSettings(data.settings))
      .catch((error) => setMessage(error instanceof Error ? error.message : 'General API settings unavailable'));
  }, []);

  const patch = (value: Partial<GeneralApiSettings>) => setSettings((current) => current ? { ...current, ...value } : current);

  const save = async () => {
    if (!settings) return;
    setBusy(true);
    setMessage('');
    try {
      const payload: Record<string, unknown> = {
        enabled: settings.enabled,
        base_url: settings.base_url,
        run_id: settings.run_id,
        participant_id: settings.participant_id,
        display_name: settings.display_name,
        roles: settings.roles,
        subscribed_symbols: settings.subscribed_symbols,
        timeout_seconds: settings.timeout_seconds,
        starting_cash: settings.starting_cash,
        commission_per_order: settings.commission_per_order,
        slippage_bps: settings.slippage_bps,
      };
      if (token) payload.api_token = token;
      const response = await apiFetch('/api/general-api', { method: 'PUT', body: JSON.stringify(payload) });
      setSettings(response.settings);
      setToken('');
      setMessage('General API settings saved.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const action = async (kind: 'test' | 'register') => {
    setBusy(true);
    setMessage('');
    try {
      if (token) await save();
      const response = await apiFetch(`/api/general-api/${kind}`, { method: 'POST' });
      setMessage(kind === 'register'
        ? `Registered ${response.participant?.participant_id || settings?.participant_id}; token stored privately.`
        : `Archive reachable (${response.contract || 'archive.general.v1'})${response.participant_authenticated ? ' and participant authenticated.' : '.'}`);
      const refreshed = await apiFetch('/api/general-api');
      setSettings(refreshed.settings);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `${kind} failed`);
    } finally {
      setBusy(false);
    }
  };

  if (!settings) return null;

  return (
    <section className="rounded-xl border border-cyan-500/30 bg-cyan-500/5 p-4" data-testid="general-api-section">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="flex gap-3">
          <Database className="mt-0.5 text-cyan-400" size={18} />
          <div>
            <h3 className="text-sm font-semibold text-foreground">General API</h3>
            <p className="text-xs text-muted-foreground">Connect Pulse to an Archive replay as a broker participant. Archive supplies released bars and records Pulse's own orders; it never invents decisions.</p>
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input type="checkbox" checked={settings.enabled} onChange={(event) => patch({ enabled: event.target.checked })} /> Enabled
        </label>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <label className="text-[11px] text-muted-foreground">Archive General URL<input className={inputClass} value={settings.base_url} onChange={(event) => patch({ base_url: event.target.value })} /></label>
        <label className="text-[11px] text-muted-foreground">Replay run ID<input className={inputClass} value={settings.run_id} onChange={(event) => patch({ run_id: event.target.value })} placeholder="run-..." /></label>
        <label className="text-[11px] text-muted-foreground">Participant ID<input className={inputClass} value={settings.participant_id} onChange={(event) => patch({ participant_id: event.target.value })} /></label>
        <label className="text-[11px] text-muted-foreground">Symbols<input className={inputClass} value={settings.subscribed_symbols.join(', ')} onChange={(event) => patch({ subscribed_symbols: event.target.value.split(',').map((item) => item.trim().toUpperCase()).filter(Boolean) })} placeholder="SPY, TSLA" /></label>
        <label className="text-[11px] text-muted-foreground">Participant token<input className={inputClass} type="password" value={token} onChange={(event) => setToken(event.target.value)} placeholder={settings.token_configured ? 'Stored privately — enter to replace' : 'Paste token or use Register'} /></label>
        <label className="text-[11px] text-muted-foreground">Starting cash<input className={inputClass} type="number" min="0.01" value={settings.starting_cash} onChange={(event) => patch({ starting_cash: Number(event.target.value) })} /></label>
        <label className="text-[11px] text-muted-foreground">Commission per order<input className={inputClass} type="number" min="0" step="0.01" value={settings.commission_per_order} onChange={(event) => patch({ commission_per_order: Number(event.target.value) })} /></label>
        <label className="text-[11px] text-muted-foreground">Slippage (bps)<input className={inputClass} type="number" min="0" step="0.1" value={settings.slippage_bps} onChange={(event) => patch({ slippage_bps: Number(event.target.value) })} /></label>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button onClick={save} disabled={busy} className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground"><Save size={13} /> Save</button>
        <button onClick={() => action('test')} disabled={busy} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs"><TestTube2 size={13} /> Test</button>
        <button onClick={() => action('register')} disabled={busy || !settings.run_id} className="inline-flex items-center gap-2 rounded-lg border border-cyan-500/40 px-3 py-2 text-xs text-cyan-300"><KeyRound size={13} /> Register</button>
        {busy && <Loader2 size={14} className="animate-spin" />}
        {settings.token_configured && <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400"><CheckCircle2 size={12} /> token configured</span>}
      </div>
      {message && <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"><Activity size={12} />{message}</p>}
    </section>
  );
}
