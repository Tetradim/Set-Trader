import React, { memo, useState, useCallback, useEffect } from 'react';
import { useStore, TickerConfig } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { X, TrendingDown, TrendingUp, ShieldAlert, BarChart3, Activity, Zap, Settings2, Layers, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Checkbox } from '@/components/ui/checkbox';
import { getMarketMeta } from '@/lib/market-utils';
import { apiFetch } from '@/lib/api';

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
  { id: 'partial', label: 'Partial Fills', icon: Layers },
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
            {activeTab === 'partial' && (
              <PartialFillsTab ticker={ticker} onChange={handleFieldChange} send={send} />
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
  const fxRates = useStore((s) => s.fxRates);
  const totalAllocated = Object.values(tickers).reduce((s, t) => s + (t.base_power ?? 0), 0);
  const otherAllocated = totalAllocated - (ticker.base_power ?? 0);
  const availableForThis = accountBalance - otherAllocated;

  const marketMeta = getMarketMeta(ticker);
  const isNonUS = marketMeta.currency !== 'USD';
  const fxRate = fxRates[marketMeta.currency] ?? null;

  // USD equivalent of base_power (for informational display)
  const usdEquiv = isNonUS && fxRate ? ticker.base_power * fxRate : null;
  // Native equivalent when account balance is in USD
  const nativeEquiv = isNonUS && fxRate ? accountBalance / fxRate : null;

  const buyPowerLabel = isNonUS
    ? `Buy Power (${marketMeta.currencySymbol})`
    : 'Buy Power ($)';

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
          <SteppedInput label={buyPowerLabel} value={ticker.base_power} onChange={(v) => onChange('base_power', v)} min={1} incrementStep={incStep} decrementStep={decStep} />
          {/* Currency-aware buy power context */}
          {isNonUS && usdEquiv !== null && (
            <p className="text-[9px] mt-0.5 font-mono text-primary/70">
              ≈ ${usdEquiv.toFixed(2)} USD at {fxRate!.toFixed(4)} {marketMeta.currency}/USD
            </p>
          )}
          {!isNonUS && accountBalance > 0 && (
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
  const openingBellEnabled = ticker.opening_bell_enabled ?? false;
  
  return (
    <div className="space-y-5">
      {/* Opening Bell Mode */}
      <ConfigSection title="Opening Bell Mode" icon={Zap} color="text-purple-400">
        <div className="col-span-2 space-y-3">
          <div className="flex items-center justify-between p-2 rounded-lg bg-purple-500/10 border border-purple-500/20">
            <div>
              <p className="text-xs font-bold text-purple-400">Force Trailing Stop at Open</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">
                Override normal sell rules for the first 30 min after market open with a forced trailing stop
              </p>
            </div>
            <Checkbox
              data-testid={`opening-bell-toggle-${ticker.symbol}`}
              checked={openingBellEnabled}
              onCheckedChange={(v) => onChange('opening_bell_enabled', v)}
            />
          </div>
          
          {openingBellEnabled && (
            <div className="space-y-2 pl-2 border-l-2 border-purple-500/30">
              <div className="flex items-center gap-3">
                <SteppedInput 
                  label={(ticker.opening_bell_trail_is_percent ?? true) ? 'Opening Trail %' : 'Opening Trail $'} 
                  value={ticker.opening_bell_trail_value ?? 1.0} 
                  onChange={(v) => onChange('opening_bell_trail_value', v)} 
                  min={0.01} 
                  max={(ticker.opening_bell_trail_is_percent ?? true) ? 20 : 99999} 
                  incrementStep={incStep} 
                  decrementStep={decStep} 
                />
                <ConfigToggle 
                  label="Use %" 
                  checked={ticker.opening_bell_trail_is_percent ?? true} 
                  onChange={(v) => onChange('opening_bell_trail_is_percent', v)} 
                />
              </div>
              <p className="text-[9px] text-muted-foreground/70">
                During 9:30–10:00 AM ET, the bot tracks the session high and sells if price drops by this trail amount. 
                After 30 min, brackets auto-reset to the new price level.
              </p>
            </div>
          )}
        </div>
      </ConfigSection>

      {/* Halve Stop Loss */}
      <ConfigSection title="Opening Volatility Protection" icon={ShieldAlert} color="text-amber-400">
        <div className="col-span-2">
          <div className="flex items-center justify-between p-2 rounded-lg bg-secondary/30 border border-border/50">
            <div>
              <p className="text-xs font-medium text-foreground">Halve Stop Loss at Open</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">Cut stop-loss distance in half for the first 30 min (e.g., 3% → 1.5%)</p>
            </div>
            <Checkbox
              data-testid={`halve-stop-toggle-${ticker.symbol}`}
              checked={ticker.halve_stop_at_open ?? false}
              onCheckedChange={(v) => onChange('halve_stop_at_open', v)}
            />
          </div>
          <p className="text-[9px] text-muted-foreground/60 mt-2">
            Tightens the stop-loss to protect profits if price dips to a new low during opening volatility.
          </p>
        </div>
      </ConfigSection>

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

// ---- signal strategy registry types ------------------------------------
type SchemaProperty = {
  type: string;
  title?: string;
  description?: string;
  default?: number | boolean | string;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
};
type StrategyEntry = {
  name: string;
  version: string;
  description: string;
  risk_level: string;
  tags: string[];
  default_params: Record<string, number | boolean | string>;
  config_schema: { properties?: Record<string, SchemaProperty>; title?: string };
  is_signal_strategy: boolean;
};

const PRESET_IDS = ['conservative_1y', 'aggressive_monthly', 'swing_trader'];
const PRESET_LABELS: Record<string, string> = {
  conservative_1y: 'Conservative 1Y',
  aggressive_monthly: 'Aggressive Monthly',
  swing_trader: 'Swing Trader',
};
const RISK_COLORS: Record<string, string> = {
  LOW:    'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  MEDIUM: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
  HIGH:   'text-red-400 bg-red-500/10 border-red-500/30',
};

function AdvancedTab({ ticker, onChange, send, incStep, decStep }: AdvancedTabProps) {
  const [registry, setRegistry] = useState<Record<string, StrategyEntry>>({});
  const [loadingRegistry, setLoadingRegistry] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [expandedStrategy, setExpandedStrategy] = useState<string | null>(null);

  const fetchRegistry = useCallback(async () => {
    setLoadingRegistry(true);
    try {
      const data = await apiFetch('/api/strategies/registry');
      setRegistry(data.strategies ?? {});
    } catch { /* ignore */ } finally {
      setLoadingRegistry(false);
    }
  }, []);

  useEffect(() => { fetchRegistry(); }, [fetchRegistry]);

  const handleReload = async () => {
    setReloading(true);
    try {
      await apiFetch('/api/strategies/reload', { method: 'POST' });
      await fetchRegistry();
    } catch { /* ignore */ } finally {
      setReloading(false);
    }
  };

  const applySignalStrategy = (name: string, entry: StrategyEntry) => {
    send('UPDATE_TICKER', {
      symbol: ticker.symbol,
      strategy: name,
      strategy_config: entry.default_params,
    });
  };

  const updateStrategyParam = (key: string, value: number | boolean | string) => {
    const current = (ticker as any).strategy_config ?? {};
    send('UPDATE_TICKER', {
      symbol: ticker.symbol,
      strategy_config: { ...current, [key]: value },
    });
  };

  const currentIsSignal = !PRESET_IDS.includes(ticker.strategy) && ticker.strategy !== 'custom' && ticker.strategy in registry;

  return (
    <div className="space-y-5">
      {/* ---- Preset Strategies ---- */}
      <div>
        <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold mb-2 flex items-center gap-1.5">
          <Zap size={11} /> Preset Bracket Strategies
        </p>
        <div className="flex gap-2 flex-wrap">
          {PRESET_IDS.map((id) => (
            <button
              key={id}
              data-testid={`modal-strategy-${id}-${ticker.symbol}`}
              onClick={() => send('APPLY_STRATEGY', { symbol: ticker.symbol, preset: id })}
              className={`text-[10px] px-2.5 py-1 rounded-full border transition-all ${
                ticker.strategy === id
                  ? 'bg-primary/20 text-primary border-primary/40'
                  : 'bg-secondary text-muted-foreground border-border hover:border-primary/30 hover:text-foreground'
              }`}
            >
              {PRESET_LABELS[id]}
            </button>
          ))}
          {ticker.strategy !== 'custom' && PRESET_IDS.includes(ticker.strategy) && (
            <button
              onClick={() => send('APPLY_STRATEGY', { symbol: ticker.symbol, preset: ticker.strategy })}
              className="text-[10px] px-2.5 py-1 rounded-full border border-border text-muted-foreground hover:text-red-400 hover:border-red-500/30 transition-all"
              title="Revert to custom config"
            >
              Revert
            </button>
          )}
        </div>
        <p className="text-[9px] text-muted-foreground/50 mt-1.5">
          Presets apply bracket parameters. Tick the same preset again to revert.
        </p>
      </div>

      {/* Separator */}
      <div className="border-t border-border" />

      {/* ---- Signal Strategies ---- */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold flex items-center gap-1.5">
            <Activity size={11} /> Signal Strategies
            {loadingRegistry && <RefreshCw size={10} className="animate-spin ml-1" />}
          </p>
          <button
            data-testid="reload-strategies-btn"
            onClick={handleReload}
            disabled={reloading}
            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          >
            <RefreshCw size={10} className={reloading ? 'animate-spin' : ''} />
            Reload
          </button>
        </div>

        {Object.keys(registry).length === 0 && !loadingRegistry && (
          <div className="rounded-lg border border-dashed border-border p-4 text-center text-[10px] text-muted-foreground/60">
            No signal strategies loaded.
            <br />
            Drop a <span className="font-mono">*.py</span> file into{' '}
            <span className="font-mono">backend/strategies/custom/</span> and click Reload.
          </div>
        )}

        <div className="space-y-2">
          {Object.entries(registry).map(([name, entry]) => {
            const isActive = ticker.strategy === name;
            const isExpanded = expandedStrategy === name;
            const riskColor = RISK_COLORS[entry.risk_level] ?? RISK_COLORS.MEDIUM;
            const schemaProps = entry.config_schema?.properties ?? {};
            const currentConfig = (ticker as any).strategy_config ?? {};

            return (
              <div
                key={name}
                data-testid={`signal-strategy-${name.replace(/\s+/g, '-')}`}
                className={`rounded-xl border transition-all ${isActive ? 'border-primary/40 bg-primary/5' : 'border-border'}`}
              >
                {/* Header row */}
                <div className="flex items-center gap-2 px-3 py-2.5">
                  <button
                    className="flex-1 flex items-start gap-2 text-left"
                    onClick={() => setExpandedStrategy(isExpanded ? null : name)}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`font-semibold text-xs ${isActive ? 'text-primary' : 'text-foreground'}`}>{name}</span>
                        <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded-full border ${riskColor}`}>
                          {entry.risk_level}
                        </span>
                        <span className="text-[9px] text-muted-foreground/60">v{entry.version}</span>
                      </div>
                      <p className="text-[10px] text-muted-foreground/70 mt-0.5 truncate">{entry.description}</p>
                    </div>
                    {isExpanded ? <ChevronUp size={12} className="text-muted-foreground mt-0.5 shrink-0" /> : <ChevronDown size={12} className="text-muted-foreground mt-0.5 shrink-0" />}
                  </button>
                  <button
                    onClick={() => isActive
                      ? send('UPDATE_TICKER', { symbol: ticker.symbol, strategy: 'custom', strategy_config: {} })
                      : applySignalStrategy(name, entry)
                    }
                    className={`text-[10px] font-bold px-2.5 py-1 rounded-lg border transition-all shrink-0 ${
                      isActive
                        ? 'bg-red-500/15 text-red-400 border-red-500/30 hover:bg-red-500/25'
                        : 'bg-primary/15 text-primary border-primary/30 hover:bg-primary/25'
                    }`}
                  >
                    {isActive ? 'Deactivate' : 'Activate'}
                  </button>
                </div>

                {/* Dynamic param form */}
                {isExpanded && Object.keys(schemaProps).length > 0 && (
                  <div className="border-t border-border/50 px-3 py-3 space-y-3">
                    <p className="text-[9px] text-muted-foreground/60 uppercase tracking-wider font-semibold">Parameters</p>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(schemaProps).map(([key, prop]) => {
                        const rawVal = key in currentConfig ? currentConfig[key] : entry.default_params[key];
                        const displayTitle = prop.title ?? key.replace(/_/g, ' ');

                        if (prop.type === 'boolean') {
                          return (
                            <div key={key} className="flex items-center gap-2 col-span-1">
                              <Checkbox
                                checked={!!rawVal}
                                onCheckedChange={(v) => updateStrategyParam(key, !!v)}
                              />
                              <label className="text-[10px] text-muted-foreground">{displayTitle}</label>
                            </div>
                          );
                        }

                        const numVal = typeof rawVal === 'number' ? rawVal : parseFloat(String(rawVal ?? 0));
                        const isInt = prop.type === 'integer';
                        const step = isInt ? 1 : 0.1;

                        return (
                          <div key={key}>
                            <label className="text-[9px] text-muted-foreground block mb-0.5">{displayTitle}</label>
                            <input
                              type="number"
                              step={step}
                              min={prop.minimum ?? prop.exclusiveMinimum}
                              max={prop.maximum}
                              value={numVal}
                              onChange={(e) => {
                                const v = isInt ? parseInt(e.target.value) : parseFloat(e.target.value);
                                if (!isNaN(v)) updateStrategyParam(key, v);
                              }}
                              className="w-full h-6 bg-background border border-border rounded px-2 text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
                              data-testid={`strategy-param-${key}`}
                            />
                          </div>
                        );
                      })}
                    </div>
                    {!isActive && (
                      <p className="text-[9px] text-amber-400/70">
                        Activate the strategy to apply these parameters to live trading.
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}


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

function PartialFillsTab({ ticker, onChange, send }: { ticker: TickerConfig; onChange: (f: string, v: any) => void; send: (action: string, data: any) => void }) {
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
