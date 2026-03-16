import React, { memo, useState, useCallback, useEffect, useMemo } from 'react';
import { useStore, TickerConfig, PricePoint } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import {
  ChevronDown,
  ChevronUp,
  Trash2,
  TrendingUp,
  TrendingDown,
  Zap,
  ShieldAlert,
  BarChart3,
  Banknote,
  Minus,
  Plus,
  Activity,
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { toast } from 'sonner';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';

interface Props {
  ticker: TickerConfig;
}

export const TickerCard = memo(function TickerCard({ ticker }: Props) {
  const { send } = useWebSocket();
  const price = useStore((s) => s.prices[ticker.symbol] ?? 0);
  const pnl = useStore((s) => s.profits[ticker.symbol] ?? 0);
  const position = useStore((s) => s.positions[ticker.symbol]);
  const incrementStep = useStore((s) => s.incrementStep);
  const decrementStep = useStore((s) => s.decrementStep);
  const chartEnabled = useStore((s) => s.chartEnabled[ticker.symbol] ?? false);
  const toggleChart = useStore((s) => s.toggleChart);
  const priceHistory = useStore((s) => s.priceHistory[ticker.symbol] ?? []);
  const [expanded, setExpanded] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmTP, setConfirmTP] = useState(false);

  const isPositive = pnl >= 0;
  const isActive = ticker.enabled;

  const handleToggle = (checked: boolean) => {
    send('UPDATE_TICKER', { symbol: ticker.symbol, enabled: checked });
  };

  const handleDelete = () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
      return;
    }
    send('DELETE_TICKER', { symbol: ticker.symbol });
  };

  const handleFieldChange = useCallback((field: string, value: any) => {
    send('UPDATE_TICKER', { symbol: ticker.symbol, [field]: value });
  }, [send, ticker.symbol]);

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

  const avgPrice = price > 0 ? price : 100;
  // Percent mode: offset from avg. Dollar mode: the value IS the target price.
  const buyTarget = ticker.buy_percent
    ? (avgPrice * (1 + ticker.buy_offset / 100)).toFixed(2)
    : ticker.buy_offset.toFixed(2);
  const sellTarget = ticker.sell_percent
    ? (avgPrice * (1 + ticker.sell_offset / 100)).toFixed(2)
    : ticker.sell_offset.toFixed(2);

  return (
    <div
      data-testid={`ticker-card-${ticker.symbol}`}
      className={`
        relative overflow-hidden rounded-xl border transition-all duration-300
        ${isActive
          ? isPositive
            ? 'border-emerald-500/30 glow-success'
            : 'border-red-500/30 glow-danger'
          : 'border-border opacity-60'
        }
        glass hover:border-primary/40
      `}
    >
      {isActive && (
        <div
          className={`absolute -right-8 -top-8 h-24 w-24 rounded-full blur-3xl opacity-20 ${
            isPositive ? 'bg-emerald-500' : 'bg-red-500'
          }`}
        />
      )}

      <div className="relative p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <Checkbox
              data-testid={`chart-toggle-${ticker.symbol}`}
              checked={chartEnabled}
              onCheckedChange={() => toggleChart(ticker.symbol)}
              className="h-3.5 w-3.5 data-[state=checked]:bg-accent data-[state=checked]:border-accent"
            />
            <h3 className="text-lg font-bold tracking-tight text-foreground">{ticker.symbol}</h3>
            <span
              className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                isActive
                  ? 'bg-primary/20 text-primary border border-primary/30'
                  : 'bg-secondary text-muted-foreground'
              }`}
            >
              {isActive ? 'LIVE' : 'OFF'}
            </span>
            {ticker.trailing_enabled && (
              <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-accent/20 text-accent border border-accent/30">
                TRAIL
              </span>
            )}
          </div>
          <Switch
            data-testid={`ticker-toggle-${ticker.symbol}`}
            checked={isActive}
            onCheckedChange={handleToggle}
            className="data-[state=checked]:bg-primary data-[state=checked]:glow-primary"
          />
        </div>

        {/* Price + P&L */}
        <div className="grid grid-cols-2 gap-4 mb-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Price</p>
            <p className="font-mono text-xl font-bold tracking-tight text-foreground">
              ${price.toFixed(2)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Net P&L</p>
            <p className={`font-mono text-xl font-bold tracking-tight ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
              {isPositive ? '+' : ''}${pnl.toFixed(2)}
            </p>
          </div>
        </div>

        {/* Quick stats */}
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground font-mono">
          <span className="flex items-center gap-1">
            <TrendingDown size={10} className="text-emerald-400" /> Buy: ${buyTarget}
          </span>
          <span className="flex items-center gap-1">
            <TrendingUp size={10} className="text-blue-400" /> Sell: ${sellTarget}
          </span>
          <span className="flex items-center gap-1">
            <Zap size={10} className="text-primary" /> ${ticker.base_power.toFixed(0)}
          </span>
        </div>

        {/* Position indicator */}
        {position && position.quantity > 0 && (
          <div className="mt-2 px-2 py-1 rounded bg-primary/10 border border-primary/20 text-xs font-mono">
            <span className="text-muted-foreground">Holding: </span>
            <span className="text-foreground font-bold">{position.quantity.toFixed(4)}</span>
            <span className="text-muted-foreground"> @ </span>
            <span className="text-foreground">${position.avg_entry.toFixed(2)}</span>
            <span className={`ml-2 font-bold ${position.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {position.unrealized_pnl >= 0 ? '+' : ''}${position.unrealized_pnl.toFixed(2)}
            </span>
          </div>
        )}

        {/* Live Price Chart */}
        {chartEnabled && <LivePriceChart ticker={ticker} priceHistory={priceHistory} />}

        {/* Controls row: Expand / Take Profit / Delete */}
        <div className="flex items-center justify-between mt-3">
          <button
            data-testid={`ticker-expand-${ticker.symbol}`}
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {expanded ? 'Collapse' : 'Configure'}
          </button>

          <div className="flex items-center gap-3">
            {/* Take Profit button — only shows when there's P&L */}
            {pnl !== 0 && (
              <button
                data-testid={`take-profit-${ticker.symbol}`}
                onClick={handleTakeProfit}
                className={`flex items-center gap-1 text-xs transition-all ${
                  confirmTP
                    ? 'text-amber-400 font-bold animate-pulse'
                    : 'text-emerald-400 hover:text-emerald-300'
                }`}
              >
                <Banknote size={12} />
                {confirmTP ? `Take $${pnl.toFixed(2)}?` : 'Take Profit'}
              </button>
            )}

            <button
              data-testid={`ticker-delete-${ticker.symbol}`}
              onClick={handleDelete}
              className={`flex items-center gap-1 text-xs transition-all ${
                confirmDelete
                  ? 'text-red-400 font-bold animate-pulse'
                  : 'text-muted-foreground hover:text-red-400'
              }`}
            >
              <Trash2 size={12} />
              {confirmDelete ? 'Confirm?' : 'Remove'}
            </button>
          </div>
        </div>
      </div>

      {/* Expanded config */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4 border-t border-border bg-secondary/20 space-y-4">
              {/* Top config toggles */}
              <div className="flex items-center justify-end gap-4">
                <div className="flex items-center gap-2">
                  <label className="text-[10px] text-muted-foreground font-medium cursor-pointer" htmlFor={`compound-${ticker.symbol}`}>
                    Compound profits
                  </label>
                  <Checkbox
                    id={`compound-${ticker.symbol}`}
                    data-testid={`compound-toggle-${ticker.symbol}`}
                    checked={ticker.compound_profits ?? true}
                    onCheckedChange={(v) => handleFieldChange('compound_profits', !!v)}
                    className="h-3.5 w-3.5 data-[state=checked]:bg-emerald-400 data-[state=checked]:border-emerald-400"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-[10px] text-muted-foreground font-medium cursor-pointer" htmlFor={`wait-day-${ticker.symbol}`}>
                    Wait 1 day before selling
                  </label>
                  <Checkbox
                    id={`wait-day-${ticker.symbol}`}
                    data-testid={`wait-day-toggle-${ticker.symbol}`}
                    checked={ticker.wait_day_after_buy ?? false}
                    onCheckedChange={(v) => handleFieldChange('wait_day_after_buy', !!v)}
                    className="h-3.5 w-3.5 data-[state=checked]:bg-amber-400 data-[state=checked]:border-amber-400"
                  />
                </div>
              </div>

              {/* Buy Rules */}
              <ConfigSection title="Buy Rules" icon={TrendingDown} color="text-emerald-400">
                <OrderTypeToggle
                  value={(ticker.buy_order_type ?? 'limit') as 'limit' | 'market'}
                  onChange={(v) => handleFieldChange('buy_order_type', v)}
                  testId={`buy-order-type-${ticker.symbol}`}
                />
                <OffsetInput
                  label={ticker.buy_percent ? 'Buy Offset (%)' : 'Buy Price ($)'}
                  value={ticker.buy_offset}
                  isPercent={ticker.buy_percent}
                  mode="buy"
                  onChange={(v) => handleFieldChange('buy_offset', v)}
                  incrementStep={incrementStep}
                  decrementStep={decrementStep}
                />
                <ConfigToggle label="Use %" checked={ticker.buy_percent}
                  onChange={(v) => handleFieldChange('buy_percent', v)} />
                <SteppedInput label="Buy Power ($)" value={ticker.base_power}
                  onChange={(v) => handleFieldChange('base_power', v)} min={1}
                  incrementStep={incrementStep} decrementStep={decrementStep} />
                <SteppedInput label="Avg Period (days)" value={ticker.avg_days}
                  onChange={(v) => handleFieldChange('avg_days', Math.round(v))} min={1} max={365}
                  incrementStep={1} decrementStep={1} />
              </ConfigSection>

              {/* Sell Rules */}
              <ConfigSection title="Sell Rules" icon={TrendingUp} color="text-blue-400">
                <OrderTypeToggle
                  value={(ticker.sell_order_type ?? 'limit') as 'limit' | 'market'}
                  onChange={(v) => handleFieldChange('sell_order_type', v)}
                  testId={`sell-order-type-${ticker.symbol}`}
                />
                <OffsetInput
                  label={ticker.sell_percent ? 'Sell Offset (%)' : 'Sell Price ($)'}
                  value={ticker.sell_offset}
                  isPercent={ticker.sell_percent}
                  mode="sell"
                  onChange={(v) => handleFieldChange('sell_offset', v)}
                  incrementStep={incrementStep}
                  decrementStep={decrementStep}
                />
                <ConfigToggle label="Use %" checked={ticker.sell_percent}
                  onChange={(v) => handleFieldChange('sell_percent', v)} />
              </ConfigSection>

              {/* Stop Loss */}
              <ConfigSection title="Stop Loss" icon={ShieldAlert} color="text-red-400">
                <OrderTypeToggle
                  value={(ticker.stop_order_type ?? 'limit') as 'limit' | 'market'}
                  onChange={(v) => handleFieldChange('stop_order_type', v)}
                  testId={`stop-order-type-${ticker.symbol}`}
                />
                <OffsetInput
                  label={ticker.stop_percent ? 'Stop Offset (%)' : 'Stop Price ($)'}
                  value={ticker.stop_offset}
                  isPercent={ticker.stop_percent}
                  mode="stop"
                  onChange={(v) => handleFieldChange('stop_offset', v)}
                  incrementStep={incrementStep}
                  decrementStep={decrementStep}
                />
                <ConfigToggle label="Use %" checked={ticker.stop_percent}
                  onChange={(v) => handleFieldChange('stop_percent', v)} />
              </ConfigSection>

              {/* Trailing Stop */}
              <ConfigSection title="Trailing Stop" icon={BarChart3} color="text-accent">
                <ConfigToggle
                  label="Enable Trailing"
                  checked={ticker.trailing_enabled}
                  onChange={(v) => handleFieldChange('trailing_enabled', v)}
                  accent
                />
                {ticker.trailing_enabled && (
                  <>
                    <OrderTypeToggle
                      value={(ticker.trailing_order_type ?? 'limit') as 'limit' | 'market'}
                      onChange={(v) => handleFieldChange('trailing_order_type', v)}
                      testId={`trailing-order-type-${ticker.symbol}`}
                    />
                    <SteppedInput
                      label={(ticker.trailing_percent_mode ?? true) ? 'Trail %' : 'Trail $'}
                      value={ticker.trailing_percent}
                      onChange={(v) => handleFieldChange('trailing_percent', v)}
                      min={0.01} max={(ticker.trailing_percent_mode ?? true) ? 50 : 99999}
                      incrementStep={incrementStep} decrementStep={decrementStep}
                    />
                    <ConfigToggle label="Use %" checked={ticker.trailing_percent_mode ?? true}
                      onChange={(v) => handleFieldChange('trailing_percent_mode', v)} />
                  </>
                )}
              </ConfigSection>

              {/* Strategy Presets */}
              <div>
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-2">
                  Preset Strategies
                </p>
                <div className="flex gap-2 flex-wrap">
                  {[
                    { id: 'conservative_1y', label: 'Conservative 1Y' },
                    { id: 'aggressive_monthly', label: 'Aggressive Monthly' },
                    { id: 'swing_trader', label: 'Swing Trader' },
                  ].map((s) => (
                    <button
                      key={s.id}
                      data-testid={`strategy-${s.id}-${ticker.symbol}`}
                      onClick={() => send('APPLY_STRATEGY', { symbol: ticker.symbol, preset: s.id })}
                      className={`text-[10px] px-2.5 py-1 rounded-full border transition-all ${
                        ticker.strategy === s.id
                          ? 'bg-primary/20 text-primary border-primary/40'
                          : 'bg-secondary text-muted-foreground border-border hover:border-primary/30 hover:text-foreground'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});

/* --- SUB COMPONENTS --- */

function LivePriceChart({ ticker, priceHistory }: { ticker: TickerConfig; priceHistory: PricePoint[] }) {
  const chartData = useMemo(() => {
    if (priceHistory.length < 2) return [];
    let runningHigh = 0;
    return priceHistory.map((p) => {
      if (p.price > runningHigh) runningHigh = p.price;
      const trailMode = ticker.trailing_percent_mode ?? true;
      const trailVal = ticker.trailing_percent;
      const trailStop = ticker.trailing_enabled
        ? trailMode
          ? runningHigh * (1 - trailVal / 100)
          : runningHigh - trailVal
        : undefined;
      return {
        time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        price: p.price,
        trailStop: trailStop ? Math.round(trailStop * 100) / 100 : undefined,
      };
    });
  }, [priceHistory, ticker.trailing_enabled, ticker.trailing_percent, ticker.trailing_percent_mode]);

  if (chartData.length < 2) {
    return (
      <div className="mt-3 flex items-center justify-center h-24 rounded-lg bg-secondary/30 border border-border/30">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Activity size={12} className="animate-pulse" />
          Collecting price data...
        </div>
      </div>
    );
  }

  const prices = chartData.map((d) => d.price);
  const minP = Math.min(...prices) * 0.9995;
  const maxP = Math.max(...prices) * 1.0005;

  return (
    <div className="mt-3 rounded-lg bg-secondary/20 border border-border/30 p-2" data-testid={`chart-${ticker.symbol}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1">
          <Activity size={10} /> Live Chart
        </span>
        <span className="text-[10px] font-mono text-muted-foreground">{chartData.length} pts</span>
      </div>
      <ResponsiveContainer width="100%" height={140}>
        <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
          <XAxis dataKey="time" tick={false} axisLine={false} />
          <YAxis domain={[minP, maxP]} tick={{ fontSize: 9, fill: '#64748b' }} axisLine={false} tickLine={false} width={50} tickFormatter={(v: number) => `$${v.toFixed(1)}`} />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '11px' }}
            labelStyle={{ color: '#94a3b8' }}
            formatter={(v: number, name: string) => [`$${v.toFixed(2)}`, name === 'price' ? 'Price' : 'Trail Stop']}
          />
          <Line type="monotone" dataKey="price" stroke="#6366f1" strokeWidth={2} dot={false} isAnimationActive={false} />
          {ticker.trailing_enabled && (
            <Line type="monotone" dataKey="trailStop" stroke="#f59e0b" strokeWidth={1} strokeDasharray="4 2" dot={false} isAnimationActive={false} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function ConfigSection({
  title, icon: Icon, color, children,
}: {
  title: string; icon: any; color: string; children: React.ReactNode;
}) {
  return (
    <div>
      <p className={`text-[10px] uppercase tracking-wider font-semibold mb-2 flex items-center gap-1.5 ${color}`}>
        <Icon size={11} /> {title}
      </p>
      <div className="grid grid-cols-2 gap-2">{children}</div>
    </div>
  );
}

function OrderTypeToggle({
  value, onChange, testId,
}: {
  value: 'limit' | 'market'; onChange: (v: string) => void; testId: string;
}) {
  return (
    <div className="col-span-2 flex items-center gap-1 p-0.5 rounded-md bg-secondary/60 border border-border/40" data-testid={testId}>
      <button
        type="button"
        onClick={() => onChange('limit')}
        className={`flex-1 text-[10px] font-bold uppercase tracking-wider py-1 rounded transition-all ${
          value === 'limit'
            ? 'bg-primary/20 text-primary shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
        }`}
        data-testid={`${testId}-limit`}
      >
        Limit
      </button>
      <button
        type="button"
        onClick={() => onChange('market')}
        className={`flex-1 text-[10px] font-bold uppercase tracking-wider py-1 rounded transition-all ${
          value === 'market'
            ? 'bg-amber-400/20 text-amber-400 shadow-sm'
            : 'text-muted-foreground hover:text-foreground'
        }`}
        data-testid={`${testId}-market`}
      >
        Market
      </button>
    </div>
  );
}

/**
 * useDecimalInput: hook that manages a local text buffer so the user can
 * freely type decimals ("250.", "0.0") without the value snapping away.
 * Commits the parsed number to the parent on blur.
 */
function useDecimalInput(externalValue: number, commit: (v: number) => void) {
  const [text, setText] = useState(String(externalValue));
  const [focused, setFocused] = useState(false);

  // Sync from parent when NOT focused (e.g. arrow buttons, strategy presets)
  useEffect(() => {
    if (!focused) setText(String(externalValue));
  }, [externalValue, focused]);

  const handleChange = (raw: string) => {
    // Allow empty, digits, one leading minus, one dot
    if (/^-?\d*\.?\d*$/.test(raw)) {
      setText(raw);
    }
  };

  const handleBlur = () => {
    setFocused(false);
    const num = parseFloat(text);
    if (!isNaN(num)) {
      commit(num);
    } else {
      setText(String(externalValue));
    }
  };

  return { text, setText, focused, setFocused, handleChange, handleBlur };
}

/**
 * OffsetInput: Smart input that handles two modes:
 * - Percent mode (buy/stop): locked "–" prefix, user types magnitude, stored negative
 * - Percent mode (sell): regular positive percent input
 * - Dollar mode: "$" prefix, user types the absolute target price (positive number)
 */
function OffsetInput({
  label, value, isPercent, mode, onChange, incrementStep, decrementStep,
}: {
  label: string; value: number; isPercent: boolean;
  mode: 'buy' | 'sell' | 'stop';
  onChange: (v: number) => void;
  incrementStep: number; decrementStep: number;
}) {
  const isNegativePercent = isPercent && (mode === 'buy' || mode === 'stop');

  if (!isPercent) {
    // DOLLAR MODE: absolute target price (always positive)
    const dec = useDecimalInput(value, (num) => onChange(Math.abs(num)));
    return (
      <div>
        <label className="text-[10px] text-muted-foreground block mb-0.5">{label}</label>
        <div className="flex items-center">
          <span className="flex items-center justify-center h-[26px] w-6 bg-emerald-500/15 text-emerald-400 border border-border border-r-0 rounded-l text-xs font-bold shrink-0">
            $
          </span>
          <input
            type="text"
            inputMode="decimal"
            value={dec.text}
            onChange={(e) => dec.handleChange(e.target.value)}
            onFocus={() => dec.setFocused(true)}
            onBlur={dec.handleBlur}
            className="w-full h-[26px] bg-background border-y border-border px-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground text-center"
            data-testid={`input-${label.toLowerCase().replace(/[\s()$%]/g, '-')}`}
          />
          <div className="flex flex-col h-[26px] shrink-0">
            <button
              onClick={() => onChange(parseFloat((value + incrementStep).toFixed(4)))}
              className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 rounded-tr text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
            >
              <Plus size={8} />
            </button>
            <button
              onClick={() => onChange(parseFloat(Math.max(0, value - decrementStep).toFixed(4)))}
              className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 border-t-0 rounded-br text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
            >
              <Minus size={8} />
            </button>
          </div>
        </div>
        <p className="text-[8px] text-muted-foreground/50 mt-0.5">
          {mode === 'buy' ? 'Buy' : mode === 'sell' ? 'Sell' : 'Stop'} when price hits ${value.toFixed(2)}
        </p>
      </div>
    );
  }

  if (isNegativePercent) {
    // PERCENT MODE (buy/stop): locked "–" prefix, store negative
    const magnitude = Math.abs(value);
    const dec = useDecimalInput(magnitude, (num) => onChange(-Math.abs(num)));
    return (
      <div>
        <label className="text-[10px] text-muted-foreground block mb-0.5">{label}</label>
        <div className="flex items-center">
          <span className="flex items-center justify-center h-[26px] w-6 bg-red-500/15 text-red-400 border border-border border-r-0 rounded-l text-xs font-bold shrink-0">
            &ndash;
          </span>
          <input
            type="text"
            inputMode="decimal"
            value={dec.text}
            onChange={(e) => dec.handleChange(e.target.value)}
            onFocus={() => dec.setFocused(true)}
            onBlur={dec.handleBlur}
            className="w-full h-[26px] bg-background border-y border-border px-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground text-center"
            data-testid={`input-${label.toLowerCase().replace(/[\s()$%]/g, '-')}`}
          />
          <div className="flex flex-col h-[26px] shrink-0">
            <button
              onClick={() => onChange(-Math.max(0, magnitude - incrementStep))}
              className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 rounded-tr text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
              title={`+${incrementStep}`}
            >
              <Plus size={8} />
            </button>
            <button
              onClick={() => onChange(-(magnitude + decrementStep))}
              className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 border-t-0 rounded-br text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
              title={`-${decrementStep}`}
            >
              <Minus size={8} />
            </button>
          </div>
        </div>
        <p className="text-[8px] text-muted-foreground/50 mt-0.5">{value}% from avg</p>
      </div>
    );
  }

  // PERCENT MODE (sell): positive percent
  const dec = useDecimalInput(value, (num) => onChange(Math.abs(num)));
  return (
    <div>
      <label className="text-[10px] text-muted-foreground block mb-0.5">{label}</label>
      <div className="flex items-center">
        <span className="flex items-center justify-center h-[26px] w-6 bg-blue-500/15 text-blue-400 border border-border border-r-0 rounded-l text-xs font-bold shrink-0">
          +
        </span>
        <input
          type="text"
          inputMode="decimal"
          value={dec.text}
          onChange={(e) => dec.handleChange(e.target.value)}
          onFocus={() => dec.setFocused(true)}
          onBlur={dec.handleBlur}
          className="w-full h-[26px] bg-background border-y border-border px-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground text-center"
          data-testid={`input-${label.toLowerCase().replace(/[\s()$%]/g, '-')}`}
        />
        <div className="flex flex-col h-[26px] shrink-0">
          <button
            onClick={() => onChange(parseFloat((value + incrementStep).toFixed(4)))}
            className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 rounded-tr text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
          >
            <Plus size={8} />
          </button>
          <button
            onClick={() => onChange(parseFloat(Math.max(0, value - decrementStep).toFixed(4)))}
            className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 border-t-0 rounded-br text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
          >
            <Minus size={8} />
          </button>
        </div>
      </div>
      <p className="text-[8px] text-muted-foreground/50 mt-0.5">+{value}% from avg</p>
    </div>
  );
}

/**
 * SteppedInput: general number input with custom increment/decrement arrows.
 * Uses local text buffer so decimals can be typed freely.
 */
function SteppedInput({
  label, value, onChange, min, max, incrementStep, decrementStep,
}: {
  label: string; value: number; onChange: (v: number) => void;
  min?: number; max?: number;
  incrementStep: number; decrementStep: number;
}) {
  const dec = useDecimalInput(value, (num) => {
    if (min !== undefined && num < min) return;
    if (max !== undefined && num > max) return;
    onChange(num);
  });

  const nudgeUp = () => {
    let next = value + incrementStep;
    if (max !== undefined) next = Math.min(next, max);
    onChange(parseFloat(next.toFixed(4)));
  };
  const nudgeDown = () => {
    let next = value - decrementStep;
    if (min !== undefined) next = Math.max(next, min);
    onChange(parseFloat(next.toFixed(4)));
  };

  return (
    <div>
      <label className="text-[10px] text-muted-foreground block mb-0.5">{label}</label>
      <div className="flex items-center">
        <input
          type="text"
          inputMode="decimal"
          value={dec.text}
          onChange={(e) => dec.handleChange(e.target.value)}
          onFocus={() => dec.setFocused(true)}
          onBlur={dec.handleBlur}
          className="w-full h-[26px] bg-background border border-border rounded-l px-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        />
        <div className="flex flex-col h-[26px] shrink-0">
          <button
            onClick={nudgeUp}
            className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 rounded-tr text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
            title={`+${incrementStep}`}
          >
            <Plus size={8} />
          </button>
          <button
            onClick={nudgeDown}
            className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 border-t-0 rounded-br text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
            title={`-${decrementStep}`}
          >
            <Minus size={8} />
          </button>
        </div>
      </div>
    </div>
  );
}

function ConfigToggle({
  label, checked, onChange, accent,
}: {
  label: string; checked: boolean; onChange: (v: boolean) => void; accent?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <Checkbox
        checked={checked}
        onCheckedChange={onChange}
        className={`${
          accent
            ? 'data-[state=checked]:bg-accent data-[state=checked]:border-accent'
            : 'data-[state=checked]:bg-primary data-[state=checked]:border-primary'
        }`}
      />
      <label className="text-[10px] text-muted-foreground cursor-pointer">{label}</label>
    </div>
  );
}
