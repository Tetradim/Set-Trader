import { useCallback, useEffect, useState } from 'react';
import { Activity, ChevronDown, ChevronUp, RefreshCw, Zap } from 'lucide-react';
import { TickerConfig } from '@/stores/useStore';
import { apiFetch } from '@/lib/api';
import { Checkbox } from '@/components/ui/checkbox';
import { Switch } from '@/components/ui/switch';

interface AdvancedTabProps {
  ticker: TickerConfig;
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

export function AdvancedTab({ ticker, send }: AdvancedTabProps) {
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
                <div className="flex items-center gap-3 px-3 py-2.5">
                  <Switch
                    checked={isActive}
                    onCheckedChange={(checked) =>
                      checked
                        ? applySignalStrategy(name, entry)
                        : send('UPDATE_TICKER', { symbol: ticker.symbol, strategy: 'custom', strategy_config: {} })
                    }
                    data-testid={`strategy-toggle-${name.replace(/\s+/g, '-')}`}
                    className="shrink-0"
                  />
                  <button
                    className="flex-1 flex items-start gap-2 text-left min-w-0"
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
                      <p className="text-[10px] text-muted-foreground/70 mt-0.5">{entry.description}</p>
                    </div>
                    {isExpanded ? <ChevronUp size={12} className="text-muted-foreground mt-0.5 shrink-0" /> : <ChevronDown size={12} className="text-muted-foreground mt-0.5 shrink-0" />}
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
