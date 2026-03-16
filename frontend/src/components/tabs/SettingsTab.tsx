import { useState, useEffect } from 'react';
import { useStore } from '@/stores/useStore';
import { apiFetch } from '@/lib/api';
import {
  Save,
  Plus,
  X,
  MessageCircle,
  Key,
  Wifi,
  WifiOff,
  Send,
  Loader2,
  CheckCircle2,
  AlertCircle,
  SlidersHorizontal,
  ArrowUp,
  ArrowDown,
} from 'lucide-react';
import { toast } from 'sonner';

export function SettingsTab() {
  const [token, setToken] = useState('');
  const [chatIds, setChatIds] = useState<string[]>([]);
  const [newChatId, setNewChatId] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [tgConnected, setTgConnected] = useState(false);
  const [incStep, setIncStep] = useState(0.5);
  const [decStep, setDecStep] = useState(0.5);
  const [incText, setIncText] = useState('0.5');
  const [decText, setDecText] = useState('0.5');

  useEffect(() => {
    apiFetch('/api/settings')
      .then((data) => {
        setToken(data.telegram?.bot_token || '');
        setChatIds(data.telegram?.chat_ids || []);
        setTgConnected(data.telegram_connected || false);
        setIncStep(data.increment_step ?? 0.5);
        setDecStep(data.decrement_step ?? 0.5);
        setIncText(String(data.increment_step ?? 0.5));
        setDecText(String(data.decrement_step ?? 0.5));
        useStore.getState().setSimulate247(data.simulate_24_7 || false);
        useStore.getState().setIncrementStep(data.increment_step ?? 0.5);
        useStore.getState().setDecrementStep(data.decrement_step ?? 0.5);
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await apiFetch('/api/settings', {
        method: 'POST',
        body: JSON.stringify({
          telegram: { bot_token: token, chat_ids: chatIds },
          simulate_24_7: useStore.getState().simulate247,
          increment_step: incStep,
          decrement_step: decStep,
        }),
      });
      // Update store with new step values
      useStore.getState().setIncrementStep(incStep);
      useStore.getState().setDecrementStep(decStep);
      setTgConnected(res.telegram_running || false);
      if (res.telegram_running) {
        toast.success('Settings saved. Telegram bot connected!');
      } else if (token) {
        toast.error('Settings saved but Telegram failed to connect. Check your token.');
      } else {
        toast.success('Settings saved. Telegram disconnected.');
      }
    } catch (e: any) {
      toast.error(e.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleTestAlert = async () => {
    setTesting(true);
    try {
      await apiFetch('/api/settings/telegram/test', { method: 'POST' });
      toast.success('Test alert sent to all chat IDs!');
    } catch (e: any) {
      toast.error(e.message || 'Test failed');
    } finally {
      setTesting(false);
    }
  };

  const addChatId = () => {
    const id = newChatId.trim();
    if (id && !chatIds.includes(id)) {
      setChatIds([...chatIds, id]);
      setNewChatId('');
    }
  };

  const removeChatId = (id: string) => {
    setChatIds(chatIds.filter((c) => c !== id));
  };

  return (
    <div className="max-w-2xl space-y-8" data-testid="settings-tab">
      {/* Input Increment/Decrement Steps */}
      <section className="glass rounded-xl border border-border p-6 space-y-5">
        <div className="flex items-center gap-2 mb-2">
          <SlidersHorizontal size={18} className="text-accent" />
          <h3 className="text-sm font-bold text-foreground">Arrow Step Sizes</h3>
        </div>
        <p className="text-xs text-muted-foreground">
          Customize how much the up/down arrows on ticker card inputs change values.
          Set different amounts for increasing vs decreasing.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
              <ArrowUp size={10} className="text-emerald-400" /> Increase Step
            </label>
            <input
              data-testid="increment-step-input"
              type="text"
              inputMode="decimal"
              value={incText}
              onChange={(e) => {
                const raw = e.target.value;
                if (/^\d*\.?\d*$/.test(raw)) {
                  setIncText(raw);
                }
              }}
              onBlur={() => {
                const num = parseFloat(incText);
                if (!isNaN(num) && num >= 0.01) {
                  setIncStep(num);
                } else {
                  setIncText(String(incStep));
                }
              }}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
            />
            <p className="text-[10px] text-muted-foreground/60 mt-1">
              e.g. 0.05 means each up-arrow click adds 0.05
            </p>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
              <ArrowDown size={10} className="text-red-400" /> Decrease Step
            </label>
            <input
              data-testid="decrement-step-input"
              type="text"
              inputMode="decimal"
              value={decText}
              onChange={(e) => {
                const raw = e.target.value;
                if (/^\d*\.?\d*$/.test(raw)) {
                  setDecText(raw);
                }
              }}
              onBlur={() => {
                const num = parseFloat(decText);
                if (!isNaN(num) && num >= 0.01) {
                  setDecStep(num);
                } else {
                  setDecText(String(decStep));
                }
              }}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
            />
            <p className="text-[10px] text-muted-foreground/60 mt-1">
              e.g. 0.10 means each down-arrow click subtracts 0.10
            </p>
          </div>
        </div>
        <div className="rounded-lg bg-secondary/50 border border-border p-2 flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono text-primary">{incStep}</span>
          <ArrowUp size={10} className="text-emerald-400" /> /
          <span className="font-mono text-primary">{decStep}</span>
          <ArrowDown size={10} className="text-red-400" />
          <span>applies to all ticker card number inputs</span>
        </div>
      </section>

      {/* Telegram Integration */}
      <section className="glass rounded-xl border border-border p-6 space-y-5">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <MessageCircle size={18} className="text-primary" />
            <h3 className="text-sm font-bold text-foreground">Telegram Integration</h3>
          </div>
          {/* Connection status pill */}
          <span
            data-testid="telegram-status"
            className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${
              tgConnected
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                : 'bg-secondary text-muted-foreground border-border'
            }`}
          >
            {tgConnected ? (
              <>
                <Wifi size={12} />
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
                </span>
                Bot Connected
              </>
            ) : (
              <>
                <WifiOff size={12} /> Not Connected
              </>
            )}
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          Connect a Telegram bot to receive trade alerts, restart/offline notifications, and execute
          commands remotely. Multiple chat IDs allow multiple users to control the same bot.
        </p>

        {/* Bot Token */}
        <div>
          <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
            <Key size={10} /> Bot Token
          </label>
          <input
            data-testid="telegram-token-input"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste your Telegram Bot Token from @BotFather"
            className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
          />
          <p className="text-[10px] text-muted-foreground/60 mt-1">
            Message @BotFather on Telegram, use /newbot, and paste the token here.
          </p>
        </div>

        {/* Chat IDs */}
        <div>
          <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium block mb-1.5">
            Authorized Chat IDs
          </label>
          <div className="flex gap-2 mb-2">
            <input
              data-testid="telegram-chatid-input"
              value={newChatId}
              onChange={(e) => setNewChatId(e.target.value)}
              placeholder="Chat ID (e.g. 123456789)"
              onKeyDown={(e) => e.key === 'Enter' && addChatId()}
              className="flex-1 bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
            />
            <button
              data-testid="add-chatid-btn"
              onClick={addChatId}
              className="px-3 py-2 rounded-lg bg-primary/20 text-primary border border-primary/30 hover:bg-primary/30 transition-all"
            >
              <Plus size={14} />
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {chatIds.map((id) => (
              <span
                key={id}
                className="flex items-center gap-1.5 text-xs font-mono bg-secondary px-2.5 py-1 rounded-full border border-border"
              >
                {id}
                <button
                  onClick={() => removeChatId(id)}
                  className="text-muted-foreground hover:text-red-400 transition-colors"
                >
                  <X size={10} />
                </button>
              </span>
            ))}
            {chatIds.length === 0 && (
              <span className="text-[10px] text-muted-foreground/50 italic">
                No chat IDs added yet. Add at least one to receive alerts.
              </span>
            )}
          </div>
        </div>

        {/* Alert Behaviour */}
        <div className="rounded-lg bg-secondary/50 border border-border p-3 space-y-2">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1.5">
            <AlertCircle size={10} /> Automatic Alerts
          </p>
          <ul className="text-xs text-muted-foreground space-y-1 ml-4 list-disc">
            <li>Trade executions (BUY, SELL, STOP, TRAILING_STOP) with price &amp; P&L</li>
            <li><strong className="text-foreground">Bot restart</strong> notification when the server comes back online</li>
            <li><strong className="text-foreground">Bot offline</strong> notification before the server shuts down</li>
            <li>Pause/resume confirmations from Telegram commands</li>
          </ul>
        </div>

        {/* Available Commands */}
        <div>
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-2">
            Telegram Commands
          </p>
          <div className="grid grid-cols-2 gap-1 text-xs font-mono">
            {[
              ['/pause', 'Pause ALL trading'],
              ['/resume', 'Resume trading'],
              ['/start', 'Start trading engine'],
              ['/stop', 'Stop trading engine'],
              ['/status', 'Bot status overview'],
              ['/portfolio', 'P&L by symbol'],
              ['/new SYMBOL [POWER]', 'Add new ticker'],
              ['/cancel SYMBOL', 'Disable a ticker'],
              ['/cancelall', 'Disable all tickers'],
              ['/history', 'Last 10 trades'],
              ['/help', 'List all commands'],
            ].map(([cmd, desc]) => (
              <div key={cmd} className="flex gap-2 px-2 py-1 rounded bg-secondary/50">
                <span className="text-primary font-bold shrink-0">{cmd}</span>
                <span className="text-muted-foreground truncate">{desc}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Action buttons */}
      <div className="flex items-center gap-3">
        <button
          data-testid="save-settings-btn"
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-lg shadow-primary/25 disabled:opacity-50"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          {saving ? 'Saving...' : 'Save & Connect'}
        </button>

        <button
          data-testid="test-telegram-btn"
          onClick={handleTestAlert}
          disabled={testing || !tgConnected}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm bg-secondary text-foreground border border-border hover:bg-secondary/80 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {testing ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          {testing ? 'Sending...' : 'Send Test Alert'}
        </button>

        {tgConnected && (
          <span className="flex items-center gap-1 text-xs text-emerald-400" data-testid="telegram-connected-indicator">
            <CheckCircle2 size={12} /> Bot polling active
          </span>
        )}
      </div>
    </div>
  );
}
