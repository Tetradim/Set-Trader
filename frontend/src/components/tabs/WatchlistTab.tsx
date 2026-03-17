import { useState, useCallback } from 'react';
import { useStore, TickerConfig } from '@/stores/useStore';
import { TickerCard } from '../TickerCard';
import { ConfigModal } from '../ConfigModal';
import { Checkbox } from '@/components/ui/checkbox';
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

export function WatchlistTab() {
  const tickers = useStore((s) => Object.values(s.tickers));
  const running = useStore((s) => s.running);
  const connected = useStore((s) => s.connected);
  const simulate247 = useStore((s) => s.simulate247);
  const chartEnabled = useStore((s) => s.chartEnabled);
  const [configSymbol, setConfigSymbol] = useState<string | null>(null);

  // Sort tickers by sort_order
  const sorted = [...tickers].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
  const activeTickers = sorted.filter((t) => t.enabled);
  const inactiveTickers = sorted.filter((t) => !t.enabled);

  const configTicker = configSymbol ? tickers.find((t) => t.symbol === configSymbol) : null;

  const handleConfigOpen = useCallback((symbol: string) => {
    setConfigSymbol(symbol);
  }, []);

  const handleConfigClose = useCallback(() => {
    setConfigSymbol(null);
  }, []);

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

  return (
    <div className="space-y-8" data-testid="watchlist-tab">
      {/* Control bar */}
      <div className="flex items-center justify-between p-3 rounded-lg glass border border-border">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Checkbox
              data-testid="simulate-247-checkbox"
              checked={simulate247}
              onCheckedChange={(checked: boolean) => {
                useStore.getState().setSimulate247(checked as boolean);
              }}
            />
            <label className="text-xs text-muted-foreground cursor-pointer">Simulate 24/7</label>
          </div>
        </div>

        <div className="flex items-center gap-3">
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
