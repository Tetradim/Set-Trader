import { useState, useCallback } from 'react';
import { useStore, TickerConfig } from '@/stores/useStore';
import { TickerCard } from '../TickerCard';
import { ConfigModal } from '../ConfigModal';
import { Shield, Zap, Sun, Moon, LayoutGrid, List, Trash2, Power, PowerOff, Copy } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { apiFetch } from '@/lib/api';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  rectSortingStrategy,
} from '@dnd-kit/sortable';
import { toast } from 'sonner';

export function WatchlistTab() {
  const tickers = useStore((s) => Object.values(s.tickers));
  const running = useStore((s) => s.running);
  const connected = useStore((s) => s.connected);
  const simulate247 = useStore((s) => s.simulate247);
  const liveDuringMarketHours = useStore((s) => s.liveDuringMarketHours);
  const paperAfterHours = useStore((s) => s.paperAfterHours);
  const setLiveDuringMarketHours = useStore((s) => s.setLiveDuringMarketHours);
  const setPaperAfterHours = useStore((s) => s.setPaperAfterHours);
  const chartEnabled = useStore((s) => s.chartEnabled);
  const profits = useStore((s) => s.profits);
  const compactMode = useStore((s) => s.compactMode);
  const setCompactMode = useStore((s) => s.setCompactMode);
  const selectedTickers = useStore((s) => s.selectedTickers);
  const clearTickerSelection = useStore((s) => s.clearTickerSelection);
  const selectAllTickers = useStore((s) => s.selectAllTickers);
  const [configSymbol, setConfigSymbol] = useState<string | null>(null);

  // Sort tickers by Net P&L (descending - best winners first)
  const sorted = [...tickers].sort((a, b) => {
    const pnlA = profits[a.symbol] ?? 0;
    const pnlB = profits[b.symbol] ?? 0;
    return pnlB - pnlA; // Descending order
  });
  const activeTickers = sorted.filter((t) => t.enabled);
  const inactiveTickers = sorted.filter((t) => !t.enabled);

  const configTicker = configSymbol ? tickers.find((t) => t.symbol === configSymbol) : null;

  const handleConfigOpen = useCallback((symbol: string) => {
    setConfigSymbol(symbol);
  }, []);

  const handleConfigClose = useCallback(() => {
    setConfigSymbol(null);
  }, []);

  // Auto-mode toggle handlers
  const handleLiveDuringMarketToggle = useCallback(async () => {
    const newValue = !liveDuringMarketHours;
    setLiveDuringMarketHours(newValue);
    try {
      await apiFetch('/api/settings', {
        method: 'POST',
        body: JSON.stringify({ live_during_market_hours: newValue }),
      });
    } catch (err) {
      console.error('Failed to update live_during_market_hours:', err);
      setLiveDuringMarketHours(!newValue); // Revert on error
    }
  }, [liveDuringMarketHours, setLiveDuringMarketHours]);

  const handlePaperAfterHoursToggle = useCallback(async () => {
    const newValue = !paperAfterHours;
    setPaperAfterHours(newValue);
    try {
      await apiFetch('/api/settings', {
        method: 'POST',
        body: JSON.stringify({ paper_after_hours: newValue }),
      });
    } catch (err) {
      console.error('Failed to update paper_after_hours:', err);
      setPaperAfterHours(!newValue); // Revert on error
    }
  }, [paperAfterHours, setPaperAfterHours]);

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    // Compute new order
    const allSymbols = sorted.map((t) => t.symbol);
    const oldIndex = allSymbols.indexOf(active.id as string);
    const newIndex = allSymbols.indexOf(over.id as string);

    if (oldIndex === -1 || newIndex === -1) return;

    const reordered = [...allSymbols];
    const [moved] = reordered.splice(oldIndex, 1);
    reordered.splice(newIndex, 0, moved);

    // Optimistic UI update
    const store = useStore.getState();
    reordered.forEach((sym, i) => {
      store.updateTicker(sym, { sort_order: i } as Partial<TickerConfig>);
    });

    // Persist to backend
    try {
      await apiFetch('/api/tickers/reorder', {
        method: 'POST',
        body: JSON.stringify({ order: reordered }),
      });
    } catch (err) {
      console.error('Reorder failed:', err);
    }
  }, [sorted]);

  const activeSymbols = activeTickers.map((t) => t.symbol);
  const inactiveSymbols = inactiveTickers.map((t) => t.symbol);

  // Bulk actions
  const handleBulkEnable = async () => {
    for (const sym of selectedTickers) {
      await apiFetch('/api/tickers', { method: 'POST', body: JSON.stringify({ symbol: sym, enabled: true }) });
    }
    toast.success(`Enabled ${selectedTickers.length} tickers`);
    clearTickerSelection();
  };

  const handleBulkDisable = async () => {
    for (const sym of selectedTickers) {
      await apiFetch('/api/tickers', { method: 'POST', body: JSON.stringify({ symbol: sym, enabled: false }) });
    }
    toast.success(`Disabled ${selectedTickers.length} tickers`);
    clearTickerSelection();
  };

  const handleBulkDelete = async () => {
    if (!confirm(`Delete ${selectedTickers.length} tickers?`)) return;
    for (const sym of selectedTickers) {
      await apiFetch(`/api/tickers/${sym}`, { method: 'DELETE' });
    }
    toast.success(`Deleted ${selectedTickers.length} tickers`);
    clearTickerSelection();
  };

  return (
    <div className="space-y-8" data-testid="watchlist-tab">
      {/* Control bar */}
      <div className="flex items-center justify-between p-3 rounded-lg glass border border-border">
        <div className="flex items-center gap-3">
          {/* Current mode indicator */}
          <span
            data-testid="watchlist-mode-indicator"
            className={`flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full border ${
              simulate247
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            }`}
          >
            {simulate247 ? <Shield size={12} /> : <Zap size={12} />}
            {simulate247 ? 'Paper Trading' : 'Live Trading'}
          </span>

          {/* Auto-mode toggles */}
          <div className="flex items-center gap-1.5 ml-2">
            <button
              data-testid="live-during-market-toggle"
              onClick={handleLiveDuringMarketToggle}
              className={`flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded-full border transition-all ${
                liveDuringMarketHours
                  ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40'
                  : 'bg-secondary/50 text-muted-foreground border-border hover:border-emerald-500/30 hover:text-emerald-400'
              }`}
              title="Go LIVE during market hours (9:30 AM - 4:00 PM ET)"
            >
              <Sun size={10} />
              Live @ Open
            </button>
            <button
              data-testid="paper-after-hours-toggle"
              onClick={handlePaperAfterHoursToggle}
              className={`flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded-full border transition-all ${
                paperAfterHours
                  ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                  : 'bg-secondary/50 text-muted-foreground border-border hover:border-amber-500/30 hover:text-amber-400'
              }`}
              title="Switch to PAPER after market close"
            >
              <Moon size={10} />
              Paper @ Close
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Bulk actions when tickers selected */}
          {selectedTickers.length > 0 && (
            <div className="flex items-center gap-1 mr-2">
              <span className="text-xs text-muted-foreground mr-1">{selectedTickers.length} selected</span>
              <button onClick={handleBulkEnable} className="p-1 rounded hover:bg-emerald-500/20 text-emerald-400" title="Enable selected">
                <Power size={12} />
              </button>
              <button onClick={handleBulkDisable} className="p-1 rounded hover:bg-amber-500/20 text-amber-400" title="Disable selected">
                <PowerOff size={12} />
              </button>
              <button onClick={handleBulkDelete} className="p-1 rounded hover:bg-red-500/20 text-red-400" title="Delete selected">
                <Trash2 size={12} />
              </button>
              <button onClick={clearTickerSelection} className="p-1 rounded hover:bg-secondary text-muted-foreground" title="Clear selection">
                ×
              </button>
            </div>
          )}

          {/* Compact mode toggle */}
          <button
            onClick={() => setCompactMode(!compactMode)}
            className={`p-1.5 rounded-lg border transition-colors ${
              compactMode ? 'bg-primary/20 text-primary border-primary/30' : 'border-border text-muted-foreground hover:text-foreground'
            }`}
            title={compactMode ? 'Switch to full view' : 'Switch to compact view'}
          >
            {compactMode ? <LayoutGrid size={14} /> : <List size={14} />}
          </button>

          <span className="text-[10px] font-mono text-muted-foreground/50">
            double-click card to configure
          </span>
          <span className="text-[10px] font-mono text-muted-foreground">
            {activeTickers.length} active / {tickers.length} total
          </span>
          <div className={`h-2 w-2 rounded-full ${
            connected
              ? running ? 'bg-emerald-400 animate-pulse shadow-[0_0_6px_#34d399]' : 'bg-emerald-400'
              : 'bg-red-400 animate-ping'
          }`} />
        </div>
      </div>

      {/* Active tickers — drag and drop */}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        {activeTickers.length > 0 && (
          <section>
            <h2 className="text-sm font-semibold mb-4 flex items-center gap-2 text-foreground" data-testid="live-tickers-section">
              <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              Live Tickers
            </h2>
            <SortableContext items={activeSymbols} strategy={rectSortingStrategy}>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {activeTickers.map((t) => (
                  <div
                    key={t.symbol}
                    className={chartEnabled[t.symbol] ? 'col-span-1 md:col-span-2' : ''}
                  >
                    <TickerCard ticker={t} onConfigOpen={handleConfigOpen} />
                  </div>
                ))}
              </div>
            </SortableContext>
          </section>
        )}

        {/* Inactive tickers */}
        {inactiveTickers.length > 0 && (
          <section>
            <h2 className="text-sm font-semibold mb-4 text-muted-foreground" data-testid="inactive-tickers-section">
              Stored / Inactive
            </h2>
            <SortableContext items={inactiveSymbols} strategy={rectSortingStrategy}>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {inactiveTickers.map((t) => (
                  <div
                    key={t.symbol}
                    className={`${chartEnabled[t.symbol] ? 'col-span-1 md:col-span-2' : ''} opacity-60 hover:opacity-100 transition-opacity`}
                  >
                    <TickerCard ticker={t} onConfigOpen={handleConfigOpen} />
                  </div>
                ))}
              </div>
            </SortableContext>
          </section>
        )}
      </DndContext>

      {tickers.length === 0 && (
        <div className="flex flex-col items-center justify-center h-64 text-muted-foreground" data-testid="empty-watchlist">
          <p className="text-sm font-medium">No tickers yet</p>
          <p className="text-xs mt-1 text-muted-foreground/60">
            Click "Add Stock" to begin tracking your first symbol
          </p>
        </div>
      )}

      {/* Config modal */}
      {configTicker && (
        <ConfigModal ticker={configTicker} onClose={handleConfigClose} />
      )}
    </div>
  );
}
