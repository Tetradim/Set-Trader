import React, { memo, useState, useEffect, useCallback } from 'react';
import { TickerConfig, StrategyInfo } from '@/stores/useStore';
import { Brain, RefreshCw, ChevronDown, AlertCircle, CheckCircle2, Info } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { uiLog } from '@/lib/clientLogger';

/* Re-use config widgets */
import {
  ConfigSection,
  ConfigToggle,
} from './ConfigWidgets';

interface Props {
  ticker: TickerConfig;
  onFieldChange: (field: string, value: any) => void;
}

/* Parse JSON Schema types to form fields */
function SchemaFieldRenderer({
  fieldPath,
  schema,
  value,
  onChange,
}: {
  fieldPath: string;
  schema: any;
  value: any;
  onChange: (value: any) => void;
}) {
  const type = schema.type;
  const title = schema.title || fieldPath;
  const description = schema.description || '';
  const defaultValue = schema.default;

  /* Boolean checkbox */
  if (type === 'boolean') {
    return (
      <div className="flex items-center justify-between py-2">
        <div>
          <div className="text-sm text-slate-200">{title}</div>
          {description && (
            <div className="text-xs text-slate-400">{description}</div>
          )}
        </div>
        <ConfigToggle
          checked={value ?? defaultValue ?? false}
          onChange={onChange}
        />
      </div>
    );
  }

  /* Number input with min/max */
  if (type === 'number' || type === 'integer') {
    const min = schema.minimum ?? schema.exclusiveMinimum ?? -Infinity;
    const max = schema.maximum ?? schema.exclusiveMaximum ?? Infinity;
    const step = type === 'integer' ? 1 : 0.01;
    
    return (
      <div className="py-2">
        <label className="block">
          <div className="text-sm text-slate-200">{title}</div>
          {description && (
            <div className="text-xs text-slate-400">{description}</div>
          )}
        </label>
        <div className="flex items-center gap-2 mt-1">
          <input
            type="number"
            step={step}
            min={min}
            max={max}
            value={value ?? defaultValue ?? 0}
            onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
            className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-slate-400"
          />
          {(min !== -Infinity || max !== Infinity) && (
            <span className="text-xs text-slate-500">
              {min !== -Infinity && `min: ${min}`}
              {min !== -Infinity && max !== Infinity && ' | '}
              {max !== Infinity && `max: ${max}`}
            </span>
          )}
        </div>
      </div>
    );
  }

  /* String with enum (radio buttons) */
  if (type === 'string' && schema.enum) {
    return (
      <div className="py-2">
        <label className="block">
          <div className="text-sm text-slate-200">{title}</div>
          {description && (
            <div className="text-xs text-slate-400">{description}</div>
          )}
        </label>
        <div className="flex flex-wrap gap-2 mt-2">
          {schema.enum.map((opt: string) => (
            <button
              key={opt}
              type="button"
              onClick={() => onChange(opt)}
              className={`px-3 py-1.5 rounded text-sm transition-colors ${
                (value ?? defaultValue) === opt
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>
    );
  }

  /* String (text input) */
  if (type === 'string') {
    return (
      <div className="py-2">
        <label className="block">
          <div className="text-sm text-slate-200">{title}</div>
          {description && (
            <div className="text-xs text-slate-400">{description}</div>
          )}
        </label>
        <input
          type="text"
          value={value ?? defaultValue ?? ''}
          onChange={(e) => onChange(e.target.value)}
          className="w-full mt-1 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-slate-400"
        />
      </div>
    );
  }

  /* Object (nested fields - render recursively) */
  if (type === 'object' && schema.properties) {
    return (
      <div className="py-2 border-l-2 border-slate-600 pl-3">
        <div className="text-sm text-slate-300 font-medium mb-2">{title}</div>
        {Object.entries(schema.properties).map(([key, propSchema]: [string, any]) => (
          <SchemaFieldRenderer
            key={key}
            fieldPath={`${fieldPath}.${key}`}
            schema={propSchema}
            value={value?.[key]}
            onChange={(newVal) => {
              onChange({ ...value, [key]: newVal });
            }}
          />
        ))}
      </div>
    );
  }

  /* Unknown type - render as text */
  return (
    <div className="py-2">
      <label className="block">
        <div className="text-sm text-slate-200">{title}</div>
      </label>
      <input
        type="text"
        value={JSON.stringify(value ?? defaultValue ?? '')}
        onChange={(e) => {
          try {
            onChange(JSON.parse(e.target.value));
          } catch {
            onChange(e.target.value);
          }
        }}
        className="w-full mt-1 bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-slate-400"
      />
    </div>
  );
}

/* Strategy picker + schema-driven form */
export const StrategyConfigSection = memo(function StrategyConfigSection({
  ticker,
  onFieldChange,
}: Props) {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(true);
  const [helpOpen, setHelpOpen] = useState(false);

  /* Fetch strategy registry */
  useEffect(() => {
    async function loadStrategies() {
      try {
        const data = await apiFetch('/api/strategies/registry', { method: 'GET' });
        const strategyList = Object.values(data.strategies || {}) as StrategyInfo[];
        setStrategies(strategyList);
      } catch (err) {
        uiLog.error('strategies.load_failed', err);
      } finally {
        setLoading(false);
      }
    }
    loadStrategies();
  }, []);

  /* Current strategy config */
  const currentStrategy = ticker.strategy || 'RSI';
  const strategyInfo = strategies.find((s) => s.name === currentStrategy);
  const configSchema = strategyInfo?.config_schema;
  const strategyConfig = ticker.strategy_config || {};

  /* Handle individual field changes */
  const handleFieldChange = useCallback((key: string, value: any) => {
    const newConfig = { ...strategyConfig, [key]: value };
    onFieldChange('strategy_config', newConfig);
  }, [strategyConfig, onFieldChange]);

  /* Handle strategy selection */
  const handleStrategyChange = useCallback((strategyName: string) => {
    onFieldChange('strategy', strategyName);
    /* Reset strategy_config when strategy changes */
    onFieldChange('strategy_config', {});
    setHelpOpen(false);
  }, [onFieldChange]);

  return (
    <ConfigSection title="Strategy" icon={Brain} color="text-purple-400" expanded={expanded} onToggle={() => setExpanded(!expanded)}>
      {loading ? (
        <div className="flex items-center gap-2 py-3 text-slate-400">
          <RefreshCw className="w-4 h-4 animate-spin" />
          <span className="text-sm">Loading strategies...</span>
        </div>
      ) : (
        <>
          {/* Strategy Picker */}
          <div className="py-2">
            <div className="flex items-center justify-between gap-2">
              <label className="block">
                <span className="text-sm text-slate-200">Active Strategy</span>
              </label>
              {strategyInfo && (
                <button
                  type="button"
                  data-testid="strategy-help-toggle"
                  onClick={() => setHelpOpen((open) => !open)}
                  className="inline-flex items-center gap-1 rounded-full border border-purple-400/30 bg-purple-500/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-purple-200 hover:border-purple-300 hover:bg-purple-500/20"
                  aria-expanded={helpOpen}
                  aria-controls="strategy-help-panel"
                >
                  <Info className="h-3 w-3" />
                  Info
                </button>
              )}
            </div>
            <div className="relative mt-1">
              <select
                value={currentStrategy}
                onChange={(e) => handleStrategyChange(e.target.value)}
                className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-slate-200 appearance-none focus:outline-none focus:border-slate-400"
              >
                <option value="">None (manual)</option>
                {strategies.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
            </div>
            {strategyInfo && helpOpen && (
              <div
                id="strategy-help-panel"
                data-testid="strategy-help-panel"
                className="mt-2 rounded-lg border border-purple-400/20 bg-purple-500/10 p-3 text-xs text-slate-200"
              >
                <div className="font-semibold text-purple-200">{strategyInfo.name}</div>
                <p className="mt-1 leading-relaxed text-slate-300">{strategyInfo.description}</p>
                {strategyInfo.tags?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {strategyInfo.tags.map((tag) => (
                      <span key={tag} className="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-300">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Strategy metadata */}
          {strategyInfo && (
            <div className="flex flex-wrap items-center gap-2 py-2 text-xs text-slate-400">
              <span className="px-2 py-0.5 bg-slate-700 rounded">
                v{strategyInfo.version}
              </span>
              <span className="px-2 py-0.5 bg-slate-700 rounded">
                {strategyInfo.risk_level}
              </span>
              <span className="flex min-w-0 items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                <span className="truncate">{strategyInfo.tags?.join(', ')}</span>
              </span>
            </div>
          )}

          {/* Schema-driven form fields */}
          {configSchema && configSchema.properties && (
            <div className="mt-3 border-t border-slate-700 pt-3">
              <div className="text-sm text-slate-300 font-medium mb-2">
                Parameters
              </div>
              {Object.entries(configSchema.properties).map(([key, propSchema]: [string, any]) => (
                <SchemaFieldRenderer
                  key={key}
                  fieldPath={key}
                  schema={propSchema}
                  value={strategyConfig[key]}
                  onChange={(val) => handleFieldChange(key, val)}
                />
              ))}
            </div>
          )}

          {/* No parameters message */}
          {currentStrategy && !configSchema && (
            <div className="flex items-center gap-2 py-3 text-sm text-slate-400">
              <AlertCircle className="w-4 h-4" />
              <span>No configurable parameters</span>
            </div>
          )}
        </>
      )}
    </ConfigSection>
  );
});
