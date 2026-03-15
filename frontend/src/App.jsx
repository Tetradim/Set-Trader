import React, { useState, useEffect } from 'react';
import { StatusHeader } from './components/StatusHeader';
import { TickerCard } from './components/TickerCard';
import { AddTickerModal } from './components/AddTickerModal';

function App() {
  const [botState, setBotState] = useState({ tickers: {}, connected: false, paused: false });

  const fetchState = async () => {
    try {
      const res = await fetch('http://localhost:8000/state');
      const data = await res.json();
      setBotState(data);
    } catch (e) { 
      console.error("Backend offline. Make sure main.py is running on port 8000."); 
    }
  };

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <StatusHeader statusData={{ 
        connected: botState.connected, 
        market_open: true, 
        paused: botState.paused,
        total_profit: 0 
      }} />

      <main className="max-w-7xl mx-auto p-6">
        <div className="flex justify-between items-center mb-8">
          <h2 className="text-3xl font-bold tracking-tight">Active Watchlist</h2>
          <AddTickerModal onTickerAdded={fetchState} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Object.entries(botState.tickers).map(([sym, cfg]) => (
            <TickerCard 
              key={sym} 
              ticker={cfg} 
              levels={{ buy_level: 0, sell_level: 0, stop_level: 0 }}
              onDelete={async (s) => {
                 await fetch(`http://localhost:8000/tickers/${s}`, { method: 'DELETE' });
                 fetchState();
              }}
              onPlace={() => {}} 
            />
          ))}
        </div>
      </main>
    </div>
  );
}

export default App;