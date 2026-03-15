import React from 'react';
import { TrendingDown, TrendingUp, Zap, Settings2, Trash2 } from 'lucide-react';

export const TickerCard = ({ ticker, levels, onPlace, onDelete }) => {
  return (
    <div className="bg-card border border-border rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-2xl font-bold tracking-tight">{ticker.symbol}</h3>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ticker.enabled ? 'bg-green-500/10 text-green-500' : 'bg-muted text-muted-foreground'}`}>
            {ticker.enabled ? 'Auto-Trading' : 'Disabled'}
          </span>
        </div>
        <div className="flex gap-2">
          <button className="p-2 hover:bg-muted rounded-md transition-colors"><Settings2 className="w-4 h-4" /></button>
          <button onClick={() => onDelete(ticker.symbol)} className="p-2 hover:bg-destructive/10 hover:text-destructive rounded-md transition-colors"><Trash2 className="w-4 h-4" /></button>
        </div>
      </div>

      <div className="space-y-3 mb-6">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Buy Level</span>
          <span className="font-mono text-blue-500 font-bold">${levels.buy_level.toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Take Profit</span>
          <span className="font-mono text-green-500 font-bold">${levels.sell_level.toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Stop Loss</span>
          <span className="font-mono text-destructive font-bold">${levels.stop_level.toFixed(2)}</span>
        </div>
      </div>

      <button 
        onClick={() => onPlace(ticker.symbol)}
        className="w-full bg-primary text-primary-foreground py-2.5 rounded-lg font-semibold flex items-center justify-center gap-2 hover:opacity-90 active:scale-[0.98] transition-all"
      >
        <Zap className="w-4 h-4 fill-current" />
        Force Bracket Order
      </button>
    </div>
  );
};