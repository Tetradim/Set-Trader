import { useEffect } from 'react';
import { useStore } from '@/stores/useStore';
import { Header } from './Header';
import { ErrorBoundary } from './ErrorBoundary';
import { DashboardTabContent } from './DashboardTabContent';
import { DashboardTabBars } from './DashboardNavigation';
import { apiFetch } from '@/lib/api';
import {
  getDashboardGroupForTab,
  normalizeDashboardTabId,
} from '@/lib/dashboard-tabs';

export function Dashboard() {
  const activeTabState = useStore((s) => s.activeTab);
  const setActiveTab = useStore((s) => s.setActiveTab);
  const setFxRates = useStore((s) => s.setFxRates);
  const setCurrencyDisplay = useStore((s) => s.setCurrencyDisplay);
  const activeTab = normalizeDashboardTabId(activeTabState);
  const activeGroup = getDashboardGroupForTab(activeTab);

  useEffect(() => {
    apiFetch('/api/fx-rates').then((d) => setFxRates(d.rates)).catch(() => {});
    apiFetch('/api/settings/currency-display').then((d) => setCurrencyDisplay(d.mode)).catch(() => {});
    const timer = setInterval(() => {
      apiFetch('/api/fx-rates').then((d) => setFxRates(d.rates)).catch(() => {});
    }, 5 * 60_000);
    return () => clearInterval(timer);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (activeTab !== activeTabState) {
      setActiveTab(activeTab);
    }
  }, [activeTab, activeTabState, setActiveTab]);

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ position: 'relative', zIndex: 1 }}
      data-testid="dashboard-container"
    >
      <div className="sp-bg" aria-hidden="true">
        <div className="sp-bg-pattern" />
        <div className="sp-bg-vignette" />
      </div>

      <Header />
      <div className="sp-gleam-bar" />

      <div className="sp-layout" style={{ flex: 1, overflow: 'hidden' }}>
        <div className="sp-main">
          <DashboardTabBars activeGroup={activeGroup} activeTab={activeTab} onTabChange={setActiveTab} />

          <div
            className="sp-tab-content flex-1 overflow-auto"
            style={{ padding: '14px 16px' }}
            data-testid="tab-content"
          >
            <ErrorBoundary key={activeTab} fallbackLabel={`Tab "${activeTab}" failed to render`}>
              <DashboardTabContent activeTab={activeTab} />
            </ErrorBoundary>
          </div>
        </div>
      </div>
    </div>
  );
}
