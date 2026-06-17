import { useEffect, useState } from 'react';
import { Plug } from 'lucide-react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { uiLog } from '@/lib/clientLogger';
import type { TickerConfig } from '@/stores/useStore';
import { useStore } from '@/stores/useStore';

interface BrokerMeta {
  id: string;
  name: string;
  color: string;
}

export function BrokerAllocationsSection() {
  const tickersMap = useStore((s) => s.tickers);
  const tickers = Object.values(tickersMap);
  const updateTicker = useStore((s) => s.updateTicker);
  const [brokers, setBrokers] = useState<BrokerMeta[]>([]);
  const [baseEditValues, setBaseEditValues] = useState<Record<string, string>>({});
  const [brokerEditValues, setBrokerEditValues] = useState<Record<string, Record<string, string>>>({});

  useEffect(() => {
    async function loadBrokers() {
      try {
        const data: any[] = await apiFetch('/api/brokers');
        setBrokers(data.filter((broker) => broker.supported).map((broker) => ({ id: broker.id, name: broker.name, color: broker.color })));
      } catch (error) {
        uiLog.error('settings.brokers_load_failed', error, { retrying: true });
        setTimeout(async () => {
          try {
            const data: any[] = await apiFetch('/api/brokers');
            setBrokers(data.filter((broker) => broker.supported).map((broker) => ({ id: broker.id, name: broker.name, color: broker.color })));
          } catch (retryError) {
            uiLog.error('settings.brokers_load_retry_failed', retryError);
          }
        }, 2000);
      }
    }
    loadBrokers();
  }, []);

  const tickerAllocationKey = tickers.map((ticker) => `${ticker.symbol}:${ticker.base_power}:${(ticker.broker_ids || []).join(',')}:${JSON.stringify(ticker.broker_allocations || {})}`).join('|');

  useEffect(() => {
    const nextBaseValues: Record<string, string> = {};
    const nextBrokerValues: Record<string, Record<string, string>> = {};
    tickers.forEach((ticker) => {
      nextBaseValues[ticker.symbol] = String(ticker.base_power ?? 0);
      nextBrokerValues[ticker.symbol] = {};
      (ticker.broker_ids || []).forEach((brokerId) => {
        nextBrokerValues[ticker.symbol][brokerId] = String((ticker.broker_allocations || {})[brokerId] ?? 0);
      });
    });
    setBaseEditValues(nextBaseValues);
    setBrokerEditValues(nextBrokerValues);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickerAllocationKey]);

  const persistTickerUpdate = async (symbol: string, updates: Partial<TickerConfig>, rollback: Partial<TickerConfig>) => {
    updateTicker(symbol, updates);
    try {
      const saved = await apiFetch(`/api/tickers/${encodeURIComponent(symbol)}`, {
        method: 'PUT',
        body: JSON.stringify(updates),
      });
      updateTicker(symbol, saved);
      return saved;
    } catch (error: any) {
      updateTicker(symbol, rollback);
      throw error;
    }
  };

  const handleBaseChange = (symbol: string, raw: string) => {
    if (/^\d*\.?\d*$/.test(raw)) {
      setBaseEditValues((prev) => ({ ...prev, [symbol]: raw }));
    }
  };

  const handleBaseBlur = async (symbol: string) => {
    const raw = baseEditValues[symbol] ?? '0';
    const amount = parseFloat(raw);
    if (Number.isNaN(amount) || amount < 0) return;
    const ticker = tickers.find((item) => item.symbol === symbol);
    if (!ticker) return;
    const previousBasePower = ticker.base_power ?? 0;
    try {
      await persistTickerUpdate(symbol, { base_power: amount }, { base_power: previousBasePower });
      uiLog.event('settings.base_allocation_update', { symbol, amount });
      toast.success(`${symbol}: buy power = $${amount.toFixed(2)}`);
    } catch (error: any) {
      setBaseEditValues((prev) => ({ ...prev, [symbol]: String(previousBasePower) }));
      toast.error(error.message || `Failed to update ${symbol} allocation`);
    }
  };

  const handleBrokerChange = (symbol: string, brokerId: string, raw: string) => {
    if (/^\d*\.?\d*$/.test(raw)) {
      setBrokerEditValues((prev) => ({ ...prev, [symbol]: { ...prev[symbol], [brokerId]: raw } }));
    }
  };

  const handleBrokerBlur = async (symbol: string, brokerId: string) => {
    const raw = brokerEditValues[symbol]?.[brokerId] ?? '0';
    const amount = parseFloat(raw);
    if (Number.isNaN(amount) || amount < 0) return;
    const ticker = tickers.find((item) => item.symbol === symbol);
    if (!ticker) return;
    const brokerAllocations = { ...(ticker.broker_allocations || {}), [brokerId]: amount };
    const basePower = Object.values(brokerAllocations).reduce((sum, value) => sum + value, 0);
    const previousBrokerAllocations = ticker.broker_allocations || {};
    const previousBasePower = ticker.base_power ?? 0;
    try {
      await persistTickerUpdate(
        symbol,
        { broker_allocations: brokerAllocations, base_power: basePower },
        { broker_allocations: previousBrokerAllocations, base_power: previousBasePower },
      );
      setBaseEditValues((prev) => ({ ...prev, [symbol]: String(basePower) }));
      uiLog.event('settings.broker_allocation_update', { symbol, broker_id: brokerId, amount, total: basePower });
      toast.success(`${symbol}: ${brokerId} = $${amount.toFixed(2)} (total: $${basePower.toFixed(2)})`);
    } catch (error: any) {
      setBrokerEditValues((prev) => ({
        ...prev,
        [symbol]: { ...prev[symbol], [brokerId]: String(previousBrokerAllocations[brokerId] ?? 0) },
      }));
      setBaseEditValues((prev) => ({ ...prev, [symbol]: String(previousBasePower) }));
      toast.error(error.message || `Failed to update ${symbol} broker allocation`);
    }
  };

  return (
    <section className="glass rounded-xl border border-border p-6 space-y-5" data-testid="broker-allocations-section">
      <SectionHeading />
      <p className="text-xs text-muted-foreground">
        Add or remove buy power for every Watchlist ticker. Broker-assigned tickers can also split that allocation per broker.
      </p>
      <div className="space-y-4">
        {tickers.map((ticker) => (
          <TickerAllocationCard
            key={ticker.symbol}
            ticker={ticker}
            brokers={brokers}
            baseValue={baseEditValues[ticker.symbol] ?? String(ticker.base_power ?? 0)}
            brokerEditValues={brokerEditValues}
            onBaseChange={handleBaseChange}
            onBaseBlur={handleBaseBlur}
            onBrokerChange={handleBrokerChange}
            onBrokerBlur={handleBrokerBlur}
          />
        ))}
      </div>
    </section>
  );
}

function SectionHeading() {
  return (
    <div className="flex items-center gap-2 mb-2">
      <Plug size={18} className="text-primary" />
      <h3 className="text-sm font-bold text-foreground">Broker Allocations</h3>
    </div>
  );
}

function TickerAllocationCard({
  ticker,
  brokers,
  baseValue,
  brokerEditValues,
  onBaseChange,
  onBaseBlur,
  onBrokerChange,
  onBrokerBlur,
}: {
  ticker: TickerConfig;
  brokers: BrokerMeta[];
  baseValue: string;
  brokerEditValues: Record<string, Record<string, string>>;
  onBaseChange: (symbol: string, value: string) => void;
  onBaseBlur: (symbol: string) => void;
  onBrokerChange: (symbol: string, brokerId: string, value: string) => void;
  onBrokerBlur: (symbol: string, brokerId: string) => void;
}) {
  const allocation = ticker.broker_allocations || {};
  const brokerTotal = Object.values(allocation).reduce((sum: number, value) => sum + value, 0);
  const baseAmount = ticker.base_power ?? brokerTotal;
  const assignedBrokers = (ticker.broker_ids || []).map((brokerId) => (
    brokers.find((broker) => broker.id === brokerId) || { id: brokerId, name: brokerId, color: '#64748b' }
  ));

  return (
    <div className="border border-border rounded-lg overflow-hidden" data-testid={`alloc-ticker-${ticker.symbol}`}>
      <div className="flex items-center justify-between bg-secondary/30 px-4 py-2 border-b border-border">
        <span className="text-sm font-bold text-foreground font-mono">{ticker.symbol}</span>
        <span className="text-xs font-mono text-primary font-bold">Buy Power: ${baseAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
      </div>
      <div className="divide-y divide-border">
        <div className="flex items-center gap-3 px-4 py-2.5" data-testid={`alloc-base-row-${ticker.symbol}`}>
          <div className="w-1.5 h-6 rounded-full shrink-0 bg-primary" />
          <span className="text-xs font-medium text-foreground min-w-[120px]">Ticker buy power</span>
          <div className="flex items-center gap-1.5 flex-1">
            <span className="text-muted-foreground text-xs">$</span>
            <input
              data-testid={`alloc-base-input-${ticker.symbol}`}
              type="text"
              inputMode="decimal"
              value={baseValue}
              onChange={(event) => onBaseChange(ticker.symbol, event.target.value)}
              onBlur={() => onBaseBlur(ticker.symbol)}
              onKeyDown={(event) => { if (event.key === 'Enter') onBaseBlur(ticker.symbol); }}
              className="w-24 bg-secondary border border-border rounded-md px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
            />
          </div>
          <span className="text-[10px] font-mono text-muted-foreground min-w-[80px] text-right">
            {assignedBrokers.length > 0 ? `Broker split: $${brokerTotal.toFixed(2)}` : 'No broker split'}
          </span>
        </div>
        {assignedBrokers.map((broker) => {
          const value = brokerEditValues[ticker.symbol]?.[broker.id] ?? String(allocation[broker.id] ?? 0);
          const amount = parseFloat(value) || 0;
          const percent = brokerTotal > 0 ? ((amount / brokerTotal) * 100).toFixed(0) : '0';
          return (
            <div key={broker.id} className="flex items-center gap-3 px-4 py-2.5" data-testid={`alloc-row-${ticker.symbol}-${broker.id}`}>
              <div className="w-1.5 h-6 rounded-full shrink-0" style={{ backgroundColor: broker.color }} />
              <span className="text-xs font-medium text-foreground min-w-[120px]">{broker.name}</span>
              <div className="flex items-center gap-1.5 flex-1">
                <span className="text-muted-foreground text-xs">$</span>
                <input
                  data-testid={`alloc-input-${ticker.symbol}-${broker.id}`}
                  type="text"
                  inputMode="decimal"
                  value={value}
                  onChange={(event) => onBrokerChange(ticker.symbol, broker.id, event.target.value)}
                  onBlur={() => onBrokerBlur(ticker.symbol, broker.id)}
                  onKeyDown={(event) => { if (event.key === 'Enter') onBrokerBlur(ticker.symbol, broker.id); }}
                  className="w-24 bg-secondary border border-border rounded-md px-2 py-1 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
                />
              </div>
              <div className="flex items-center gap-2 min-w-[80px]">
                <div className="flex-1 h-1.5 bg-secondary rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all" style={{ width: `${percent}%`, backgroundColor: broker.color }} />
                </div>
                <span className="text-[10px] font-mono text-muted-foreground w-8 text-right">{percent}%</span>
              </div>
            </div>
          );
        })}
        {assignedBrokers.length === 0 && (
          <div className="px-4 py-2.5 text-[11px] text-muted-foreground">
            This ticker has no broker assignment. Its buy power is still used for paper/unassigned allocation.
          </div>
        )}
      </div>
    </div>
  );
}
