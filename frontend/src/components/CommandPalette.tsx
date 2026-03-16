import { useState } from 'react';
import { Command } from 'cmdk';
import { useHotkeys } from 'react-hotkeys-hook';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Plus, Play, Square, Pause, Trash2, BarChart3, History, ScrollText, Settings, LayoutDashboard, Crosshair } from 'lucide-react';
import { useStore } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const { send } = useWebSocket();
  const tickers = useStore((s) => s.tickers);
  const running = useStore((s) => s.running);
  const paused = useStore((s) => s.paused);
  const setActiveTab = useStore((s) => s.setActiveTab);

  useHotkeys('mod+k', (e) => {
    e.preventDefault();
    setOpen((o) => !o);
  });

  if (!open) return null;

  const handleAction = (action: () => void) => {
    action();
    setOpen(false);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[18vh] bg-black/60 backdrop-blur-sm"
      onClick={() => setOpen(false)}
      data-testid="command-palette-overlay"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: -10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96 }}
        transition={{ duration: 0.15 }}
        className="w-full max-w-lg glass rounded-xl border border-border shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        data-testid="command-palette"
      >
        <Command className="flex flex-col h-full">
          <div className="flex items-center border-b border-border px-3">
            <Search className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
            <Command.Input
              placeholder="Search commands, symbols..."
              className="flex h-12 w-full bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground text-foreground"
              data-testid="command-palette-input"
            />
          </div>
          <Command.List className="max-h-[300px] overflow-y-auto p-2">
            <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
              No results found.
            </Command.Empty>

            <Command.Group heading="Navigation" className="px-2 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
              {[
                { label: 'Watchlist', icon: LayoutDashboard, tab: 'watchlist' },
                { label: 'Positions', icon: Crosshair, tab: 'positions' },
                { label: 'Trade History', icon: History, tab: 'history' },
                { label: 'Logs', icon: ScrollText, tab: 'logs' },
                { label: 'Settings', icon: Settings, tab: 'settings' },
              ].map((item) => (
                <Command.Item
                  key={item.tab}
                  onSelect={() => handleAction(() => setActiveTab(item.tab))}
                  className="flex items-center gap-2 px-2 py-2 rounded-md hover:bg-secondary cursor-pointer text-sm text-foreground"
                >
                  <item.icon size={14} className="text-muted-foreground" /> {item.label}
                </Command.Item>
              ))}
            </Command.Group>

            <Command.Group heading="Bot Controls" className="px-2 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
              <Command.Item
                onSelect={() => handleAction(() => send(running ? 'STOP_BOT' : 'START_BOT'))}
                className="flex items-center gap-2 px-2 py-2 rounded-md hover:bg-secondary cursor-pointer text-sm text-foreground"
              >
                {running ? <Square size={14} className="text-red-400" /> : <Play size={14} className="text-emerald-400" />}
                {running ? 'Stop Bot' : 'Start Bot'}
              </Command.Item>
              <Command.Item
                onSelect={() => handleAction(() => send('GLOBAL_PAUSE', { pause: !paused }))}
                className="flex items-center gap-2 px-2 py-2 rounded-md hover:bg-secondary cursor-pointer text-sm text-foreground"
              >
                <Pause size={14} className="text-amber-400" />
                {paused ? 'Resume Trading' : 'Pause All Trading'}
              </Command.Item>
            </Command.Group>

            {Object.keys(tickers).length > 0 && (
              <Command.Group heading="Active Tickers" className="px-2 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                {Object.values(tickers).map((t) => (
                  <Command.Item
                    key={t.symbol}
                    className="flex items-center justify-between px-2 py-2 rounded-md hover:bg-secondary cursor-pointer text-sm"
                  >
                    <span className="font-bold text-foreground">{t.symbol}</span>
                    <div className="flex gap-3 text-[10px] text-muted-foreground">
                      <button
                        onClick={(e) => { e.stopPropagation(); send('UPDATE_TICKER', { symbol: t.symbol, enabled: !t.enabled }); setOpen(false); }}
                        className="hover:text-primary"
                      >
                        {t.enabled ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); send('DELETE_TICKER', { symbol: t.symbol }); setOpen(false); }}
                        className="hover:text-red-400 flex items-center gap-0.5"
                      >
                        <Trash2 size={10} /> Remove
                      </button>
                    </div>
                  </Command.Item>
                ))}
              </Command.Group>
            )}
          </Command.List>

          <div className="border-t border-border px-3 py-2 flex items-center gap-4 text-[10px] text-muted-foreground">
            <span>Navigate with arrows</span>
            <span>Enter to select</span>
            <span>Esc to close</span>
          </div>
        </Command>
      </motion.div>
    </div>
  );
}
