import { TickerGrid } from './components/TickerGrid';
import { AddTickerDialog } from './components/AddTickerDialog';
import { TradeLog } from './components/TradeLog';
import { useStore } from './stores/useStore';
import { useEffect, useState } from 'react'
import './App.css'
import { useWebSocket } from './hooks/useWebSocket'
import { CommandPalette } from './components/CommandPalette'


function App() {
  const connected = useStore((state) => state.connected);

  return (
    <main className="min-h-screen bg-background text-foreground p-4 md:p-8 space-y-8">
      {/* Header Area */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b pb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">BracketBot Terminal</h1>
          <p className="text-muted-foreground flex items-center gap-2 mt-1">
            <span className={`h-2 w-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
            {connected ? 'System Online' : 'Connecting to Backend...'}
          </p>
        </div>
        <AddTickerDialog />
      </header>

      {/* Main Dashboard Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-8">
        <div className="xl:col-span-3">
          <TickerGrid />
        </div>
        
        {/* Sidebar Log */}
        <div className="xl:col-span-1 border-l pl-0 xl:pl-8">
          <h2 className="text-lg font-semibold mb-4">Activity Log</h2>
          <TradeLog />
        </div>
      </div>
    </main>
  );
}

export default App;