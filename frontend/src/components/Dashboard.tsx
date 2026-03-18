import { useStore } from '@/stores/useStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { Header } from './Header';
import { WatchlistTab } from './tabs/WatchlistTab';
import { PositionsTab } from './tabs/PositionsTab';
import { HistoryTab } from './tabs/HistoryTab';
import { LogsTab } from './tabs/LogsTab';
import { SettingsTab } from './tabs/SettingsTab';
import { BrokersTab } from './tabs/BrokersTab';
import { TradeLogSidebar } from './TradeLogSidebar';
import { CommandPalette } from './CommandPalette';
import { LayoutDashboard, Crosshair, History, ScrollText, Settings, Plug } from 'lucide-react';
import { ErrorBoundary } from './ErrorBoundary';

const TABS = [
  { id: 'watchlist', label: 'Watchlist', icon: LayoutDashboard },
  { id: 'positions', label: 'Positions', icon: Crosshair },
  { id: 'history', label: 'History', icon: History },
  { id: 'logs', label: 'Logs', icon: ScrollText },
  { id: 'brokers', label: 'Brokers', icon: Plug },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export function Dashboard() {
  const activeTab = useStore((s) => s.activeTab);
  const setActiveTab = useStore((s) => s.setActiveTab);

  return (
    <div className="min-h-screen flex flex-col" data-testid="dashboard-container">
      <Header />
      <CommandPalette />

      <div className="flex-1 flex">
        {/* Main content area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Tab bar */}
          <nav className="flex items-center gap-1 px-6 pt-4 pb-0 border-b border-border" data-testid="tab-bar">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  data-testid={`tab-${tab.id}`}
                  onClick={() => setActiveTab(tab.id)}
                  className={`
                    flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-lg transition-all
                    ${active
                      ? 'text-primary bg-card border border-b-0 border-border -mb-px'
                      : 'text-muted-foreground hover:text-foreground hover:bg-secondary/50'
                    }
                  `}
                >
                  <Icon size={15} />
                  {tab.label}
                </button>
              );
            })}
          </nav>

          {/* Tab content */}
          <div className="flex-1 overflow-auto p-6" data-testid="tab-content">
            <ErrorBoundary fallbackLabel="Tab failed to render">
              {activeTab === 'watchlist' && <WatchlistTab />}
              {activeTab === 'positions' && <PositionsTab />}
              {activeTab === 'history' && <HistoryTab />}
              {activeTab === 'logs' && <LogsTab />}
              {activeTab === 'brokers' && <BrokersTab />}
              {activeTab === 'settings' && <SettingsTab />}
            </ErrorBoundary>
          </div>
        </div>

        {/* Trade log sidebar */}
        <TradeLogSidebar />
      </div>
    </div>
  );
}
