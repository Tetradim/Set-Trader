import React, { memo, useState, useCallback } from 'react';
import { useStore, TickerConfig } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { X, TrendingDown, TrendingUp, ShieldAlert, BarChart3, Activity, Zap, Settings2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Checkbox } from '@/components/ui/checkbox';

/* Re-use the sub-components from TickerCard */
import {
  ConfigSection,
  ConfigToggle,
  SteppedInput,
  OffsetInput,
  OrderTypeToggle,
} from './ticker-card/ConfigWidgets';

const CONFIG_TABS = [
  { id: 'rules', label: 'Rules', icon: TrendingDown },
  { id: 'risk', label: 'Risk', icon: ShieldAlert },
  { id: 'rebracket', label: 'Rebracket', icon: Activity },
  { id: 'advanced', label: 'Advanced', icon: Settings2 },
] as const;

type ConfigTabId = (typeof CONFIG_TABS)[number]['id'];

interface Props {
  ticker: TickerConfig;
  onClose: () => void;
}

export const ConfigModal = memo(function ConfigModal({ ticker, onClose }: Props) {
  const { send } = useWebSocket();
  const incrementStep = useStore((s) => s.incrementStep);
  const decrementStep = useStore((s) => s.decrementStep);
  const [activeTab, setActiveTab] = useState<ConfigTabId>('rules');

  const handleFieldChange = useCallback(
    (field: string, value: any) => {
      if (field === 'buy_percent' && value === false && ticker.buy_offset < 0) {
        send('UPDATE_TICKER', { symbol: ticker.symbol, buy_percent: false, buy_offset: Math.abs(ticker.buy_offset) });
        return;
      }
      if (field === 'sell_percent' && value === false && ticker.sell_offset < 0) {
        send('UPDATE_TICKER', { symbol: ticker.symbol, sell_percent: false, sell_offset: Math.abs(ticker.sell_offset) });
        return;
      }
      if (field === 'stop_percent' && value === false && ticker.stop_offset < 0) {
        send('UPDATE_TICKER', { symbol: ticker.symbol, stop_percent: false, stop_offset: Math.abs(ticker.stop_offset) });
        return;
      }
      send('UPDATE_TICKER', { symbol: ticker.symbol, [field]: value });
    },
    [send, ticker.symbol, ticker.buy_offset, ticker.sell_offset, ticker.stop_offset]
  );

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        data-testid={`config-modal-overlay-${ticker.symbol}`}
      >
        <motion.div
          className="glass border border-border rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl"
          initial={{ scale: 0.92, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.92, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 300 }}
          onClick={(e) => e.stopPropagation()}
          data-testid={`config-modal-${ticker.symbol}`}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-bold text-foreground">{ticker.symbol}</h2>
              <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${
                ticker.enabled ? 'bg-emerald-400/20 text-emerald-400 border border-emerald-400/30' : 'bg-secondary text-muted-foreground'
              }`}>
                {ticker.enabled ? 'LIVE' : 'OFF'}
              </span>
            </div>
            <button
              onClick={onClose}
              className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-lg hover:bg-secondary"
              data-testid={`close-config-modal-${ticker.symbol}`}
            >
              <X size={18} />
            </button>
          </div>

          {/* Tab bar */}
          <div className="flex items-center gap-1 px-6 pt-3 border-b border-border shrink-0">
            {CONFIG_TABS.map((tab) => {
              const Icon = tab.icon;
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg transition-all ${
                    active
                      ? 'text-primary bg-card border border-b-0 border-border -mb-px'
                      : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                  }`}
                  data-testid={`config-tab-${tab.id}-${ticker.symbol}`}
                >
                  <Icon size={12} />
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-auto px-6 py-5 space-y-5">
            {/* Auto-stop alert banner */}
            {ticker.auto_stopped && (
              <div className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30">
                <div className="flex items-center gap-2">
                  <ShieldAlert size={14} className="text-red-500 shrink-0" />
                  <p className="text-xs text-red-400">
                    <span className="font-bold">Auto-stopped:</span> {ticker.auto_stop_reason || 'Loss limit reached'}
                  </p>
                </div>
                <button
                  onClick={() => {
                    handleFieldChange('auto_stopped', false);
                    handleFieldChange('auto_stop_reason', '');
                    handleFieldChange('enabled', true);
                  }}
                  className="text-[10px] font-bold uppercase px-3 py-1 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 border border-red-500/40 transition-colors shrink-0"
                  data-testid={`modal-re-enable-${ticker.symbol}`}
                >
                  Re-enable
                </button>
              </div>
            )}

            {activeTab === 'rules' && (
              <RulesTab ticker={ticker} onChange={handleFieldChange} incStep={incrementStep} decStep={decrementStep} />
            )}
            {activeTab === 'risk' && (
              <RiskTab ticker={ticker} onChange={handleFieldChange} incStep={incrementStep} decStep={decrementStep} />
            )}
            {activeTab === 'rebracket' && (
              <RebracketTab ticker={ticker} onChange={handleFieldChange} incStep={incrementStep} decStep={decrementStep} />
            )}
            {activeTab === 'advanced' && (
              <AdvancedTab ticker={ticker} onChange={handleFieldChange} send={send} incStep={incrementStep} decStep={decrementStep} />
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
});

/* ============ Tab Panels ============ */

interface TabProps {
  ticker: TickerConfig;
  onChange: (field: string, value: any) => void;
  incStep: number;
  decStep: number;
}

function RulesTab({ ticker, onChange, incStep, decStep }: TabProps) {
  const accountBalance = useStore((s) => s.accountBalance);
  const tickers = useStore((s) => s.tickers);
  const totalAllocated = Object.values(tickers).reduce((s, t) => s + (t.base_power ?? 0), 0);
  const otherAllocated = totalAllocated - (ticker.base_power ?? 0);
  const availableForThis = accountBalance - otherAllocated;

  return (
    <div className="space-y-5">
      {/* Quick toggles */}
      <div className="flex items-center gap-6">
        <ConfigToggle label="Compound profits" checked={ticker.compound_profits ?? true} onChange={(v) => onChange('compound_profits', v)} />
        <ConfigToggle label="Wait 1 day before selling" checked={ticker.wait_day_after_buy ?? false} onChange={(v) => onChange('wait_day_after_buy', v)} />
      </div>

      {/* Buy Rules */}
      <ConfigSection title="Buy Rules" icon={TrendingDown} color="text-emerald-400">
        <OrderTypeToggle value={(ticker.buy_order_type ?? 'limit') as 'limit' | 'market'} onChange={(v) => onChange('buy_order_type', v)} testId={`modal-buy-ot-${ticker.symbol}`} />
        <OffsetInput label={ticker.buy_percent ? 'Buy Offset (%)' : 'Buy Price ($)'} value={ticker.buy_offset} isPercent={ticker.buy_percent} mode="buy" onChange={(v) => onChange('buy_offset', v)} incrementStep={incStep} decrementStep={decStep} />
        <ConfigToggle label="Use %" checked={ticker.buy_percent} onChange={(v) => onChange('buy_percent', v)} />
        <div>
          <SteppedInput label="Buy Power ($)" value={ticker.base_power} onChange={(v) => onChange('base_power', v)} min={1} incrementStep={incStep} decrementStep={decStep} />
          {accountBalance > 0 && (
            <p className={`text-[9px] mt-0.5 font-mono ${
              ticker.base_power > availableForThis ? 'text-amber-400' : 'text-muted-foreground/50'
            }`}>
              {ticker.base_power > availableForThis
                ? `Exceeds available by $${(ticker.base_power - availableForThis).toFixed(2)}`
                : `$${(availableForThis - ticker.base_power).toFixed(2)} remaining after this`
              }
            </p>
          )}
        </div>
        <SteppedInput label="Avg Period (days)" value={ticker.avg_days} onChange={(v) => onChange('avg_days', Math.round(v))} min={1} max={365} incrementStep={1} decrementStep={1} />
      </ConfigSection>

      {/* Sell Rules */}
      <ConfigSection title="Sell Rules" icon={TrendingUp} color="text-blue-400">
        <OrderTypeToggle value={(ticker.sell_order_type ?? 'limit') as 'limit' | 'market'} onChange={(v) => onChange('sell_order_type', v)} testId={`modal-sell-ot-${ticker.symbol}`} />
        <OffsetInput label={ticker.sell_percent ? 'Sell Offset (%)' : 'Sell Price ($)'} value={ticker.sell_offset} isPercent={ticker.sell_percent} mode="sell" onChange={(v) => onChange('sell_offset', v)} incrementStep={incStep} decrementStep={decStep} />
        <ConfigToggle label="Use %" checked={ticker.sell_percent} onChange={(v) => onChange('sell_percent', v)} />
      </ConfigSection>
    </div>
  );
}

function RiskTab({ ticker, onChange, incStep, decStep }: TabProps) {
  return (
    <div className="space-y-5">
      {/* Stop Loss */}
      <ConfigSection title="Stop Loss" icon={ShieldAlert} color="text-red-400">
        <OrderTypeToggle value={(ticker.stop_order_type ?? 'limit') as 'limit' | 'market'} onChange={(v) => onChange('stop_order_type', v)} testId={`modal-stop-ot-${ticker.symbol}`} />
        <OffsetInput label={ticker.stop_percent ? 'Stop Offset (%)' : 'Stop Price ($)'} value={ticker.stop_offset} isPercent={ticker.stop_percent} mode="stop" onChange={(v) => onChange('stop_offset', v)} incrementStep={incStep} decrementStep={decStep} />
        <ConfigToggle label="Use %" checked={ticker.stop_percent} onChange={(v) => onChange('stop_percent', v)} />
      </ConfigSection>

      {/* Trailing Stop */}
      <ConfigSection title="Trailing Stop" icon={BarChart3} color="text-accent">
        <ConfigToggle label="Enable Trailing" checked={ticker.trailing_enabled} onChange={(v) => onChange('trailing_enabled', v)} accent />
        {ticker.trailing_enabled && (
          <>
            <OrderTypeToggle value={(ticker.trailing_order_type ?? 'limit') as 'limit' | 'market'} onChange={(v) => onChange('trailing_order_type', v)} testId={`modal-trail-ot-${ticker.symbol}`} />
            <SteppedInput label={(ticker.trailing_percent_mode ?? true) ? 'Trail %' : 'Trail $'} value={ticker.trailing_percent} onChange={(v) => onChange('trailing_percent', v)} min={0.01} max={(ticker.trailing_percent_mode ?? true) ? 50 : 99999} incrementStep={incStep} decrementStep={decStep} />
            <ConfigToggle label="Use %" checked={ticker.trailing_percent_mode ?? true} onChange={(v) => onChange('trailing_percent_mode', v)} />
          </>
        )}
      </ConfigSection>

      {/* Risk Controls */}
      <ConfigSection title="Risk Controls" icon={ShieldAlert} color="text-orange-400">
        <SteppedInput label="Max Daily Loss ($)" value={ticker.max_daily_loss ?? 0} onChange={(v) => onChange('max_daily_loss', v)} min={0} max={99999} incrementStep={incStep} decrementStep={decStep} />
        <SteppedInput label="Max Consec. Losses" value={ticker.max_consecutive_losses ?? 0} onChange={(v) => onChange('max_consecutive_losses', Math.round(v))} min={0} max={100} incrementStep={1} decrementStep={1} />
        <div className="col-span-2 text-[9px] text-muted-foreground/60">
          Set to 0 to disable. When triggered, ticker is disabled and requires manual re-enable.
        </div>
      </ConfigSection>
    </div>
  );
}

function RebracketTab({ ticker, onChange, incStep, decStep }: TabProps) {
  return (
    <div className="space-y-5">
      <ConfigSection title="Auto Rebracket" icon={Activity} color="text-cyan-400">
        <div className="col-span-2">
          <ConfigToggle label="Enable Auto Rebracket" checked={ticker.auto_rebracket ?? false} onChange={(v) => onChange('auto_rebracket', v)} accent />
        </div>
        {(ticker.auto_rebracket ?? false) && (
          <>
            <SteppedInput label="Threshold ($)" value={ticker.rebracket_threshold ?? 2.0} onChange={(v) => onChange('rebracket_threshold', v)} min={0.01} max={99999} incrementStep={incStep} decrementStep={decStep} />
            <SteppedInput label="Spread ($)" value={ticker.rebracket_spread ?? 0.80} onChange={(v) => onChange('rebracket_spread', v)} min={0.01} max={99999} incrementStep={incStep} decrementStep={decStep} />
            <SteppedInput label="Cooldown (s)" value={ticker.rebracket_cooldown ?? 0} onChange={(v) => onChange('rebracket_cooldown', v)} min={0} max={3600} incrementStep={5} decrementStep={5} />
            <SteppedInput label="Lookback Ticks" value={ticker.rebracket_lookback ?? 10} onChange={(v) => onChange('rebracket_lookback', v)} min={2} max={100} incrementStep={1} decrementStep={1} />
            <SteppedInput label="Buffer ($)" value={ticker.rebracket_buffer ?? 0.10} onChange={(v) => onChange('rebracket_buffer', v)} min={0} max={99999} incrementStep={incStep} decrementStep={decStep} />
            <div className="col-span-2 text-[9px] text-muted-foreground/60">
              Threshold: drift distance to trigger. Spread: new bracket width. Cooldown: min seconds between rebrackets. Lookback: price ticks to find recent low. Buffer: gap below recent low for new buy.
            </div>
          </>
        )}
      </ConfigSection>
    </div>
  );
}

interface AdvancedTabProps extends TabProps {
  send: (action: string, payload: Record<string, any>) => void;
}

function AdvancedTab({ ticker, onChange, send, incStep, decStep }: AdvancedTabProps) {
  return (
    <div className="space-y-5">
      {/* Preset Strategies */}
      <div>
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-2 flex items-center gap-1.5">
          <Zap size={11} /> Preset Strategies
        </p>
        <div className="flex gap-2 flex-wrap">
          {[
            { id: 'conservative_1y', label: 'Conservative 1Y' },
            { id: 'aggressive_monthly', label: 'Aggressive Monthly' },
            { id: 'swing_trader', label: 'Swing Trader' },
          ].map((s) => (
            <button
              key={s.id}
              data-testid={`modal-strategy-${s.id}-${ticker.symbol}`}
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
  );
}
