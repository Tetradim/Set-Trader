import React, { memo, useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { useStore, TickerConfig } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Switch } from '@/components/ui/switch';
import { apiFetch } from '@/lib/api';
import { AlertTriangle, Banknote, GripVertical, Pause, Play, Settings2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { getMarketMeta, formatPrice } from '@/lib/market-utils';
import { TunnelSVG } from './TunnelSVG';
import {
  buildTickerChartData,
  computeResizeState,
  getChartDomain,
  hasMeaningfulChartMovement,
  RESIZE_HANDLES,
  ResizeDirection,
  TICKER_CARD_MIN_HEIGHT,
  TICKER_CARD_MIN_WIDTH,
  TICKER_CARD_SNAP_GRID,
} from '@/lib/ticker-card-utils';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

interface Props {
  ticker: TickerConfig;
  onConfigOpen: (symbol: string) => void;
  tunnelColor: 'gold' | 'red' | 'amber' | 'blue';
  cardSheen: string;
}

export const TickerCard = memo(function TickerCard({ ticker, onConfigOpen, tunnelColor, cardSheen }: Props) {
  // Defensive: guard against undefined ticker
  if (!ticker || !ticker.symbol) {
    return null;
  }
  const { send }           = useWebSocket();
  const price              = useStore((s) => s.prices[ticker.symbol] ?? 0);
  const pnl                = useStore((s) => s.profits[ticker.symbol] ?? 0);
  const priceHistory       = useStore((s) => s.priceHistory[ticker.symbol] ?? []);
  const currencyDisplay    = useStore((s) => s.currencyDisplay);
  const fxRates            = useStore((s) => s.fxRates);

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmTP,     setConfirmTP]     = useState(false);
  const [quickEdit,     setQuickEdit]     = useState({ buy: false, sell: false, stop: false });
  const [editVals,      setEditVals]      = useState({ buy: ticker.buy_offset, sell: ticker.sell_offset, stop: ticker.stop_offset });
  const [cardSize, setCardSize] = useState({ width: 0, height: 0 });
  const resizeRef = useRef<HTMLDivElement>(null);
  const [isResizing, setIsResizing] = useState(false);

  useEffect(() => {
    setEditVals({ buy: ticker.buy_offset, sell: ticker.sell_offset, stop: ticker.stop_offset });
  }, [ticker.buy_offset, ticker.sell_offset, ticker.stop_offset]);

  const handleCardDoubleClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.closest('button, input, select, textarea, [role="button"]')) return;
    e.preventDefault();
    onConfigOpen(ticker.symbol);
  }, [onConfigOpen, ticker.symbol]);

  const handleResizeStart = useCallback((e: React.MouseEvent, direction: ResizeDirection) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);
    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = resizeRef.current?.offsetWidth || TICKER_CARD_MIN_WIDTH;
    const startHeight = resizeRef.current?.offsetHeight || TICKER_CARD_MIN_HEIGHT;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const nextSize = computeResizeState({
        direction,
        startWidth,
        startHeight,
        deltaX: moveEvent.clientX - startX,
        deltaY: moveEvent.clientY - startY,
        minWidth: TICKER_CARD_MIN_WIDTH,
        minHeight: TICKER_CARD_MIN_HEIGHT,
        snap: moveEvent.shiftKey,
        snapGrid: TICKER_CARD_SNAP_GRID,
      });

      setCardSize(nextSize);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, []);

  const handleResizeKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 25 : 10;
    if (!['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'].includes(e.key)) return;
    e.preventDefault();
    setCardSize((current) => {
      const width = current.width || resizeRef.current?.offsetWidth || 0;
      const height = current.height || resizeRef.current?.offsetHeight || 0;
      if (e.key === 'ArrowRight') return { width: Math.max(TICKER_CARD_MIN_WIDTH, width + step), height };
      if (e.key === 'ArrowLeft') return { width: Math.max(TICKER_CARD_MIN_WIDTH, width - step), height };
      if (e.key === 'ArrowDown') return { width, height: Math.max(TICKER_CARD_MIN_HEIGHT, height + step) };
      return { width, height: Math.max(TICKER_CARD_MIN_HEIGHT, height - step) };
    });
  }, []);

  const isActive   = ticker.enabled;
  const isPositive = pnl >= 0;
  const marketMeta = getMarketMeta(ticker);
  const primaryPrice = formatPrice(price, ticker, currencyDisplay, fxRates);

  // Card active class
  const cardClass = [
    'sp-ticker-card',
    isActive && isPositive ? 'active' : '',
    isActive && !isPositive ? 'negative' : '',
    !isActive ? 'paused' : '',
  ].filter(Boolean).join(' ');

  const handleDelete = () => {
    if (!confirmDelete) { setConfirmDelete(true); setTimeout(() => setConfirmDelete(false), 4000); return; }
    send('DELETE_TICKER', { symbol: ticker.symbol });
  };

  const handleTakeProfit = () => {
    if (!confirmTP) { setConfirmTP(true); setTimeout(() => setConfirmTP(false), 4000); return; }
    send('TAKE_PROFIT', { symbol: ticker.symbol });
    setConfirmTP(false);
    toast.success(`Took profit for ${ticker.symbol}: $${pnl.toFixed(2)}`);
  };

  const handleDuplicate = async () => {
    try {
      const allTickers = useStore.getState().tickers;
      const newSymbol  = `${ticker.symbol}_COPY`;
      const newTicker  = { ...ticker, symbol: newSymbol, sort_order: Object.keys(allTickers).length };
      delete (newTicker as any)._id;
      await apiFetch('/api/tickers', { method: 'POST', body: JSON.stringify(newTicker) });
      toast.success(`Duplicated as ${newSymbol}`);
    } catch { toast.error('Failed to duplicate'); }
  };

  const saveQuickEdit = (field: string, value: number) => {
    send('UPDATE_TICKER', { symbol: ticker.symbol, [field]: value });
    setQuickEdit({ buy: false, sell: false, stop: false });
    toast.success(`${field} → ${value}`);
  };

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: ticker.symbol });

  const dndStyle: React.CSSProperties = {
    transform:  CSS.Transform.toString(transform),
    transition,
    opacity:    isDragging ? 0.4 : isActive ? 1 : 0.6,
    zIndex:     isDragging ? 50 : undefined,
  };

  const sparkColor = isPositive ? '#2dd4a0' : '#e03040';

  const chartData = useMemo(() => buildTickerChartData(priceHistory, price), [priceHistory, price]);
  const chartDomain = useMemo(() => getChartDomain(chartData), [chartData]);
  const hasChartMovement = useMemo(() => hasMeaningfulChartMovement(chartData), [chartData]);

  // Sheen class based on mode
  const modeSheen = (() => {
    if (!isActive) return 'sp-sheen-amber';
    if (ticker.strategy === 'paper') return 'sp-sheen-blue';
    if (!isPositive) return 'sp-sheen-red';
    return cardSheen;
  })();

  const modeLabel = !isActive ? 'PAUSED' : ticker.strategy === 'paper' ? 'PAPER' : 'LIVE';
  const modeClass = !isActive ? 'sp-mode-paused' : ticker.strategy === 'paper' ? 'sp-mode-paper' : 'sp-mode-live';
  const chartGradientId = `chartGrad-${ticker.symbol.replace(/[^a-zA-Z0-9_-]/g, '-')}`;

  return (
    <div
      ref={(el) => {
        setNodeRef(el);
        if (el) resizeRef.current = el;
      }}
      style={{
        ...dndStyle,
        ...(cardSize.width > 0 ? { width: cardSize.width, minWidth: cardSize.width } : {}),
        ...(cardSize.height > 0 ? { height: cardSize.height, minHeight: cardSize.height } : {}),
      }}
      className={`${cardClass} ${isResizing ? 'resizing' : ''}`}
      data-testid={`ticker-card-${ticker.symbol}`}
      onDoubleClick={handleCardDoubleClick}
    >
      {/* Sci-fi tunnel background */}
      <div className="sp-ticker-tunnel">
        <TunnelSVG color={tunnelColor} />
      </div>

      {/* Auto-stopped banner */}
      {ticker.auto_stopped && (
        <div style={{ position:'relative', zIndex:6, background:'rgba(240,80,96,0.12)', borderBottom:'1px solid rgba(240,80,96,0.2)', padding:'3px 10px', fontSize:9, letterSpacing:'.12em', color:'#f05060', fontFamily:"'JetBrains Mono',monospace", textTransform:'uppercase' }}>
          <AlertTriangle size={10} aria-hidden="true" style={{ display: 'inline', marginRight: 4, verticalAlign: '-1px' }} />
          Auto-stopped — {ticker.auto_stop_reason || 'Risk limit hit'}
        </div>
      )}

      {/* Title bar */}
      <div className={`sp-ticker-titlebar ${modeSheen}`}>
        <button
          {...attributes}
          {...listeners}
          type="button"
          style={{ background:'none', border:'none', cursor:'grab', color:'rgba(200,145,10,0.25)', padding:0, display:'flex', alignItems:'center', position:'relative', zIndex:1 }}
          aria-label={`Drag ${ticker.symbol} card`}
          data-testid={`drag-handle-${ticker.symbol}`}
        >
          <GripVertical size={13} />
        </button>

        <span className="sp-ticker-sym">
          {marketMeta.currency !== 'USD' && <span style={{ marginRight: 4 }}>{marketMeta.flag}</span>}
          {ticker.symbol}
        </span>

        <span className={`sp-ticker-mode ${modeClass}`}>{modeLabel}</span>

        {ticker.trailing_enabled && (
          <span style={{ fontSize:7, fontWeight:700, letterSpacing:'.12em', textTransform:'uppercase', padding:'2px 5px', borderRadius:3, background:'rgba(220,168,40,0.1)', color:'#dca828', border:'1px solid rgba(220,168,40,0.22)', fontFamily:"'JetBrains Mono',monospace", position:'relative', zIndex:1 }}>
            TRAIL
          </span>
        )}
      </div>

      {/* Body */}
      <div className="sp-ticker-body">
        {/* Price */}
        <div className="sp-price-row">
          <div className="sp-price">{primaryPrice}</div>
          {pnl !== 0 && (
            <div className={`sp-price-chg ${pnl >= 0 ? 'up' : 'dn'}`}>
              {pnl >= 0 ? '+' : ''}${Math.abs(pnl).toFixed(2)}
            </div>
          )}
        </div>

        <div className={`sp-chart-container ${hasChartMovement ? '' : 'flat'}`}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
              <defs>
                <linearGradient id={chartGradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={sparkColor} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={sparkColor} stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <XAxis dataKey="time" hide />
              <YAxis domain={chartDomain} hide />
              <Tooltip
                contentStyle={{
                  background: '#1a1a24',
                  border: '1px solid rgba(220,168,40,0.3)',
                  borderRadius: 4,
                  fontSize: 11,
                }}
                labelStyle={{ display: 'none' }}
                formatter={(value: number) => [`$${value.toFixed(2)}`, 'Price']}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke={sparkColor}
                strokeWidth={1.5}
                fill={`url(#${chartGradientId})`}
                isAnimationActive={false}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
          {!hasChartMovement && (
            <div className="sp-chart-flat-label">Live trace pending</div>
          )}
        </div>

        {/* Buy / Sell brackets — quick editable */}
        <div className="sp-bracket-row">
          <div>
            <div className="sp-bracket-lbl">Buy</div>
            {quickEdit.buy ? (
              <div style={{ display:'flex', alignItems:'center', gap:3 }}>
                <input aria-label={`Buy offset for ${ticker.symbol}`} type="number" value={editVals.buy} onChange={(e) => setEditVals(v => ({ ...v, buy: parseFloat(e.target.value)||0 }))} style={{ width:52, padding:'1px 4px', background:'#1c1c24', border:'1px solid rgba(220,168,40,0.3)', borderRadius:3, fontSize:11, fontFamily:"'JetBrains Mono',monospace", color:'#f0ead6' }} autoFocus />
                <button type="button" aria-label={`Save buy offset for ${ticker.symbol}`} onClick={() => saveQuickEdit('buy_offset', editVals.buy)} style={{ color:'#dca828', background:'none', border:'none', cursor:'pointer', fontSize:11 }}>✓</button>
                <button type="button" aria-label={`Cancel buy offset edit for ${ticker.symbol}`} onClick={() => setQuickEdit(v => ({ ...v, buy:false }))} style={{ color:'rgba(255,255,255,0.3)', background:'none', border:'none', cursor:'pointer', fontSize:13 }}>×</button>
              </div>
            ) : (
              <button type="button" aria-label={`Edit buy offset for ${ticker.symbol}`} className="sp-bracket-val buy" style={{ background:'none', border:'none', cursor:'pointer', padding:0 }} onClick={() => setQuickEdit(v => ({ ...v, buy:true }))}>
                {ticker.buy_percent ? `${ticker.buy_offset}%` : `$${ticker.buy_offset}`}
              </button>
            )}
          </div>
          <div>
            <div className="sp-bracket-lbl">Sell</div>
            {quickEdit.sell ? (
              <div style={{ display:'flex', alignItems:'center', gap:3 }}>
                <input aria-label={`Sell offset for ${ticker.symbol}`} type="number" value={editVals.sell} onChange={(e) => setEditVals(v => ({ ...v, sell: parseFloat(e.target.value)||0 }))} style={{ width:52, padding:'1px 4px', background:'#1c1c24', border:'1px solid rgba(220,168,40,0.3)', borderRadius:3, fontSize:11, fontFamily:"'JetBrains Mono',monospace", color:'#f0ead6' }} autoFocus />
                <button type="button" aria-label={`Save sell offset for ${ticker.symbol}`} onClick={() => saveQuickEdit('sell_offset', editVals.sell)} style={{ color:'#dca828', background:'none', border:'none', cursor:'pointer', fontSize:11 }}>✓</button>
                <button type="button" aria-label={`Cancel sell offset edit for ${ticker.symbol}`} onClick={() => setQuickEdit(v => ({ ...v, sell:false }))} style={{ color:'rgba(255,255,255,0.3)', background:'none', border:'none', cursor:'pointer', fontSize:13 }}>×</button>
              </div>
            ) : (
              <button type="button" aria-label={`Edit sell offset for ${ticker.symbol}`} className="sp-bracket-val sell" style={{ background:'none', border:'none', cursor:'pointer', padding:0 }} onClick={() => setQuickEdit(v => ({ ...v, sell:true }))}>
                {ticker.sell_percent ? `${ticker.sell_offset}%` : `$${ticker.sell_offset}`}
              </button>
            )}
          </div>
        </div>

        {/* P&L bar */}
        <div className="sp-pnl-bar">
          <div
            className={`sp-pnl-fill ${isPositive ? 'pos' : 'neg'}`}
            style={{ width: `${Math.min(Math.abs(pnl) / (ticker.base_power || 100) * 100, 100)}%` }}
          />
        </div>
      </div>

      {/* Footer */}
      <div className="sp-ticker-footer">
        <div className={`sp-pnl-val ${pnl >= 0 ? 'pos' : 'neg'}`}>
          {pnl >= 0 ? '+' : ''}${Math.abs(pnl).toFixed(2)}
        </div>
        <div className="sp-card-btns">
          <button type="button" className="sp-card-btn" title="Configure" aria-label={`Configure ${ticker.symbol}`} onClick={() => onConfigOpen(ticker.symbol)}>
            <Settings2 size={11} />
          </button>
          <button
            type="button"
            className="sp-card-btn"
            aria-label={`${isActive ? 'Pause' : 'Resume'} ${ticker.symbol}`}
            title={isActive ? 'Pause' : 'Resume'}
            onClick={() => send('UPDATE_TICKER', { symbol: ticker.symbol, enabled: !isActive })}
          >
            {isActive
              ? <Pause size={11} aria-hidden="true" />
              : <Play size={11} aria-hidden="true" />
            }
          </button>
          {pnl !== 0 && (
            <button
              type="button"
              className="sp-card-btn"
              aria-label={confirmTP ? `Confirm take profit for ${ticker.symbol}` : `Take profit for ${ticker.symbol}`}
              title={confirmTP ? `Take $${pnl.toFixed(2)}?` : 'Take Profit'}
              onClick={handleTakeProfit}
              style={confirmTP ? { color:'#dca828', borderColor:'rgba(220,168,40,0.4)' } : {}}
            >
              <Banknote size={11} />
            </button>
          )}
          <button
            type="button"
            className="sp-card-btn"
            aria-label={confirmDelete ? `Confirm remove ${ticker.symbol}` : `Remove ${ticker.symbol}`}
            title={confirmDelete ? 'Confirm?' : 'Remove'}
            onClick={handleDelete}
            style={confirmDelete ? { color:'#f05060', borderColor:'rgba(240,80,96,0.35)' } : {}}
          >
            <Trash2 size={11} />
          </button>
        </div>
      </div>

      {RESIZE_HANDLES.map((handle) => (
        <div
          key={handle.direction}
          className={handle.className}
          role="separator"
          aria-label={`${handle.label} ${ticker.symbol}`}
          onMouseDown={(e) => handleResizeStart(e, handle.direction)}
        />
      ))}
      
      {/* Keyboard accessible resize handle (alternative) */}
      <div
        className="sp-resize-handle-keyboard"
        role="separator"
        tabIndex={0}
        aria-label={`Resize ${ticker.symbol} card. Use arrow keys to resize.`}
        onKeyDown={handleResizeKeyDown}
        style={{ position: 'absolute', right: 4, bottom: 4, width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
      />
    </div>
  );
});
