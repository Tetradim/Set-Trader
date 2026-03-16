import React, { memo, useState } from 'react';
import { useStore, TickerConfig } from '@/stores/useStore';
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
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface Props {
  ticker: TickerConfig;
}

export const TickerCard = memo(function TickerCard({ ticker }: Props) {
  const { send } = useWebSocket();
  const price = useStore((s) => s.prices[ticker.symbol] ?? 0);
  const pnl = useStore((s) => s.profits[ticker.symbol] ?? 0);
  const position = useStore((s) => s.positions[ticker.symbol]);
  const [expanded, setExpanded] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

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

  const handleFieldChange = (field: string, value: any) => {
    send('UPDATE_TICKER', { symbol: ticker.symbol, [field]: value });
  };

  const avgPrice = price > 0 ? price : 100;
  const buyTarget = ticker.buy_percent
    ? (avgPrice * (1 + ticker.buy_offset / 100)).toFixed(2)
    : (avgPrice + ticker.buy_offset).toFixed(2);
  const sellTarget = ticker.sell_percent
    ? (avgPrice * (1 + ticker.sell_offset / 100)).toFixed(2)
    : (avgPrice + ticker.sell_offset).toFixed(2);

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
      {/* Ambient glow */}
      {isActive && (
        <div
          className={`absolute -right-8 -top-8 h-24 w-24 rounded-full blur-3xl opacity-20 ${
            isPositive ? 'bg-emerald-500' : 'bg-red-500'
          }`}
        />
      )}

      {/* Card header */}
      <div className="relative p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
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

        {/* Quick stats row */}
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

        {/* Expand / Delete controls */}
        <div className="flex items-center justify-between mt-3">
          <button
            data-testid={`ticker-expand-${ticker.symbol}`}
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {expanded ? 'Collapse' : 'Configure'}
          </button>
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
              {/* Buy Rules */}
              <ConfigSection
                title="Buy Rules"
                icon={TrendingDown}
                color="text-emerald-400"
              >
                <ConfigRow label="Offset" value={ticker.buy_offset}
                  onChange={(v) => handleFieldChange('buy_offset', v)} />
                <ConfigToggle label="Use %" checked={ticker.buy_percent}
                  onChange={(v) => handleFieldChange('buy_percent', v)} />
                <ConfigRow label="Buy Power ($)" value={ticker.base_power}
                  onChange={(v) => handleFieldChange('base_power', v)} min={1} />
                <ConfigRow label="Avg Period (days)" value={ticker.avg_days}
                  onChange={(v) => handleFieldChange('avg_days', Math.round(v))} min={1} max={365} />
              </ConfigSection>

              {/* Sell Rules */}
              <ConfigSection title="Sell Rules" icon={TrendingUp} color="text-blue-400">
                <ConfigRow label="Offset" value={ticker.sell_offset}
                  onChange={(v) => handleFieldChange('sell_offset', v)} />
                <ConfigToggle label="Use %" checked={ticker.sell_percent}
                  onChange={(v) => handleFieldChange('sell_percent', v)} />
              </ConfigSection>

              {/* Stop Loss */}
              <ConfigSection title="Stop Loss" icon={ShieldAlert} color="text-red-400">
                <ConfigRow label="Stop Offset" value={ticker.stop_offset}
                  onChange={(v) => handleFieldChange('stop_offset', v)} />
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
                  <ConfigRow label="Trail %" value={ticker.trailing_percent}
                    onChange={(v) => handleFieldChange('trailing_percent', v)} min={0.1} max={50} step={0.1} />
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

function ConfigSection({
  title,
  icon: Icon,
  color,
  children,
}: {
  title: string;
  icon: any;
  color: string;
  children: React.ReactNode;
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

function ConfigRow({
  label,
  value,
  onChange,
  min,
  max,
  step = 0.5,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <div>
      <label className="text-[10px] text-muted-foreground block mb-0.5">{label}</label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full bg-background border border-border rounded px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
      />
    </div>
  );
}

function ConfigToggle({
  label,
  checked,
  onChange,
  accent,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  accent?: boolean;
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
