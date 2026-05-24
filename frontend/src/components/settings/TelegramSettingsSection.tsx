import { AlertCircle, CheckCircle2, Key, Loader2, MessageCircle, Plus, Save, Send, Wifi, WifiOff, X } from 'lucide-react';

type Props = {
  token: string;
  chatIds: string[];
  newChatId: string;
  connected: boolean;
  saving: boolean;
  testing: boolean;
  onTokenChange: (value: string) => void;
  onNewChatIdChange: (value: string) => void;
  onAddChatId: () => void;
  onRemoveChatId: (id: string) => void;
  onSave: () => void;
  onTestAlert: () => void;
};

const TELEGRAM_COMMANDS = [
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
];

export function TelegramSettingsSection({
  token,
  chatIds,
  newChatId,
  connected,
  saving,
  testing,
  onTokenChange,
  onNewChatIdChange,
  onAddChatId,
  onRemoveChatId,
  onSave,
  onTestAlert,
}: Props) {
  return (
    <>
      <section className="glass rounded-xl border border-border p-6 space-y-5">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <MessageCircle size={18} className="text-primary" />
            <h3 className="text-sm font-bold text-foreground">Telegram Integration</h3>
          </div>
          <span
            data-testid="telegram-status"
            className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${
              connected ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-secondary text-muted-foreground border-border'
            }`}
          >
            {connected ? <><Wifi size={12} /> Bot Connected</> : <><WifiOff size={12} /> Not Connected</>}
          </span>
        </div>
        <p className="text-xs text-muted-foreground">
          Connect Telegram for trade alerts, restart/offline notifications, and remote commands.
        </p>
        <div>
          <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
            <Key size={10} /> Bot Token
          </label>
          <input
            data-testid="telegram-token-input"
            type="password"
            value={token}
            onChange={(event) => onTokenChange(event.target.value)}
            placeholder="Paste your Telegram Bot Token from @BotFather"
            className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
          />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium block mb-1.5">
            Authorized Chat IDs
          </label>
          <div className="flex gap-2 mb-2">
            <input
              data-testid="telegram-chatid-input"
              value={newChatId}
              onChange={(event) => onNewChatIdChange(event.target.value)}
              placeholder="Chat ID"
              onKeyDown={(event) => event.key === 'Enter' && onAddChatId()}
              className="flex-1 bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
            />
            <button data-testid="add-chatid-btn" onClick={onAddChatId} className="px-3 py-2 rounded-lg bg-primary/20 text-primary border border-primary/30 hover:bg-primary/30 transition-all">
              <Plus size={14} />
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {chatIds.map((id) => (
              <span key={id} className="flex items-center gap-1.5 text-xs font-mono bg-secondary px-2.5 py-1 rounded-full border border-border">
                {id}
                <button onClick={() => onRemoveChatId(id)} className="text-muted-foreground hover:text-red-400 transition-colors">
                  <X size={10} />
                </button>
              </span>
            ))}
            {chatIds.length === 0 && <span className="text-[10px] text-muted-foreground/50 italic">No chat IDs added yet.</span>}
          </div>
        </div>
        <div className="rounded-lg bg-secondary/50 border border-border p-3 space-y-2">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1.5">
            <AlertCircle size={10} /> Automatic Alerts
          </p>
          <ul className="text-xs text-muted-foreground space-y-1 ml-4 list-disc">
            <li>Trade executions with price and P&L</li>
            <li>Bot restart/offline notifications</li>
            <li>Pause/resume confirmations from Telegram commands</li>
          </ul>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-2">Telegram Commands</p>
          <div className="grid grid-cols-2 gap-1 text-xs font-mono">
            {TELEGRAM_COMMANDS.map(([cmd, desc]) => (
              <div key={cmd} className="flex gap-2 px-2 py-1 rounded bg-secondary/50">
                <span className="text-primary font-bold shrink-0">{cmd}</span>
                <span className="text-muted-foreground truncate">{desc}</span>
              </div>
            ))}
          </div>
        </div>
      </section>
      <div className="flex items-center gap-3">
        <button
          data-testid="save-settings-btn"
          onClick={onSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-lg shadow-primary/25 disabled:opacity-50"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          {saving ? 'Saving...' : 'Save & Connect'}
        </button>
        <button
          data-testid="test-telegram-btn"
          onClick={onTestAlert}
          disabled={testing || !connected}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm bg-secondary text-foreground border border-border hover:bg-secondary/80 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {testing ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          {testing ? 'Sending...' : 'Send Test Alert'}
        </button>
        {connected && (
          <span className="flex items-center gap-1 text-xs text-emerald-400" data-testid="telegram-connected-indicator">
            <CheckCircle2 size={12} /> Bot polling active
          </span>
        )}
      </div>
    </>
  );
}
