import { useState, useCallback, useRef } from 'react';
import { useStore } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { TickerCard } from '@/components/TickerCard';
import { ConfigModal } from '@/components/ConfigModal';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  rectSortingStrategy,
} from '@dnd-kit/sortable';
import { apiFetch } from '@/lib/api';
import { toast } from 'sonner';

// ── Tunnel SVG backgrounds per card state ────────────────────────────────────
export function TunnelSVG({ color }: { color: 'gold' | 'red' | 'amber' | 'blue' }) {
  const configs = {
    gold:  { core: '#c87808', mid: '#8a5005', glow: '#ffd060', line: 'rgba(200,140,8,0.5)',  frame: 'rgba(220,160,10,0.45)' },
    red:   { core: '#a01018', mid: '#600808', glow: '#ff6070', line: 'rgba(192,40,46,0.5)',  frame: 'rgba(220,50,60,0.45)'  },
    amber: { core: '#b87808', mid: '#704805', glow: '#e0a820', line: 'rgba(190,130,8,0.45)', frame: 'rgba(210,150,10,0.4)'  },
    blue:  { core: '#1840a0', mid: '#0c2060', glow: '#6090e0', line: 'rgba(77,130,220,0.45)',frame: 'rgba(100,150,240,0.4)' },
  };
  const c = configs[color];
  const id = `tg-${color}`;
  const id2 = `tg2-${color}`;
  return (
    <svg viewBox="0 0 200 215" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice" style={{ position:'absolute', top:0, left:0, width:'100%', height:'100%' }}>
      <defs>
        <radialGradient id={id} cx="50%" cy="50%" r="55%">
          <stop offset="0%"   stopColor={c.core} stopOpacity="0.9" />
          <stop offset="30%"  stopColor={c.mid}  stopOpacity="0.7" />
          <stop offset="70%"  stopColor="#2a1802" stopOpacity="0.5" />
          <stop offset="100%" stopColor="#050204" stopOpacity="0.9" />
        </radialGradient>
        <radialGradient id={id2} cx="50%" cy="50%" r="28%">
          <stop offset="0%"   stopColor={c.glow} stopOpacity="0.7" />
          <stop offset="100%" stopColor={c.core} stopOpacity="0"   />
        </radialGradient>
      </defs>
      <rect width="200" height="215" fill="#050204" />
      <rect width="200" height="215" fill={`url(#${id})`} />
      {/* Corridor lines */}
      {[[100,107,0,0],[100,107,200,0],[100,107,0,215],[100,107,200,215],
        [100,107,0,107],[100,107,200,107],[100,107,100,0],[100,107,100,215]
      ].map(([x1,y1,x2,y2], i) => (
        <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={i < 4 ? c.line : c.line.replace('0.5','0.32')} strokeWidth={i < 4 ? 1 : 0.8} />
      ))}
      {/* Nested square frames */}
      {[[70,77,60,60],[50,57,100,100],[30,37,140,140],[10,17,180,180]].map(([x,y,w,h], i) => (
        <rect key={i} x={x} y={y} width={w} height={h} fill="none" stroke={c.frame} strokeWidth={i === 0 ? 1 : 0.8} strokeOpacity={1 - i * 0.2} />
      ))}
      {/* Bright center */}
      <rect width="200" height="215" fill={`url(#${id2})`} />
      {/* Corner tech marks */}
      <rect x="0"   y="0"   width="18" height="2" fill={c.frame} />
      <rect x="0"   y="0"   width="2"  height="18" fill={c.frame} />
      <rect x="182" y="0"   width="18" height="2" fill={c.frame} />
      <rect x="198" y="0"   width="2"  height="18" fill={c.frame} />
      {/* Readability overlay */}
      <rect width="200" height="215" fill="rgba(4,2,8,0.38)" />
    </svg>
  );
}

// ── Market color state ────────────────────────────────────────────────────────
const SWATCH_COLORS = ['#dca828','#2dd4a0','#4d82dc','#e03040','#c84afa','#f97316'];
const DEFAULT_MKT_COLORS: Record<string, string> = {
  NYSE: '#dca828', NASDAQ: '#2dd4a0', LSE: '#4d82dc', Crypto: '#c84afa',
};

// ── WatchlistTab ─────────────────────────────────────────────────────────────
export function WatchlistTab() {
  const { send }       = useWebSocket();
  const tickers        = useStore((s) => s.tickers);
  const profits        = useStore((s) => s.profits);
  const prices         = useStore((s) => s.prices);
  const accountBalance = useStore((s) => s.accountBalance);
  const allocated      = useStore((s) => s.allocated);
  const available      = useStore((s) => s.available);

  const [configSymbol, setConfigSymbol] = useState<string | null>(null);
  const [activePanel, setActivePanel]   = useState<'trades'|'positions'|'controls'|'broker'>('trades');
  const [pickerOpen, setPickerOpen]     = useState(false);
  const [mktColors, setMktColors]       = useState(DEFAULT_MKT_COLORS);
  const [toggles, setToggles]           = useState({ sim247: false, liveMarket: true, paperAfter: true, stopLoss: true, trailing: false });

  const simulate247           = useStore((s) => s.simulate247);
  const liveDuringMarketHours = useStore((s) => s.liveDuringMarketHours);
  const paperAfterHours       = useStore((s) => s.paperAfterHours);
  const trades                = useStore((s) => s.trades);
  const running               = useStore((s) => s.running);

  const totalPnl = Object.values(profits).reduce((a, b) => a + b, 0);
  const localAllocated = Object.values(tickers).reduce((s, t) => s + (t.base_power ?? 0), 0);
  const effectiveAllocated = localAllocated || allocated;
  const effectiveAvailable = accountBalance - effectiveAllocated;

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    
    // Get fresh tickers from store instead of closure
    const currentTickers = useStore.getState().tickers;
    const symbols = Object.values(currentTickers)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((t) => t.symbol);
    const from = symbols.indexOf(active.id as string);
    const to   = symbols.indexOf(over.id as string);
    if (from === -1 || to === -1) return;
    const reordered = [...symbols];
    reordered.splice(to, 0, reordered.splice(from, 1)[0]);
    try {
      await apiFetch('/api/tickers/reorder', { method: 'POST', body: JSON.stringify({ symbols: reordered }) });
    } catch { toast.error('Failed to reorder tickers'); }
  }, []); // Empty deps - gets fresh state internally

  const sortedSymbols = Object.values(tickers)
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((t) => t.symbol);

  // Decide tunnel color per card
  function tunnelColor(symbol: string): 'gold' | 'red' | 'amber' | 'blue' {
    const t = tickers[symbol];
    if (!t?.enabled) return 'amber';
    if (t.strategy === 'paper' || !t.enabled) return 'blue';
    const pnl = profits[symbol] ?? 0;
    if (pnl < 0) return 'red';
    return 'gold';
  }

  function cardSheen(symbol: string): string {
    const color = tunnelColor(symbol);
    return `sp-sheen-${color === 'amber' ? 'amber' : color === 'red' ? 'red' : color === 'blue' ? 'blue' : 'gold'}`;
  }

  const marketItems = [
    { key: 'NYSE',   status: 'open',   label: 'Open' },
    { key: 'NASDAQ', status: 'open',   label: 'Open' },
    { key: 'LSE',    status: 'closed', label: 'Closed' },
    { key: 'Crypto', status: 'open',   label: '24/7' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* ── STAT CARDS ── */}
      <div className="sp-stat-grid">
        {[
          { label: 'Account Balance', value: `$${accountBalance.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`, variant: 'gold',   sub: '↑ +$312.50 today', subVariant: 'green'  },
          { label: 'Allocated',       value: `$${effectiveAllocated.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`, variant: 'silver', sub: `${accountBalance > 0 ? ((effectiveAllocated/accountBalance)*100).toFixed(1) : 0}% deployed`, subVariant: 'silver' },
          { label: 'Available Cash',  value: `$${effectiveAvailable.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}`, variant: 'green',  sub: 'Cash reserve', subVariant: 'dim'  },
          { label: 'Total P&L',       value: `${totalPnl >= 0 ? '+' : ''}$${Math.abs(totalPnl).toFixed(2)}`, variant: 'green', sub: 'Win rate 68%', subVariant: 'green' },
        ].map(({ label, value, variant, sub, subVariant }) => (
          <div className="sp-stat-card" key={label}>
            <div className="sp-stat-bg" />
            <div className="sp-stat-glow" />
            <div className="sp-stat-sheen" />
            <div className="sp-stat-content">
              <div className={`sp-stat-lbl ${variant}`}>{label}</div>
              <div className={`sp-stat-val ${variant}`}>{value}</div>
              <div className={`sp-stat-sub ${subVariant}`}>{sub}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── MARKET STRIP ── */}
      <div className="sp-mkt-wrap">
        <div className="sp-mkt-strip">
          {marketItems.map(({ key, status, label }) => (
            <div
              key={key}
              className="sp-mkt-item"
              onClick={() => setPickerOpen(!pickerOpen)}
            >
              <div className="sp-mkt-name">{key}</div>
              <div className={`sp-mkt-status ${status}`}>● {label}</div>
              <div className="sp-mkt-dot" style={{ background: mktColors[key] || '#dca828' }} />
            </div>
          ))}
          <div className="sp-mkt-item">
            <div className="sp-mkt-name">Session</div>
            <div className="sp-mkt-status pre">Pre-Market</div>
          </div>
          <div className="sp-mkt-item" style={{ cursor: 'default' }}>
            <div className="sp-mkt-time" id="watchlist-clock">--:--:-- ET</div>
            <div className="sp-mkt-date">{new Date().toLocaleDateString('en-US',{weekday:'long',year:'numeric',month:'long',day:'numeric'})}</div>
          </div>
        </div>

        {/* Color picker */}
        <div className={`sp-mkt-picker ${pickerOpen ? 'open' : ''}`}>
          <div className="sp-picker-title">Market Color Code — click a market to assign</div>
          {marketItems.map(({ key }) => (
            <div className="sp-picker-row" key={key}>
              <span className="sp-picker-label">{key}</span>
              <div className="sp-picker-swatches">
                {SWATCH_COLORS.map((color) => (
                  <div
                    key={color}
                    className={`sp-picker-swatch ${mktColors[key] === color ? 'selected' : ''}`}
                    style={{ background: color }}
                    onClick={() => setMktColors(prev => ({ ...prev, [key]: color }))}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── ACTIVE TICKERS ── */}
      <div>
        <div className="sp-sec-hdr">
          <div className="sp-sec-title">Active Tickers</div>
          <div className="sp-sec-line" />
          <button className="sp-sec-action">Manage ↗</button>
        </div>

        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={sortedSymbols} strategy={rectSortingStrategy}>
            <div className="sp-ticker-grid">
              {sortedSymbols.map((symbol) => {
                const t = tickers[symbol];
                if (!t) return null; // skip invalid tickers
                return (
                <ErrorBoundary key={symbol} fallbackLabel={`${symbol} failed`}>
                  <TickerCard
                    ticker={t}
                    onConfigOpen={(s) => setConfigSymbol(s)}
                    tunnelColor={tunnelColor(symbol)}
                    cardSheen={cardSheen(symbol)}
                  />
                </ErrorBoundary>
                );
              })}

              {/* Add ticker placeholder */}
              <div className="sp-add-ticker">
                <span style={{ fontSize: 22, lineHeight: 1 }}>+</span>
                <span style={{ fontSize: 8, letterSpacing: '.2em', textTransform: 'uppercase', fontFamily: "'JetBrains Mono',monospace" }}>
                  Add Ticker
                </span>
              </div>
            </div>
          </SortableContext>
        </DndContext>
      </div>

      {/* ── BOTTOM PANEL — tab inside a tab ── */}
      <div className="sp-panel-wrap">
        <div className="sp-subtabs">
          {(['trades','positions','controls','broker'] as const).map((panel) => (
            <button
              key={panel}
              className={`sp-subtab ${activePanel === panel ? 'active' : ''}`}
              onClick={() => setActivePanel(panel)}
            >
              {panel === 'trades'    ? 'Trade Log'    :
               panel === 'positions' ? 'Positions'    :
               panel === 'controls'  ? 'Bot Controls' : 'Broker'}
            </button>
          ))}
        </div>

        {/* TRADE LOG */}
        <div className={`sp-panel ${activePanel === 'trades' ? 'active' : ''}`}>
          <div className="sp-trade-hdr">
            <div>Symbol</div><div>Side</div><div>Time</div>
            <div className="sp-col-r">Price</div><div className="sp-col-r">P&L</div><div className="sp-col-r">Status</div>
          </div>
          {trades.slice(0, 20).map((trade) => (
            <div className="sp-trade-row" key={trade.id}>
              <div className="sp-trade-sym">{trade.symbol}</div>
              <div>
                {trade.side === 'BUY'
                  ? <span className="sp-trade-buy">BUY</span>
                  : <span className="sp-trade-sell">{trade.side}</span>
                }
              </div>
              <div className="sp-trade-time">{new Date(trade.timestamp).toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'})}</div>
              <div className="sp-trade-price">${trade.price.toFixed(2)}</div>
              <div className={`sp-trade-pnl ${trade.pnl >= 0 ? 'p' : 'n'}`}>
                {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(2)}
              </div>
              <div className="sp-trade-status">FILLED</div>
            </div>
          ))}
          {trades.length === 0 && <div className="sp-empty">No trades yet — bot activity will appear here in real-time</div>}
        </div>

        {/* POSITIONS */}
        <div className={`sp-panel ${activePanel === 'positions' ? 'active' : ''}`}>
          <div className="sp-empty">No open positions — connect Alpaca to populate live data</div>
        </div>

        {/* BOT CONTROLS */}
        <div className={`sp-panel ${activePanel === 'controls' ? 'active' : ''}`}>
          <div className="sp-ctrl-grid">
            <div>
              <div className="sp-ctrl-lbl">Bot State</div>
              <div className="sp-ctrl-btns">
                <button className="sp-ctrl-btn sp-btn-start" onClick={() => send('START_BOT')}>▶ Start All</button>
                <button className="sp-ctrl-btn sp-btn-pause" onClick={() => send('PAUSE_BOT')}>⏸ Pause</button>
                <button className="sp-ctrl-btn sp-btn-stop"  onClick={() => send('STOP_BOT')}>⏹ Stop</button>
              </div>
            </div>
            <div>
              <div className="sp-ctrl-lbl">Trading Mode</div>
              <div className="sp-ctrl-btns">
                <button className="sp-ctrl-btn sp-btn-pause" onClick={() => send('SET_MODE', { mode: 'paper' })}>Paper</button>
                <button className="sp-ctrl-btn sp-btn-stop"  onClick={() => send('SET_MODE', { mode: 'live'  })}>Live</button>
              </div>
            </div>
          </div>
          <div className="sp-toggle-list">
            {[
              { key: 'sim247',     label: 'Simulate 24/7',           action: 'SET_SIMULATE_247',            val: simulate247            },
              { key: 'liveMarket', label: 'Live During Market Hours', action: 'SET_LIVE_DURING_MARKET_HOURS', val: liveDuringMarketHours  },
              { key: 'paperAfter', label: 'Paper After Hours',        action: 'SET_PAPER_AFTER_HOURS',        val: paperAfterHours        },
              { key: 'stopLoss',   label: 'Stop Loss Enabled',        action: null,                           val: toggles.stopLoss       },
              { key: 'trailing',   label: 'Trailing Stop',            action: null,                           val: toggles.trailing       },
            ].map(({ key, label, action, val }) => (
              <div className="sp-toggle-row" key={key}>
                <div className="sp-toggle-name">{label}</div>
                <div
                  className={`sp-toggle ${val ? 'on' : ''}`}
                  onClick={() => {
                    if (action) send(action, { value: !val });
                    else setToggles(prev => ({ ...prev, [key]: !prev[key as keyof typeof prev] }));
                  }}
                />
              </div>
            ))}
          </div>
        </div>

        {/* BROKER */}
        <div className={`sp-panel ${activePanel === 'broker' ? 'active' : ''}`}>
          <div className="sp-empty">Broker configuration — API keys and connection settings</div>
        </div>
      </div>

      {/* Config modal */}
      {configSymbol && tickers[configSymbol] && (
        <ErrorBoundary fallbackLabel="Config modal failed">
          <ConfigModal
            symbol={configSymbol}
            onClose={() => setConfigSymbol(null)}
          />
        </ErrorBoundary>
      )}
    </div>
  );
}
