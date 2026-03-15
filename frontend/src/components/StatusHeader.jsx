import React from 'react';
import { 
  Activity, 
  CircleDot, 
  Power, 
  Wifi, 
  WifiOff, 
  TrendingUp, 
  Clock 
} from 'lucide-react';

export const StatusHeader = ({ statusData }) => {
  const { connected, market_open, paused, total_profit } = statusData;

  return (
    <div className="flex items-center justify-between p-4 bg-card border-b border-border">
      <div className="flex items-center gap-6">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <Activity className="text-primary w-6 h-6" />
          Bracket Bot <span className="text-xs font-normal opacity-50">v3.0</span>
        </h1>
        
        <div className="flex items-center gap-4 text-sm">
          {/* Connection Status */}
          <div className="flex items-center gap-1.5">
            {connected ? (
              <Wifi className="w-4 h-4 text-green-500" />
            ) : (
              <WifiOff className="w-4 h-4 text-destructive" />
            )}
            <span className={connected ? "text-green-500" : "text-destructive"}>
              {connected ? "Live" : "Disconnected"}
            </span>
          </div>

          {/* Market Status */}
          <div className="flex items-center gap-1.5">
            <Clock className="w-4 h-4" />
            <span>Market: {market_open ? "Open" : "Closed"}</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Profit Display */}
        <div className="flex flex-col items-end">
          <span className="text-[10px] uppercase font-bold opacity-50">Session Profit</span>
          <span className={`font-mono font-bold flex items-center gap-1 ${total_profit >= 0 ? "text-green-500" : "text-destructive"}`}>
            <TrendingUp className="w-4 h-4" />
            ${total_profit?.toFixed(2)}
          </span>
        </div>

        {/* Action Button */}
        <button 
          className={`p-2 rounded-full transition-colors ${paused ? "bg-green-500/10 text-green-500" : "bg-destructive/10 text-destructive"}`}
          title={paused ? "Resume Bot" : "Pause Bot"}
        >
          <Power className="w-5 h-5" />
        </button>
      </div>
    </div>
  );
};