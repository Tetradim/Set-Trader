import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/stores/useStore';
import { apiFetch } from '@/lib/api';
import { uiLog } from '@/lib/clientLogger';
import { Globe, Clock, TrendingUp, RefreshCw, Info, AlertTriangle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

type MarketStatus = 'open' | 'closed' | 'lunch';

type MarketInfo = {
  code: string;
  name: string;
  flag: string;
  currency: string;
  currency_symbol: string;
  currency_note: string;
  tz_label: string;
  hours_display: string;
  status: MarketStatus;
  local_time: string;
  utc_offset?: string;
  is_open: boolean;
  yf_suffix: string;
  ticker_examples: string[];
  trading_notes: string;
  lunch_break: boolean;
  calendar_source?: string;
  calendar_reason?: string;
  is_holiday?: boolean;
  is_session_day?: boolean;
  market_open_utc?: string;
  market_close_utc?: string;
  break_start_utc?: string;
  break_end_utc?: string;
};

export function ForeignTab() {
  const [activeMarket, setActiveMarket] = useState('');
  const [markets, setMarkets] = useState<MarketInfo[]>([]);
  const [localFxRates, setLocalFxRates] = useState<Record<string, number>>({ USD: 1.0 });
  const [loading, setLoading] = useState(true);
  const [fxLoading, setFxLoading] = useState(false);

  const currencyDisplay = useStore((s) => s.currencyDisplay);
  const setCurrencyDisplay = useStore((s) => s.setCurrencyDisplay);
  const storeFxRates = useStore((s) => s.fxRates);
  const setStoreFxRates = useStore((s) => s.setFxRates);

  // Use store FX rates if available, fall back to local
  const fxRates = Object.keys(storeFxRates).length > 1 ? storeFxRates : localFxRates;

  const fetchMarkets = useCallback(async () => {
    try {
      const data = await apiFetch('/api/markets');
      const nextMarkets = (data?.markets ?? []) as MarketInfo[];
      uiLog.event('foreign.markets_loaded', { market_count: nextMarkets.length });
      setMarkets(nextMarkets);
      const nextForeignMarkets = nextMarkets.filter((market) => market.code !== 'US');
      setActiveMarket((current) => {
        if (current && nextForeignMarkets.some((market) => market.code === current)) return current;
        const firstOpen = nextForeignMarkets.find((market) => market.is_open);
        return (firstOpen ?? nextForeignMarkets[0])?.code ?? '';
      });
    } catch (err) {
      uiLog.error('foreign.markets_fetch_failed', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchFxRates = useCallback(async (showLoading = false) => {
    if (showLoading) setFxLoading(true);
    try {
      const data = await apiFetch('/api/fx-rates');
      setLocalFxRates(data.rates);
      setStoreFxRates(data.rates);
    } catch (err) {
      uiLog.error('foreign.fx_fetch_failed', err);
    } finally {
      setFxLoading(false);
    }
  }, [setStoreFxRates]);

  const toggleCurrency = useCallback(async () => {
    const newMode = currencyDisplay === 'usd' ? 'native' : 'usd';
    setCurrencyDisplay(newMode);
    try {
      await apiFetch(`/api/settings/currency-display?mode=${newMode}`, { method: 'POST' });
    } catch {
      setCurrencyDisplay(currencyDisplay); // revert on error
    }
  }, [currencyDisplay, setCurrencyDisplay]);

  useEffect(() => {
    fetchMarkets();
    fetchFxRates();
    // Load persisted preference
    apiFetch('/api/settings/currency-display')
      .then((d) => setCurrencyDisplay(d.mode))
      .catch(() => {});

    const marketTimer = setInterval(fetchMarkets, 30_000);   // refresh status every 30s
    const fxTimer    = setInterval(fetchFxRates, 5 * 60_000); // refresh FX every 5min
    return () => { clearInterval(marketTimer); clearInterval(fxTimer); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const foreignMarkets = markets.filter((market) => market.code !== 'US');
  const openMarketCount = foreignMarkets.filter((market) => market.is_open).length;
  const currentMarket = foreignMarkets.find((market) => market.code === activeMarket);

  return (
    <div className="space-y-6" data-testid="foreign-tab">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
            <Globe size={18} className="text-primary" />
            Foreign Markets
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5 max-w-xl">
            Follow global exchanges as sessions hand off across North America, Europe, Asia-Pacific, and Africa.
            Ticker cards use each market&apos;s exchange suffix, local hours, lunch window, and opening-bell rules.
          </p>
          <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
            <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5">
              {foreignMarkets.length} overseas markets
            </span>
            <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-emerald-300">
              {openMarketCount} open now
            </span>
          </div>
        </div>

        {/* Currency toggle + FX refresh */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            data-testid="fx-refresh-btn"
            onClick={() => fetchFxRates(true)}
            disabled={fxLoading}
            title="Refresh FX rates"
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          >
            <RefreshCw size={13} className={fxLoading ? 'animate-spin' : ''} />
          </button>
          <span className="text-xs text-muted-foreground">Display:</span>
          <button
            data-testid="currency-display-toggle"
            onClick={toggleCurrency}
            className={`flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-full border transition-all ${
              currencyDisplay === 'native'
                ? 'bg-amber-500/20 text-amber-400 border-amber-500/40 shadow-amber-500/10 shadow-sm'
                : 'bg-primary/20 text-primary border-primary/40 shadow-primary/10 shadow-sm'
            }`}
          >
            {currencyDisplay === 'usd' ? '$ USD' : '¤ Native'}
          </button>
        </div>
      </div>

      {/* Market sub-tabs */}
      <div className="flex items-center gap-0.5 border-b border-border overflow-x-auto pb-0 scrollbar-hide">
        {foreignMarkets.map((market) => {
          const isActive = activeMarket === market.code;
          const statusDot = market.status === 'open'   ? 'bg-emerald-400 shadow-[0_0_4px_#34d399]'
            : market.status === 'lunch'  ? 'bg-amber-400'
            : 'bg-muted-foreground/30';

          return (
            <button
              key={market.code}
              data-testid={`market-tab-${market.code}`}
              onClick={() => setActiveMarket(market.code)}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium rounded-t-lg transition-all whitespace-nowrap shrink-0 ${
                isActive
                  ? 'text-primary bg-card border border-b-0 border-border -mb-px'
                  : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
              }`}
            >
              {market.flag}{' '}
              {market.code}
              <span className={`w-1.5 h-1.5 rounded-full transition-colors ${statusDot}`} />
            </button>
          );
        })}
      </div>

      {/* Market panel */}
      <AnimatePresence mode="wait">
        {loading ? (
          <div className="flex items-center justify-center h-48 text-muted-foreground" key="loading">
            <RefreshCw size={16} className="animate-spin mr-2" />
            Loading market data...
          </div>
        ) : currentMarket ? (
          <motion.div
            key={activeMarket}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
          >
            <MarketPanel
              market={currentMarket}
              fxRates={fxRates}
              currencyDisplay={currencyDisplay}
            />
          </motion.div>
        ) : (
          <div className="text-muted-foreground text-sm text-center py-16 border border-dashed border-border rounded-xl" key="empty">
            Market data unavailable
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------

function MarketPanel({
  market, fxRates, currencyDisplay,
}: {
  market: MarketInfo;
  fxRates: Record<string, number>;
  currencyDisplay: 'usd' | 'native';
}) {
  const fxRate = fxRates?.[market.currency];
  const tickerExamples = Array.isArray(market.ticker_examples) ? market.ticker_examples : [];

  const statusStyle =
    market.status === 'open'
      ? { label: 'Open', classes: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' }
      : market.status === 'lunch'
      ? { label: 'Lunch Break', classes: 'text-amber-400 bg-amber-500/10 border-amber-500/30' }
      : { label: 'Closed', classes: 'text-muted-foreground bg-secondary/50 border-border' };

  return (
    <div className="space-y-4" data-testid={`market-panel-${market.code}`}>
      {/* Status card */}
      <div className="flex items-start gap-4 p-4 rounded-xl glass border border-border">
        <span className="text-4xl select-none">{market.flag}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-bold text-foreground">{market.name}</h3>
            <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${statusStyle.classes}`}>
              {statusStyle.label}
            </span>
          </div>
          <div className="flex items-center gap-4 mt-1.5 text-xs text-muted-foreground flex-wrap">
            <span className="flex items-center gap-1.5">
              <Clock size={11} />
              {market.local_time} {market.tz_label}
            </span>
            <span className="text-muted-foreground/60">{market.hours_display}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
            <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5">
              {market.calendar_source?.startsWith('pandas_market_calendars') ? 'Exchange calendar' : 'Local hours'}
            </span>
            {market.is_holiday && (
              <span className="rounded-full border border-red-500/20 bg-red-500/10 px-2 py-0.5 text-red-300">
                Holiday / closed
              </span>
            )}
            {market.calendar_reason && !market.is_open && (
              <span className="rounded-full border border-border bg-secondary/40 px-2 py-0.5">
                {market.calendar_reason.replace(/_/g, ' ')}
              </span>
            )}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Currency</div>
          <div className="text-sm font-bold text-foreground mt-0.5">
            {market.currency}
            <span className="text-muted-foreground font-normal ml-1">({market.currency_symbol})</span>
          </div>
          {fxRate ? (
            <div className="text-[10px] font-mono text-muted-foreground/70 mt-0.5">
              1 {market.currency} ≈ ${fxRate.toFixed(4)} USD
            </div>
          ) : (
            <div className="text-[10px] text-muted-foreground/40 mt-0.5">FX rate loading…</div>
          )}
        </div>
      </div>

      {/* UK pence warning */}
      {market.currency_note && (
        <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300">
          <AlertTriangle size={13} className="shrink-0 mt-0.5" />
          <span>{market.currency_note}</span>
        </div>
      )}

      {/* Grid: examples + notes */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Example tickers */}
        <div className="rounded-xl border border-border bg-card p-4 space-y-3">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
            <TrendingUp size={11} /> Example Tickers
          </p>
          <div className="flex flex-wrap gap-1.5">
            {tickerExamples.map((sym) => (
              <span
                key={sym}
                className="text-xs font-mono bg-secondary/60 border border-border px-2.5 py-1 rounded-lg text-foreground cursor-default select-all"
                title="Copy and paste into Add Stock"
              >
                {sym}
              </span>
            ))}
          </div>
          <p className="text-[10px] text-muted-foreground/60">
            Copy a symbol above, then use "Add Stock" in the Watchlist tab to start tracking it.
          </p>
        </div>

        {/* Trading notes */}
        <div className="rounded-xl border border-border bg-card p-4 space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
            <Info size={11} /> Trading Notes
          </p>
          <p className="text-xs text-muted-foreground leading-relaxed">{market.trading_notes}</p>
          <ul className="text-[10px] text-muted-foreground/60 space-y-1 list-disc list-inside">
            <li>Opening Bell rules use this market's open time.</li>
            {market.lunch_break && <li>Engine pauses evaluation during the lunch break window.</li>}
            {market.market_close_utc && <li>Holiday and half-day closures come from the exchange calendar when available.</li>}
            <li>Opening Bell windows are 30 min from each market's open.</li>
          </ul>
        </div>
      </div>

      {/* Currency display info */}
      <div className="rounded-xl border border-border bg-secondary/20 p-4 space-y-2">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Active Currency Display
        </p>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground">Prices shown in:</span>
          <span className={`text-xs font-bold px-2.5 py-0.5 rounded-full border ${
            currencyDisplay === 'native'
              ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
              : 'bg-primary/20 text-primary border-primary/40'
          }`}>
            {currencyDisplay === 'native'
              ? `${market.currency} (${market.currency_symbol})`
              : 'USD ($)'}
          </span>
        </div>
        {currencyDisplay === 'usd' && fxRate ? (
          <p className="text-[10px] text-muted-foreground/60">
            Prices are multiplied by the live {market.currency}/USD rate ({fxRate.toFixed(4)}) before display.
          </p>
        ) : currencyDisplay === 'native' ? (
          <p className="text-[10px] text-muted-foreground/60">
            Prices displayed as returned by the data feed in native {market.currency}.
          </p>
        ) : null}
        <p className="text-[10px] text-muted-foreground/40">
          Toggle with the "Display" button at the top. Preference is saved across restarts.
        </p>
      </div>
    </div>
  );
}
