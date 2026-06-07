import { Banknote, Pause, Play, RotateCcw, Settings2, Trash2 } from 'lucide-react';

interface TickerCardFooterProps {
  symbol: string;
  pnl: number;
  isActive: boolean;
  confirmTakeProfit: boolean;
  confirmDelete: boolean;
  hasCustomSize: boolean;
  onConfigOpen: (symbol: string) => void;
  onToggleEnabled: () => void;
  onTakeProfit: () => void;
  onDelete: () => void;
  onResetSize: () => void;
}

export function TickerCardFooter({
  symbol,
  pnl,
  isActive,
  confirmTakeProfit,
  confirmDelete,
  hasCustomSize,
  onConfigOpen,
  onToggleEnabled,
  onTakeProfit,
  onDelete,
  onResetSize,
}: TickerCardFooterProps) {
  return (
    <div className="sp-ticker-footer">
      <div className={`sp-pnl-val ${pnl >= 0 ? 'pos' : 'neg'}`}>
        {pnl >= 0 ? '+' : ''}${Math.abs(pnl).toFixed(2)}
      </div>
      <div className="sp-card-btns">
        <button type="button" className="sp-card-btn" title="Configure" aria-label={`Configure ${symbol}`} onClick={() => onConfigOpen(symbol)}>
          <Settings2 size={11} />
        </button>
        {hasCustomSize && (
          <button
            type="button"
            className="sp-card-btn"
            aria-label={`Reset ${symbol} card size`}
            title="Reset size"
            onClick={onResetSize}
          >
            <RotateCcw size={11} />
          </button>
        )}
        <button
          type="button"
          className="sp-card-btn"
          aria-label={`${isActive ? 'Pause' : 'Resume'} ${symbol}`}
          title={isActive ? 'Pause' : 'Resume'}
          onClick={onToggleEnabled}
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
            aria-label={confirmTakeProfit ? `Confirm take profit for ${symbol}` : `Take profit for ${symbol}`}
            title={confirmTakeProfit ? `Take $${pnl.toFixed(2)}?` : 'Take Profit'}
            onClick={onTakeProfit}
            style={confirmTakeProfit ? { color:'#dca828', borderColor:'rgba(220,168,40,0.4)' } : {}}
          >
            <Banknote size={11} />
          </button>
        )}
        <button
          type="button"
          className="sp-card-btn"
          aria-label={confirmDelete ? `Confirm remove ${symbol}` : `Remove ${symbol}`}
          title={confirmDelete ? 'Confirm?' : 'Remove'}
          onClick={onDelete}
          style={confirmDelete ? { color:'#f05060', borderColor:'rgba(240,80,96,0.35)' } : {}}
        >
          <Trash2 size={11} />
        </button>
      </div>
    </div>
  );
}
