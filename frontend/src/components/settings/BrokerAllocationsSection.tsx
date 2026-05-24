import { useEffect, useState } from 'react';
import { Plug } from 'lucide-react';
import { toast } from 'sonner';
import { useWebSocket } from '@/hooks/useWebSocket';
import { apiFetch } from '@/lib/api';
import { uiLog } from '@/lib/clientLogger';
import { useStore } from '@/stores/useStore';

interface BrokerMeta {
  id: string;
  name: string;
  color: string;
}

export function BrokerAllocationsSection() {
  const tickersMap = useStore((s) => s.tickers);
  const tickers = Object.values(tickersMap);
  const { send } = useWebSocket();
  const [brokers, setBrokers] = useState<BrokerMeta[]>([]);
  const [editValues, setEditValues] = useState<Record<string, Record<string, string>>>({});

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

  const tickerBrokerKey = tickers.map((ticker) => `${ticker.symbol}:${(ticker.broker_ids || []).join(',')}:${JSON.stringify(ticker.broker_allocations || {})}`).join('|');

  useEffect(() => {
    const nextValues: Record<string, Record<string, string>> = {};
    tickers.forEach((ticker) => {
      nextValues[ticker.symbol] = {};
      (ticker.broker_ids || []).forEach((brokerId) => {
        nextValues[ticker.symbol][brokerId] = String((ticker.broker_allocations || {})[brokerId] ?? 0);
      });
    });
    setEditValues(nextValues);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickerBrokerKey]);

  const tickersWithBrokers = tickers.filter((ticker) => (ticker.broker_ids || []).length > 0);

  const handleChange = (symbol: string, brokerId: string, raw: string) => {
    if (/^\d*\.?\d*$/.test(raw)) {
      setEditValues((prev) => ({ ...prev, [symbol]: { ...prev[symbol], [brokerId]: raw } }));
    }
  };

  const handleBlur = (symbol: string, brokerId: string) => {
    const raw = editValues[symbol]?.[brokerId] ?? '0';
    const amount = parseFloat(raw);
    if (Number.isNaN(amount) || amount < 0) return;
    const ticker = tickers.find((item) => item.symbol === symbol);
    if (!ticker) return;
    const brokerAllocations = { ...(ticker.broker_allocations || {}), [brokerId]: amount };
    const basePower = Object.values(brokerAllocations).reduce((sum, value) => sum + value, 0);
    uiLog.event('settings.broker_allocation_update', { symbol, broker_id: brokerId, amount, total: basePower });
    send('UPDATE_TICKER', { symbol, broker_allocations: brokerAllocations, base_power: basePower });
    toast.success(`${symbol}: ${brokerId} = $${amount.toFixed(2)} (total: $${basePower.toFixed(2)})`);
  };

  if (tickersWithBrokers.length === 0) {
    return (
      <section className="glass rounded-xl border border-border p-6 space-y-3">
        <SectionHeading />
        <p className="text-xs text-muted-foreground">
          Assign brokers to ticker cards first, then set custom buy power per broker here.
        </p>
      </section>
    );
  }

  return (
    <section className="glass rounded-xl border border-border p-6 space-y-5" data-testid="broker-allocations-section">
      <SectionHeading />
      <p className="text-xs text-muted-foreground">
        Set custom buy power per broker for each ticker. Total buy power equals the sum of all broker allocations.
      </p>
      <div className="space-y-4">
        {tickersWithBrokers.map((ticker) => (
          <TickerAllocationCard
            key={ticker.symbol}
            ticker={ticker}
            brokers={brokers}
            editValues={editValues}
            onChange={handleChange}
            onBlur={handleBlur}
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
  editValues,
  onChange,
  onBlur,
}: {
  ticker: any;
  brokers: BrokerMeta[];
  editValues: Record<string, Record<string, string>>;
  onChange: (symbol: string, brokerId: string, value: string) => void;
  onBlur: (symbol: string, brokerId: string) => void;
}) {
  const allocation = ticker.broker_allocations || {};
  const total = Object.values(allocation).reduce((sum: number, value: any) => sum + value, 0);
  const assignedBrokers = (ticker.broker_ids || []).map((brokerId: string) => brokers.find((broker) => broker.id === brokerId)).filter(Boolean) as BrokerMeta[];

  return (
    <div className="border border-border rounded-lg overflow-hidden" data-testid={`alloc-ticker-${ticker.symbol}`}>
      <div className="flex items-center justify-between bg-secondary/30 px-4 py-2 border-b border-border">
        <span className="text-sm font-bold text-foreground font-mono">{ticker.symbol}</span>
        <span className="text-xs font-mono text-primary font-bold">Total: ${total.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
      </div>
      <div className="divide-y divide-border">
        {assignedBrokers.map((broker) => {
          const value = editValues[ticker.symbol]?.[broker.id] ?? String(allocation[broker.id] ?? 0);
          const amount = parseFloat(value) || 0;
          const percent = total > 0 ? ((amount / total) * 100).toFixed(0) : '0';
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
                  onChange={(event) => onChange(ticker.symbol, broker.id, event.target.value)}
                  onBlur={() => onBlur(ticker.symbol, broker.id)}
                  onKeyDown={(event) => { if (event.key === 'Enter') onBlur(ticker.symbol, broker.id); }}
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
      </div>
    </div>
  );
}
