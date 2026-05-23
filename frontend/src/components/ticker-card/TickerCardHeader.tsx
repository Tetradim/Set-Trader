import { AlertTriangle, GripVertical } from 'lucide-react';
import type { TickerConfig } from '@/stores/useStore';
import type { getMarketMeta } from '@/lib/market-utils';

type MarketMeta = ReturnType<typeof getMarketMeta>;

interface TickerCardHeaderProps {
  ticker: TickerConfig;
  marketMeta: MarketMeta;
  modeSheen: string;
  modeLabel: string;
  modeClass: string;
  dragAttributes: Record<string, unknown>;
  dragListeners?: Record<string, unknown>;
}

export function TickerCardHeader({
  ticker,
  marketMeta,
  modeSheen,
  modeLabel,
  modeClass,
  dragAttributes,
  dragListeners,
}: TickerCardHeaderProps) {
  return (
    <>
      {ticker.auto_stopped && (
        <div style={{ position:'relative', zIndex:6, background:'rgba(240,80,96,0.12)', borderBottom:'1px solid rgba(240,80,96,0.2)', padding:'3px 10px', fontSize:9, letterSpacing:'.12em', color:'#f05060', fontFamily:"'JetBrains Mono',monospace", textTransform:'uppercase' }}>
          <AlertTriangle size={10} aria-hidden="true" style={{ display: 'inline', marginRight: 4, verticalAlign: '-1px' }} />
          Auto-stopped - {ticker.auto_stop_reason || 'Risk limit hit'}
        </div>
      )}

      <div className={`sp-ticker-titlebar ${modeSheen}`}>
        <button
          {...dragAttributes}
          {...dragListeners}
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
    </>
  );
}
