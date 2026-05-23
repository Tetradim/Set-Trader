import React, { memo, useState, useCallback, useEffect, useRef } from 'react';
import { useStore, TickerConfig } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { apiFetch } from '@/lib/api';
import { toast } from 'sonner';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { getMarketMeta, formatPrice } from '@/lib/market-utils';
import { TunnelSVG } from './TunnelSVG';
import {
  computeResizeState,
  ResizeDirection,
  TICKER_CARD_MIN_HEIGHT,
  TICKER_CARD_MIN_WIDTH,
  TICKER_CARD_SNAP_GRID,
} from '@/lib/ticker-card-utils';
import { TickerSparkline } from './ticker-card/TickerSparkline';
import { TickerQuickBrackets } from './ticker-card/TickerQuickBrackets';
import { TickerResizeHandles } from './ticker-card/TickerResizeHandles';
import { TickerCardFooter } from './ticker-card/TickerCardFooter';
import { TickerCardHeader } from './ticker-card/TickerCardHeader';

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

  // Sheen class based on mode
  const modeSheen = (() => {
    if (!isActive) return 'sp-sheen-amber';
    if (ticker.strategy === 'paper') return 'sp-sheen-blue';
    if (!isPositive) return 'sp-sheen-red';
    return cardSheen;
  })();

  const modeLabel = !isActive ? 'PAUSED' : ticker.strategy === 'paper' ? 'PAPER' : 'LIVE';
  const modeClass = !isActive ? 'sp-mode-paused' : ticker.strategy === 'paper' ? 'sp-mode-paper' : 'sp-mode-live';

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

      <TickerCardHeader
        ticker={ticker}
        marketMeta={marketMeta}
        modeSheen={modeSheen}
        modeLabel={modeLabel}
        modeClass={modeClass}
        dragAttributes={attributes}
        dragListeners={listeners}
      />
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

        <TickerSparkline
          symbol={ticker.symbol}
          price={price}
          priceHistory={priceHistory}
          isPositive={isPositive}
        />

        {/* Buy / Sell brackets - quick editable */}
        <TickerQuickBrackets
          ticker={ticker}
          quickEdit={quickEdit}
          editVals={editVals}
          setQuickEdit={setQuickEdit}
          setEditVals={setEditVals}
          saveQuickEdit={saveQuickEdit}
        />
        {/* P&L bar */}
        <div className="sp-pnl-bar">
          <div
            className={`sp-pnl-fill ${isPositive ? 'pos' : 'neg'}`}
            style={{ width: `${Math.min(Math.abs(pnl) / (ticker.base_power || 100) * 100, 100)}%` }}
          />
        </div>
      </div>

      <TickerCardFooter
        symbol={ticker.symbol}
        pnl={pnl}
        isActive={isActive}
        confirmTakeProfit={confirmTP}
        confirmDelete={confirmDelete}
        onConfigOpen={onConfigOpen}
        onToggleEnabled={() => send('UPDATE_TICKER', { symbol: ticker.symbol, enabled: !isActive })}
        onTakeProfit={handleTakeProfit}
        onDelete={handleDelete}
      />

      <TickerResizeHandles
        symbol={ticker.symbol}
        onResizeStart={handleResizeStart}
        onResizeKeyDown={handleResizeKeyDown}
      />
    </div>
  );
});
