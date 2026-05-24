import { TickerConfig } from '@/stores/useStore';
import { Checkbox } from '@/components/ui/checkbox';

/* ============ Partial Fills Tab ============ */

interface Leg {
  alloc_pct: number;
  offset: number;
  is_percent: boolean;
}

const DEFAULT_BUY_LEGS: Leg[] = [
  { alloc_pct: 50, offset: -3.0, is_percent: true },
  { alloc_pct: 30, offset: -5.0, is_percent: true },
  { alloc_pct: 20, offset: -7.0, is_percent: true },
];

const DEFAULT_SELL_LEGS: Leg[] = [
  { alloc_pct: 50, offset: 3.0, is_percent: true },
  { alloc_pct: 50, offset: 6.0, is_percent: true },
];

export function PartialFillsTab({ ticker, send }: { ticker: TickerConfig; send: (action: string, data: any) => void }) {
  const enabled = ticker.partial_fills_enabled ?? false;
  const buyLegs: Leg[] = ticker.buy_legs?.length ? ticker.buy_legs : [];
  const sellLegs: Leg[] = ticker.sell_legs?.length ? ticker.sell_legs : [];

  const handleToggle = (checked: boolean) => {
    send('UPDATE_TICKER', {
      symbol: ticker.symbol,
      partial_fills_enabled: checked,
      ...(checked && buyLegs.length === 0 ? { buy_legs: DEFAULT_BUY_LEGS } : {}),
      ...(checked && sellLegs.length === 0 ? { sell_legs: DEFAULT_SELL_LEGS } : {}),
    });
  };

  const updateBuyLegs = (legs: Leg[]) => {
    send('UPDATE_TICKER', { symbol: ticker.symbol, buy_legs: legs });
  };

  const updateSellLegs = (legs: Leg[]) => {
    send('UPDATE_TICKER', { symbol: ticker.symbol, sell_legs: legs });
  };

  const buyTotal = buyLegs.reduce((a, l) => a + (l.alloc_pct || 0), 0);
  const sellTotal = sellLegs.reduce((a, l) => a + (l.alloc_pct || 0), 0);

  return (
    <div className="space-y-5" data-testid={`partial-fills-tab-${ticker.symbol}`}>
      {/* Enable toggle */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-bold text-foreground">Scale In / Scale Out</p>
          <p className="text-xs text-muted-foreground mt-0.5">Buy and sell in multiple legs instead of all at once</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
            enabled ? 'bg-primary/10 text-primary border-primary/30' : 'bg-secondary text-muted-foreground border-border'
          }`}>
            {enabled ? 'ON' : 'OFF'}
          </span>
          <Checkbox
            data-testid={`partial-fills-toggle-${ticker.symbol}`}
            checked={enabled}
            onCheckedChange={handleToggle}
          />
        </div>
      </div>

      {enabled && (
        <>
          {/* Buy Legs */}
          <LegEditor
            label="Buy Legs (Scale In)"
            description="Each leg buys a % of your total buy power when the price drops to the trigger"
            legs={buyLegs}
            onChange={updateBuyLegs}
            side="buy"
            symbol={ticker.symbol}
            totalPct={buyTotal}
          />

          {/* Sell Legs */}
          <LegEditor
            label="Sell Legs (Scale Out)"
            description="Each leg sells a % of your position when the price rises to the trigger"
            legs={sellLegs}
            onChange={updateSellLegs}
            side="sell"
            symbol={ticker.symbol}
            totalPct={sellTotal}
          />

          {/* Summary */}
          <div className="rounded-lg bg-secondary/30 border border-border p-3 text-xs text-muted-foreground space-y-1">
            <p className="font-semibold text-foreground text-[11px]">How it works:</p>
            <p>With partial fills, the bot splits your trades into multiple legs. Each leg triggers at a different price level.</p>
            <p>Buy legs trigger from the <span className="text-primary font-medium">{buyLegs.length > 0 && buyLegs[0]?.is_percent ? 'moving average' : 'dollar price'}</span>. Sell legs trigger from your <span className="text-primary font-medium">average entry price</span>.</p>
            <p>Stop loss still protects your entire remaining position.</p>
          </div>
        </>
      )}
    </div>
  );
}

function LegEditor({ label, description, legs, onChange, side, symbol, totalPct }: {
  label: string;
  description: string;
  legs: Leg[];
  onChange: (legs: Leg[]) => void;
  side: 'buy' | 'sell';
  symbol: string;
  totalPct: number;
}) {
  const isBuy = side === 'buy';
  const accent = isBuy ? 'emerald' : 'amber';

  const updateLeg = (index: number, field: keyof Leg, value: any) => {
    const updated = legs.map((l, i) => i === index ? { ...l, [field]: value } : l);
    onChange(updated);
  };

  const addLeg = () => {
    const defaultOffset = isBuy ? -(legs.length + 1) * 2 : (legs.length + 1) * 3;
    onChange([...legs, { alloc_pct: 0, offset: defaultOffset, is_percent: true }]);
  };

  const removeLeg = (index: number) => {
    onChange(legs.filter((_, i) => i !== index));
  };

  const isOverAllocated = totalPct > 100;

  return (
    <div className={`rounded-xl border p-4 space-y-3 ${
      isBuy ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-amber-500/20 bg-amber-500/5'
    }`} data-testid={`${side}-legs-editor-${symbol}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className={`text-xs font-bold ${isBuy ? 'text-emerald-400' : 'text-amber-400'}`}>{label}</p>
          <p className="text-[10px] text-muted-foreground mt-0.5">{description}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
            isOverAllocated ? 'bg-red-500/20 text-red-400' : `bg-${accent}-500/10 text-${accent}-400`
          }`}>
            {totalPct.toFixed(0)}%
          </span>
          <button
            onClick={addLeg}
            className={`text-[10px] font-bold px-2 py-1 rounded-lg border transition-colors ${
              isBuy
                ? 'border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10'
                : 'border-amber-500/30 text-amber-400 hover:bg-amber-500/10'
            }`}
            data-testid={`add-${side}-leg-${symbol}`}
          >
            + Leg
          </button>
        </div>
      </div>

      {isOverAllocated && (
        <p className="text-[10px] text-red-400 font-medium">Total allocation exceeds 100%. Reduce leg percentages.</p>
      )}

      {legs.length === 0 && (
        <p className="text-xs text-muted-foreground text-center py-3">No legs configured. Click "+ Leg" to add one.</p>
      )}

      {legs.map((leg, i) => (
        <div key={i} className="flex items-center gap-2 bg-background/50 rounded-lg px-3 py-2 border border-border/50" data-testid={`${side}-leg-${i}-${symbol}`}>
          <span className={`text-[10px] font-bold w-5 text-center ${isBuy ? 'text-emerald-400' : 'text-amber-400'}`}>
            {i + 1}
          </span>

          {/* Alloc % */}
          <div className="flex items-center gap-1">
            <input
              type="number"
              min={1}
              max={100}
              value={leg.alloc_pct}
              onChange={(e) => updateLeg(i, 'alloc_pct', Math.max(0, Math.min(100, parseFloat(e.target.value) || 0)))}
              className="w-14 text-xs font-mono bg-background border border-border rounded px-1.5 py-1 text-center text-foreground focus:border-primary/50 focus:outline-none"
              data-testid={`${side}-leg-${i}-alloc-${symbol}`}
            />
            <span className="text-[10px] text-muted-foreground">%</span>
          </div>

          <span className="text-[10px] text-muted-foreground">{isBuy ? 'buy at' : 'sell at'}</span>

          {/* Offset */}
          <div className="flex items-center gap-1">
            <input
              type="number"
              step={0.1}
              value={leg.offset}
              onChange={(e) => updateLeg(i, 'offset', parseFloat(e.target.value) || 0)}
              className="w-20 text-xs font-mono bg-background border border-border rounded px-1.5 py-1 text-center text-foreground focus:border-primary/50 focus:outline-none"
              data-testid={`${side}-leg-${i}-offset-${symbol}`}
            />
          </div>

          {/* % or $ toggle */}
          <button
            onClick={() => updateLeg(i, 'is_percent', !leg.is_percent)}
            className={`text-[10px] font-bold w-8 py-1 rounded border transition-all ${
              leg.is_percent
                ? 'bg-primary/10 text-primary border-primary/30'
                : 'bg-secondary text-muted-foreground border-border'
            }`}
            data-testid={`${side}-leg-${i}-mode-${symbol}`}
          >
            {leg.is_percent ? '%' : '$'}
          </button>

          {/* Remove */}
          <button
            onClick={() => removeLeg(i)}
            className="text-muted-foreground hover:text-red-400 transition-colors ml-auto p-0.5"
            data-testid={`remove-${side}-leg-${i}-${symbol}`}
          >
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}
