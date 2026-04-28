import React, { memo, useState, useCallback, useEffect } from 'react';
import { useStore, TickerConfig } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import { apiFetch } from '@/lib/api';
import {
  Trash2,
  TrendingUp,
  TrendingDown,
  Zap,
  ShieldAlert,
  Banknote,
  GripVertical,
  Settings2,
  Plug,
  Copy,
  Palette,
} from 'lucide-react';
import { toast } from 'sonner';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { getMarketMeta, formatPrice, formatPriceSecondary } from '@/lib/market-utils';

interface Props {
  ticker: TickerConfig;
  onConfigOpen: (symbol: string) => void;
}

interface BrokerOption {
  id: string;
  name: string;
  color: string;
  supported: boolean;
}

let _brokerPromise: Promise<BrokerOption[]> | null = null;

function fetchBrokers(): Promise<BrokerOption[]> {
  if (!_brokerPromise) {
    _brokerPromise = apiFetch('/api/brokers')
      .then((data: any[]) => data.filter(b => b.supported).map(b => ({ id: b.id, name: b.name, color: b.color, supported: b.supported })))
      .catch(() => [] as BrokerOption[]);
  }
  return _brokerPromise;
}

const CARD_COLORS = [
  '#6366f1',
  '#10b981',
  '#f59e0b',
  '#f43f5e',
  '#8b5cf6',
  '#06b6d4',
  '#ec4899',
  '#84cc16',
  '#f97316',
  '#64748b',
];

export const TickerCard = memo(function TickerCard({ ticker, onConfigOpen }: Props) {
  const { send } = useWebSocket();
  const price = useStore((s) => s.prices[ticker.symbol] ?? 0);
  const pnl = useStore((s) => s.profits[ticker.symbol] ?? 0);
  const position = useStore((s) => s.positions[ticker.symbol]);
  const currencyDisplay = useStore((s) => s.currencyDisplay);
  const fxRates = useStore((s) => s.fxRates);
  const compactMode = useStore((s) => s.compactMode);
  const tickerColors = useStore((s) => s.tickerColors);
  const selectedTickers = useStore((s) => s.selectedTickers);
  const toggleTickerSelection = useStore((s) => s.toggleTickerSelection);
  const setTickerColor = useStore((s) => s.setTickerColor);

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmTP, setConfirmTP] = useState(false);
  const [brokers, setBrokers] = useState<BrokerOption[]>([]);
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [quickEdit, setQuickEdit] = useState({ buy: false, sell: false, stop: false });
  const [editValues, setEditValues] = useState({
    buy_offset: ticker.buy_offset,
    sell_offset: ticker.sell_offset,
    stop_offset: ticker.stop_offset,
  });

  useEffect(() => {
    fetchBrokers().then(setBrokers);
  }, []);

  useEffect(() => {
    setEditValues({
      buy_offset: ticker.buy_offset,
      sell_offset: ticker.sell_offset,
      stop_offset: ticker.stop_offset,
    });
  }, [ticker.buy_offset, ticker.sell_offset, ticker.stop_offset]);

  const marketMeta = getMarketMeta(ticker);
  const isNonUS = marketMeta.currency !== 'USD';
  const primaryPrice = formatPrice(price, ticker, currencyDisplay, fxRates);

  const handleBrokerToggle = useCallback((brokerId: string) => {
    const current = ticker.broker_ids || [];
    const updated = current.includes(brokerId)
      ? current.filter(id => id !== brokerId)
      : [...current, brokerId];
    send('UPDATE_TICKER', { symbol: ticker.symbol, broker_ids: updated });
  }, [send, ticker.symbol, ticker.broker_ids]);

  const selectedBrokers = brokers.filter(b => (ticker.broker_ids || []).includes(b.id));
  const failedBrokers = useStore((s) => s.failedBrokers);

  const isPositive = pnl >= 0;
  const isActive = ticker.enabled;
  const isSelected = selectedTickers.includes(ticker.symbol);
  const cardColor = tickerColors[ticker.symbol] || CARD_COLORS[0];

  const handleDelete = () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 4000);
      return;
    }
    send('DELETE_TICKER', { symbol: ticker.symbol });
  };

  const hasPosition = position && position.quantity > 0;

  const handleTakeProfit = () => {
    if (!confirmTP) {
      setConfirmTP(true);
      setTimeout(() => setConfirmTP(false), 4000);
      return;
    }
    send('TAKE_PROFIT', { symbol: ticker.symbol });
    setConfirmTP(false);
    toast.success(`Took profit for ${ticker.symbol}: $${pnl.toFixed(2)} moved to cash`);
  };

  const handleDuplicate = async () => {
    try {
      const allTickers = useStore.getState().tickers;
      const newSymbol = `${ticker.symbol}_COPY`;
      const newTicker = {
        ...ticker,
        symbol: newSymbol,
        sort_order: Object.keys(allTickers).length,
      };
      delete (newTicker as any)._id;
      await apiFetch('/api/tickers', {
        method: 'POST',
        body: JSON.stringify(newTicker),
      });
      toast.success(`Duplicated ${ticker.symbol} as ${newSymbol}`);
    } catch {
      toast.error('Failed to duplicate ticker');
    }
  };

  const saveQuickEdit = (field: string, value: number) => {
    send('UPDATE_TICKER', { symbol: ticker.symbol, [field]: value });
    setQuickEdit({ buy: false, sell: false, stop: false });
    toast.success(`${field} updated to ${value}`);
  };

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: ticker.symbol });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 50 : 'auto',
    '--card-accent': cardColor,
  } as React.CSSProperties;

  // Compact view
  if (compactMode) {
    return (
      <div
        ref={setNodeRef}
        style={style}
        data-testid={`ticker-card-${ticker.symbol}`}
        className={`
          relative overflow-hidden rounded-lg border transition-all duration-200
          ${isActive ? 'border-l-4' : 'border-border opacity-60'}
          ${isSelected ? 'ring-2 ring-primary' : ''}
          glass hover:border-primary/40 cursor-pointer
        `}
        style={{ ...style, borderLeftColor: isActive ? cardColor : undefined }}
        onClick={() => toggleTickerSelection(ticker.symbol)}
      >
        <div className="flex items-center justify-between p-2">
          <div className="flex items-center gap-2">
            <Checkbox
              checked={isSelected}
              onCheckedChange={() => {}}
              className="h-3 w-3"
            />
            <span className={`font-bold text-sm ${ticker.auto_stopped ? 'text-red-500' : 'text-foreground'}`}>
              {ticker.symbol}
            </span>
            <span className="text-muted-foreground text-xs">{primaryPrice}</span>
          </div>
          <div className="flex items-center gap-2">
            {pnl !== 0 && (
              <span className={`text-xs font-mono font-bold ${pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
              </span>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); onConfigOpen(ticker.symbol); }}
              className="p-1 text-muted-foreground hover:text-foreground"
            >
              <Settings2 size={12} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Full view
  return (
    <div
      ref={setNodeRef}
      style={style}
      data-testid={`ticker-card-${ticker.symbol}`}
      className={`
        relative overflow-hidden rounded-xl border transition-all duration-300
        ${isActive
          ? isPositive
            ? 'border-emerald-500/30 glow-success'
            : 'border-red-500/30 glow-danger'
          : 'border-border opacity-60'
        }
        ${isSelected ? 'ring-2 ring-primary ring-offset-2 ring-offset-background' : ''}
        glass hover:border-primary/40
      `}
      onDoubleClick={() => onConfigOpen(ticker.symbol)}
    >
      {isActive && (
        <div className={`absolute -right-8 -top-8 h-24 w-24 rounded-full blur-3xl opacity-20 ${
          isPositive ? 'bg-emerald-500' : 'bg-red-500'
        }`} />
      )}

      <div className="relative p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <button
              {...attributes}
              {...listeners}
              className="cursor-grab active:cursor-grabbing text-muted-foreground/40 hover:text-muted-foreground"
              data-testid={`drag-handle-${ticker.symbol}`}
            >
              <GripVertical size={14} />
            </button>

            <Checkbox
              checked={isSelected}
              onCheckedChange={() => toggleTickerSelection(ticker.symbol)}
              className="h-3.5 w-3.5"
            />

            <h3 className={`text-lg font-bold ${ticker.auto_stopped ? 'text-red-500 animate-pulse' : 'text-foreground'}`}>
              {isNonUS && <span className="mr-1">{marketMeta.flag}</span>}
              {ticker.symbol}
            </h3>

            {ticker.auto_stopped && (
              <span className="text-[9px] font-bold uppercase px-1.5 py-0.5 rounded bg-red-500/20 text-red-500">
                AUTO-STOPPED
              </span>
            )}
            <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
              isActive ? 'bg-primary/20 text-primary' : 'bg-secondary text-muted-foreground'
            }`}>
              {isActive ? 'LIVE' : 'OFF'}
            </span>
            {ticker.trailing_enabled && (
              <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-accent/20 text-accent">TRAIL</span>
            )}
          </div>

          <div className="flex items-center gap-1">
            <div className="relative">
              <button
                onClick={() => setShowColorPicker(!showColorPicker)}
                className="p-1.5 rounded hover:bg-secondary"
                title="Card color"
              >
                <Palette size={12} style={{ color: cardColor }} />
              </button>
              {showColorPicker && (
                <div className="absolute right-0 top-full mt-1 p-2 bg-card border border-border rounded-lg shadow-lg z-50">
                  <div className="grid grid-cols-5 gap-1">
                    {CARD_COLORS.map((color) => (
                      <button
                        key={color}
                        onClick={() => { setTickerColor(ticker.symbol, color); setShowColorPicker(false); }}
                        className={`w-5 h-5 rounded-full border-2 ${cardColor === color ? 'border-white' : 'border-transparent'}`}
                        style={{ backgroundColor: color }}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>

            <button
              onClick={handleDuplicate}
              className="p-1.5 rounded hover:bg-secondary"
              title="Duplicate ticker"
            >
              <Copy size={12} className="text-muted-foreground" />
            </button>

            <Switch
              checked={isActive}
              onCheckedChange={(checked) => send('UPDATE_TICKER', { symbol: ticker.symbol, enabled: checked })}
              className="h-4 w-7"
            />
          </div>
        </div>

        {/* Price & P&L */}
        <div className="flex items-end justify-between mb-2">
          <div>
            <div className="text-2xl font-bold text-foreground font-mono">
              {primaryPrice}
            </div>
          </div>
          {pnl !== 0 && (
            <div className="text-right">
              <div className={`text-lg font-bold font-mono ${pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {pnl >= 0 ? '+' : ''}{formatPrice(Math.abs(pnl), ticker, currencyDisplay, fxRates)}
              </div>
              <div className="text-xs text-muted-foreground">P&L</div>
            </div>
          )}
        </div>

        {/* Position */}
        {position && position.quantity > 0 && (
          <div className="mt-2 px-2 py-1 rounded bg-primary/10 border border-primary/20 text-xs font-mono">
            <span className="text-muted-foreground">Holding: </span>
            <span className="font-bold">{position.quantity.toFixed(4)}</span>
            <span className="text-muted-foreground"> @ </span>
            <span>{formatPrice(position.avg_entry, ticker, currencyDisplay, fxRates)}</span>
            <span className={`ml-2 font-bold ${position.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {position.unrealized_pnl >= 0 ? '+' : ''}{formatPrice(Math.abs(position.unrealized_pnl), ticker, currencyDisplay, fxRates)}
            </span>
          </div>
        )}

        {/* Quick Edit */}
        <div className="mt-3 pt-2 border-t border-border/50">
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1">
              <TrendingDown size={10} className="text-emerald-400" />
              <span className="text-muted-foreground w-8">Buy:</span>
              {quickEdit.buy ? (
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={editValues.buy_offset}
                    onChange={(e) => setEditValues({ ...editValues, buy_offset: parseFloat(e.target.value) || 0 })}
                    className="w-16 px-1 py-0.5 bg-secondary border rounded text-xs"
                    autoFocus
                  />
                  <button onClick={() => saveQuickEdit('buy_offset', editValues.buy_offset)}><Zap size={10} /></button>
                  <button onClick={() => setQuickEdit({ ...quickEdit, buy: false })}>×</button>
                </div>
              ) : (
                <button onClick={() => setQuickEdit({ ...quickEdit, buy: true })} className="font-mono hover:text-emerald-400">
                  {ticker.buy_percent ? `${ticker.buy_offset}%` : `$${ticker.buy_offset}`}
                </button>
              )}
            </div>

            <div className="flex items-center gap-1">
              <TrendingUp size={10} className="text-blue-400" />
              <span className="text-muted-foreground w-8">Sell:</span>
              {quickEdit.sell ? (
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={editValues.sell_offset}
                    onChange={(e) => setEditValues({ ...editValues, sell_offset: parseFloat(e.target.value) || 0 })}
                    className="w-16 px-1 py-0.5 bg-secondary border rounded text-xs"
                  />
                  <button onClick={() => saveQuickEdit('sell_offset', editValues.sell_offset)}><Zap size={10} /></button>
                  <button onClick={() => setQuickEdit({ ...quickEdit, sell: false })}>×</button>
                </div>
              ) : (
                <button onClick={() => setQuickEdit({ ...quickEdit, sell: true })} className="font-mono hover:text-blue-400">
                  {ticker.sell_percent ? `${ticker.sell_offset}%` : `$${ticker.sell_offset}`}
                </button>
              )}
            </div>

            <div className="flex items-center gap-1">
              <Zap size={10} className="text-red-400" />
              <span className="text-muted-foreground w-8">Stop:</span>
              {quickEdit.stop ? (
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={editValues.stop_offset}
                    onChange={(e) => setEditValues({ ...editValues, stop_offset: parseFloat(e.target.value) || 0 })}
                    className="w-16 px-1 py-0.5 bg-secondary border rounded text-xs"
                  />
                  <button onClick={() => saveQuickEdit('stop_offset', editValues.stop_offset)}><Zap size={10} /></button>
                  <button onClick={() => setQuickEdit({ ...quickEdit, stop: false })}>×</button>
                </div>
              ) : (
                <button onClick={() => setQuickEdit({ ...quickEdit, stop: true })} className="font-mono hover:text-red-400">
                  {ticker.stop_percent ? `${ticker.stop_offset}%` : `$${ticker.stop_offset}`}
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center justify-between mt-3">
          <button
            onClick={() => onConfigOpen(ticker.symbol)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <Settings2 size={14} />
            Configure
          </button>

          <div className="flex items-center gap-3">
            {pnl !== 0 && (
              <button
                onClick={handleTakeProfit}
                className={`flex items-center gap-1 text-xs ${confirmTP ? 'text-amber-400 font-bold animate-pulse' : 'text-emerald-400 hover:text-emerald-300'}`}
              >
                <Banknote size={12} />
                {confirmTP ? `Take $${pnl.toFixed(2)}?` : 'Take Profit'}
              </button>
            )}

            <button
              onClick={handleDelete}
              className={`flex items-center gap-1 text-xs ${confirmDelete ? 'text-red-400 font-bold animate-pulse' : 'text-muted-foreground hover:text-red-400'}`}
            >
              <Trash2 size={12} />
              {confirmDelete ? (hasPosition ? 'Delete with position?' : 'Confirm delete?') : 'Remove'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});
