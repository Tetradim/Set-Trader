import type { Dispatch, SetStateAction } from 'react';
import type { TickerConfig } from '@/stores/useStore';

type QuickEditState = { buy: boolean; sell: boolean; stop: boolean };
type QuickEditValues = { buy: number; sell: number; stop: number };

interface TickerQuickBracketsProps {
  ticker: TickerConfig;
  quickEdit: QuickEditState;
  editVals: QuickEditValues;
  setQuickEdit: Dispatch<SetStateAction<QuickEditState>>;
  setEditVals: Dispatch<SetStateAction<QuickEditValues>>;
  saveQuickEdit: (field: string, value: number) => void;
}

export function TickerQuickBrackets({
  ticker,
  quickEdit,
  editVals,
  setQuickEdit,
  setEditVals,
  saveQuickEdit,
}: TickerQuickBracketsProps) {
  return (
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
  );
}
