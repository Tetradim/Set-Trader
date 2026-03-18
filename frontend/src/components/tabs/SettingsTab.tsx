import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/stores/useStore';
import { apiFetch } from '@/lib/api';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Switch } from '@/components/ui/switch';
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
  Wallet,
  Plug,
  Shield,
  Zap,
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
  const [balanceText, setBalanceText] = useState('0');
  const [balanceValue, setBalanceValue] = useState(0);
  const [allocated, setAllocated] = useState(0);

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
        setBalanceValue(data.account_balance ?? 0);
        setBalanceText(String(data.account_balance ?? 0));
        setAllocated(data.allocated ?? 0);
        useStore.getState().setSimulate247(data.simulate_24_7 || false);
        useStore.getState().setIncrementStep(data.increment_step ?? 0.5);
        useStore.getState().setDecrementStep(data.decrement_step ?? 0.5);
        if (data.account_balance !== undefined) {
          useStore.getState().setAccountBalance(data.account_balance, data.allocated ?? 0, data.available ?? 0);
        }
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
          account_balance: balanceValue,
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
      {/* Account Balance */}
      <section className="glass rounded-xl border border-border p-6 space-y-5">
        <div className="flex items-center gap-2 mb-2">
          <Wallet size={18} className="text-primary" />
          <h3 className="text-sm font-bold text-foreground">Account Balance</h3>
        </div>
        <p className="text-xs text-muted-foreground">
          Set your total account capital. This is the master balance from which buy power is allocated to individual tickers.
          Take Profit moves gains into your Cash Reserve.
        </p>
        <div>
          <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
            <Wallet size={10} className="text-primary" /> Total Account Balance ($)
          </label>
          <input
            data-testid="account-balance-input"
            type="text"
            inputMode="decimal"
            value={balanceText}
            onChange={(e) => {
              const raw = e.target.value;
              if (/^\d*\.?\d*$/.test(raw)) {
                setBalanceText(raw);
              }
            }}
            onBlur={() => {
              const num = parseFloat(balanceText);
              if (!isNaN(num) && num >= 0) {
                setBalanceValue(num);
              } else {
                setBalanceText(String(balanceValue));
              }
            }}
            className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
            placeholder="e.g. 100000"
          />
          <p className="text-[10px] text-muted-foreground/60 mt-1">
            Your total trading capital (e.g. $100,000). Allocate portions to each ticker via Buy Power.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="rounded-lg bg-secondary/50 border border-border p-3">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Account</p>
            <p className="font-mono text-lg font-bold text-foreground">${balanceValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
          </div>
          <div className="rounded-lg bg-secondary/50 border border-border p-3">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Allocated</p>
            <p className="font-mono text-lg font-bold text-amber-400">${allocated.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
          </div>
          <div className="rounded-lg bg-secondary/50 border border-border p-3">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Available</p>
            <p className={`font-mono text-lg font-bold ${(balanceValue - allocated) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              ${(balanceValue - allocated).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
        </div>
      </section>

      {/* Trading Mode Toggle */}
      <TradingModeSection />

      {/* Broker Allocations per Ticker */}
      <BrokerAllocationsSection />

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
              ['/reconnect_brokers', 'Reconnect all brokers'],
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


interface BrokerMeta { id: string; name: string; color: string }

function TradingModeSection() {
  const simulate247 = useStore((s) => s.simulate247);
  const { send } = useWebSocket();

  const handleToggle = async (checked: boolean) => {
    useStore.getState().setSimulate247(checked);
    try {
      await apiFetch('/api/settings', {
        method: 'POST',
        body: JSON.stringify({ simulate_24_7: checked }),
      });
      toast.success(checked
        ? 'Paper Trading mode enabled. Market always open, no live orders.'
        : 'Live Trading mode enabled. Real market hours, orders routed to brokers.'
      );
    } catch (e: any) {
      toast.error(e.message || 'Failed to save mode');
    }
  };

  return (
    <section className="glass rounded-xl border border-border p-6 space-y-4" data-testid="trading-mode-section">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {simulate247 ? (
            <Shield size={18} className="text-amber-400" />
          ) : (
            <Zap size={18} className="text-emerald-400" />
          )}
          <h3 className="text-sm font-bold text-foreground">Trading Mode</h3>
        </div>
        <div className="flex items-center gap-3">
          <span className={`text-xs font-bold px-2.5 py-1 rounded-full border ${
            simulate247
              ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
              : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
          }`} data-testid="trading-mode-badge">
            {simulate247 ? 'PAPER' : 'LIVE'}
          </span>
          <Switch
            data-testid="simulation-toggle"
            checked={simulate247}
            onCheckedChange={handleToggle}
            className="data-[state=checked]:bg-amber-500"
          />
        </div>
      </div>
      <div className={`rounded-lg p-4 border ${
        simulate247
          ? 'bg-amber-500/5 border-amber-500/20'
          : 'bg-emerald-500/5 border-emerald-500/20'
      }`}>
        {simulate247 ? (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-amber-400">Paper Trading (Simulation)</p>
            <ul className="text-xs text-muted-foreground space-y-1 list-disc ml-4">
              <li>Market is treated as always open (24/7)</li>
              <li>Trades are logged locally but <strong className="text-foreground">NOT sent to brokers</strong></li>
              <li>Perfect for testing strategies risk-free</li>
              <li>All trade analytics and P&L are tracked normally</li>
            </ul>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-emerald-400">Live Trading</p>
            <ul className="text-xs text-muted-foreground space-y-1 list-disc ml-4">
              <li>Follows real US market hours (9:30 AM - 4:00 PM EST)</li>
              <li>Orders are <strong className="text-foreground">routed to connected brokers</strong></li>
              <li>Tickers without assigned brokers still trade in paper mode</li>
              <li>Broker failures are handled gracefully with alerts</li>
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

function BrokerAllocationsSection() {
  const tickersMap = useStore((s) => s.tickers);
  const tickers = Object.values(tickersMap);
  const { send } = useWebSocket();
  const [brokers, setBrokers] = useState<BrokerMeta[]>([]);
  const [editValues, setEditValues] = useState<Record<string, Record<string, string>>>({});

  useEffect(() => {
    apiFetch('/api/brokers')
      .then((data: any[]) => setBrokers(data.filter(b => b.supported).map(b => ({ id: b.id, name: b.name, color: b.color }))))
      .catch(() => {});
  }, []);

  // Init edit values from tickers — use memoized key to prevent infinite loop
  const tickerBrokerKey = tickers.map(t => `${t.symbol}:${(t.broker_ids || []).join(',')}:${JSON.stringify(t.broker_allocations || {})}`).join('|');
  
  useEffect(() => {
    const vals: Record<string, Record<string, string>> = {};
    tickers.forEach(t => {
      vals[t.symbol] = {};
      (t.broker_ids || []).forEach(bid => {
        vals[t.symbol][bid] = String((t.broker_allocations || {})[bid] ?? 0);
      });
    });
    setEditValues(vals);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickerBrokerKey]);

  const tickersWithBrokers = tickers.filter(t => (t.broker_ids || []).length > 0);

  const handleChange = (symbol: string, brokerId: string, raw: string) => {
    if (/^\d*\.?\d*$/.test(raw)) {
      setEditValues(prev => ({ ...prev, [symbol]: { ...prev[symbol], [brokerId]: raw } }));
    }
  };

  const handleBlur = (symbol: string, brokerId: string) => {
    const raw = editValues[symbol]?.[brokerId] ?? '0';
    const num = parseFloat(raw);
    if (isNaN(num) || num < 0) return;
    const ticker = tickers.find(t => t.symbol === symbol);
    if (!ticker) return;
    const newAlloc = { ...(ticker.broker_allocations || {}), [brokerId]: num };
    const newTotal = Object.values(newAlloc).reduce((s, v) => s + v, 0);
    send('UPDATE_TICKER', { symbol, broker_allocations: newAlloc, base_power: newTotal });
    toast.success(`${symbol}: ${brokerId} = $${num.toFixed(2)} (total: $${newTotal.toFixed(2)})`);
  };

  if (tickersWithBrokers.length === 0) {
    return (
      <section className="glass rounded-xl border border-border p-6 space-y-3">
        <div className="flex items-center gap-2 mb-2">
          <Plug size={18} className="text-primary" />
          <h3 className="text-sm font-bold text-foreground">Broker Allocations</h3>
        </div>
        <p className="text-xs text-muted-foreground">
          Assign brokers to ticker cards first, then set custom buy power per broker here.
          Select brokers on each card in the Watchlist tab.
        </p>
      </section>
    );
  }

  return (
    <section className="glass rounded-xl border border-border p-6 space-y-5" data-testid="broker-allocations-section">
      <div className="flex items-center gap-2 mb-2">
        <Plug size={18} className="text-primary" />
        <h3 className="text-sm font-bold text-foreground">Broker Allocations</h3>
      </div>
      <p className="text-xs text-muted-foreground">
        Set custom buy power per broker for each ticker. Total buy power = sum of all broker allocations.
        On Take Profit, gains return proportionally to each broker's allocation.
      </p>

      <div className="space-y-4">
        {tickersWithBrokers.map(ticker => {
          const alloc = ticker.broker_allocations || {};
          const total = Object.values(alloc).reduce((s, v) => s + v, 0);
          const assignedBrokers = (ticker.broker_ids || []).map(bid => brokers.find(b => b.id === bid)).filter(Boolean) as BrokerMeta[];

          return (
            <div key={ticker.symbol} className="border border-border rounded-lg overflow-hidden" data-testid={`alloc-ticker-${ticker.symbol}`}>
              <div className="flex items-center justify-between bg-secondary/30 px-4 py-2 border-b border-border">
                <span className="text-sm font-bold text-foreground font-mono">{ticker.symbol}</span>
                <span className="text-xs font-mono text-primary font-bold">Total: ${total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              </div>
              <div className="divide-y divide-border">
                {assignedBrokers.map(broker => {
                  const val = editValues[ticker.symbol]?.[broker.id] ?? String(alloc[broker.id] ?? 0);
                  const numVal = parseFloat(val) || 0;
                  const pct = total > 0 ? ((numVal / total) * 100).toFixed(0) : '0';
                  return (
                    <div key={broker.id} className="flex items-center gap-3 px-4 py-2.5" data-testid={`alloc-row-${ticker.symbol}-${broker.id}`}>
                      <div className="w-1.5 h-6 rounded-full shrink-0" style={{ backgroundColor: broker.color }} />
                      <span className="text-xs font-medium text-foreground min-w-[120px]">{broker.name}</span>
                      <div className="flex items-center gap-1.5 flex-1">
                        <span className="text-muted-foreground text-xs">$</span>
                        <input
                          data-testid={`alloc-input-${ticker.symbol}-${broker.id}`}
                          type="text"
                          inputMode="decimal"
                          value={val}
                          onChange={(e) => handleChange(ticker.symbol, broker.id, e.target.value)}
                          onBlur={() => handleBlur(ticker.symbol, broker.id)}
                          onKeyDown={(e) => { if (e.key === 'Enter') handleBlur(ticker.symbol, broker.id); }}
                          className="w-24 bg-secondary border border-border rounded-md px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
                        />
                      </div>
                      {/* Percentage bar */}
                      <div className="flex items-center gap-2 min-w-[80px]">
                        <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                          <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: broker.color }} />
                        </div>
                        <span className="text-[10px] font-mono text-muted-foreground w-8 text-right">{pct}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <div className="rounded-lg bg-secondary/50 border border-border p-3 text-xs text-muted-foreground space-y-1">
        <p className="font-medium text-foreground">How Take Profit works with multi-broker:</p>
        <ul className="list-disc ml-4 space-y-0.5">
          <li>Each broker's position is sold independently through its own API</li>
          <li>Realized gains return proportionally to each broker's allocation</li>
          <li>With compounding ON: each broker's allocation grows by its share of the profit</li>
          <li>Total buy power on the card = sum of all broker allocations</li>
        </ul>
      </div>
    </section>
  );
}
