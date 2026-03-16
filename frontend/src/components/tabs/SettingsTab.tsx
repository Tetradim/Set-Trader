import { useState, useEffect } from 'react';
import { useStore } from '@/stores/useStore';
import { apiFetch } from '@/lib/api';
import { Save, Plus, X, MessageCircle, Key } from 'lucide-react';
import { toast } from 'sonner';

export function SettingsTab() {
  const [token, setToken] = useState('');
  const [chatIds, setChatIds] = useState<string[]>([]);
  const [newChatId, setNewChatId] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    apiFetch('/api/settings')
      .then((data) => {
        setToken(data.telegram?.bot_token || '');
        setChatIds(data.telegram?.chat_ids || []);
        useStore.getState().setSimulate247(data.simulate_24_7 || false);
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await apiFetch('/api/settings', {
        method: 'POST',
        body: JSON.stringify({
          telegram: { bot_token: token, chat_ids: chatIds },
          simulate_24_7: useStore.getState().simulate247,
        }),
      });
      toast.success('Settings saved');
    } catch (e: any) {
      toast.error(e.message || 'Save failed');
    } finally {
      setSaving(false);
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
      {/* Telegram Integration */}
      <section className="glass rounded-xl border border-border p-6 space-y-5">
        <div className="flex items-center gap-2 mb-2">
          <MessageCircle size={18} className="text-primary" />
          <h3 className="text-sm font-bold text-foreground">Telegram Integration</h3>
        </div>
        <p className="text-xs text-muted-foreground">
          Connect a Telegram bot to receive trade notifications and execute commands remotely.
          Multiple chat IDs allow multiple users/accounts to control the bot.
        </p>

        {/* Bot Token */}
        <div>
          <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium block mb-1.5 flex items-center gap-1">
            <Key size={10} /> Bot Token
          </label>
          <input
            data-testid="telegram-token-input"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Enter your Telegram Bot Token"
            className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
          />
          <p className="text-[10px] text-muted-foreground/60 mt-1">
            Create a bot via @BotFather on Telegram to get your token
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
          </div>
        </div>

        {/* Available Commands */}
        <div>
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-2">
            Available Telegram Commands
          </p>
          <div className="grid grid-cols-2 gap-1 text-xs font-mono">
            {[
              ['/new SYMBOL POWER', 'Add new ticker'],
              ['/cancel SYMBOL', 'Cancel ticker orders'],
              ['/cancelall', 'Cancel all orders'],
              ['/portfolio', 'View portfolio'],
              ['/history', 'Trade history'],
              ['/help', 'List all commands'],
            ].map(([cmd, desc]) => (
              <div key={cmd} className="flex gap-2 px-2 py-1 rounded bg-secondary/50">
                <span className="text-primary font-bold">{cmd}</span>
                <span className="text-muted-foreground">{desc}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Save */}
      <button
        data-testid="save-settings-btn"
        onClick={handleSave}
        disabled={saving}
        className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-lg shadow-primary/25 disabled:opacity-50"
      >
        <Save size={14} />
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  );
}
