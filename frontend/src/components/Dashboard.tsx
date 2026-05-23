import { useEffect } from 'react';
import { useStore } from '@/stores/useStore';
import { Header } from './Header';
import { WatchlistTab } from './tabs/WatchlistTab';
import { PositionsTab } from './tabs/PositionsTab';
import { HistoryTab } from './tabs/HistoryTab';
import { LogsTab } from './tabs/LogsTab';
import { SettingsTab } from './tabs/SettingsTab';
import { BrokersTab } from './tabs/BrokersTab';
import { TracesTab } from './tabs/TracesTab';
import { ForeignTab } from './tabs/ForeignTab';
import { RiskCenterTab } from './tabs/RiskCenterTab';
import { PreflightTab } from './tabs/PreflightTab';
import { OrdersExecutionTab } from './tabs/OrdersExecutionTab';
import { ReconciliationTab } from './tabs/ReconciliationTab';
import { ComplianceAuditTab } from './tabs/ComplianceAuditTab';
import { IncidentsOpsTab } from './tabs/IncidentsOpsTab';
import { PortfolioAnalyticsTab } from './tabs/PortfolioAnalyticsTab';
import { AdminIAMTab } from './tabs/AdminIAMTab';
import { SLODashboardTab } from './tabs/SLODashboardTab';
import { PortfolioTab } from './tabs/PortfolioTab';
import { ErrorBoundary } from './ErrorBoundary';
import { apiFetch } from '@/lib/api';
import {
  DASHBOARD_TAB_GROUPS,
  DashboardGroupId,
  DashboardTabId,
  getDashboardGroupForTab,
  getDefaultTabForDashboardGroup,
  getTabsForDashboardGroup,
  normalizeDashboardTabId,
} from '@/lib/dashboard-tabs';
import {
  Activity,
  BarChart3,
  Bell,
  Briefcase,
  Crosshair,
  Globe,
  History,
  LayoutDashboard,
  List,
  Plug,
  Scale,
  ScrollText,
  Server,
  Settings,
  Shield,
  ShieldCheck,
  Target,
  Users,
} from 'lucide-react';

const GROUP_NAV: Array<{ id: DashboardGroupId; icon: any; title: string }> = [
  { id: 'trading', icon: LayoutDashboard, title: 'Trading' },
  { id: 'risk', icon: ShieldCheck, title: 'Risk' },
  { id: 'monitoring', icon: Activity, title: 'Monitoring' },
  { id: 'integrations', icon: Plug, title: 'Integrations' },
  { id: 'settings', icon: Settings, title: 'Settings' },
];

const TAB_DETAILS: Record<DashboardTabId, { label: string; icon: any }> = {
  watchlist: { label: 'Watchlist', icon: LayoutDashboard },
  portfolio: { label: 'Portfolio', icon: Briefcase },
  positions: { label: 'Positions', icon: Crosshair },
  orders: { label: 'Orders', icon: List },
  history: { label: 'History', icon: History },
  preflight: { label: 'Preflight', icon: ShieldCheck },
  'risk-center': { label: 'Risk Center', icon: Shield },
  reconciliation: { label: 'Reconcile', icon: Scale },
  compliance: { label: 'Compliance', icon: Users },
  logs: { label: 'Logs', icon: ScrollText },
  traces: { label: 'Traces', icon: Activity },
  incidents: { label: 'Incidents', icon: Bell },
  slo: { label: 'SLO', icon: Target },
  analytics: { label: 'Analytics', icon: BarChart3 },
  brokers: { label: 'Brokers', icon: Plug },
  foreign: { label: 'Foreign', icon: Globe },
  settings: { label: 'Settings', icon: Settings },
  admin: { label: 'Admin', icon: Users },
};

export function Dashboard() {
  const activeTabState = useStore((s) => s.activeTab);
  const setActiveTab = useStore((s) => s.setActiveTab);
  const setFxRates = useStore((s) => s.setFxRates);
  const setCurrencyDisplay = useStore((s) => s.setCurrencyDisplay);
  const activeTab = normalizeDashboardTabId(activeTabState);
  const activeGroup = getDashboardGroupForTab(activeTab);
  const activeGroupTabs = getTabsForDashboardGroup(activeGroup);

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
        <nav className="sp-sidebar" aria-label="Main navigation groups">
          {GROUP_NAV.map((item) => {
            const Icon = item.icon;
            const isActive = activeGroup === item.id;
            return (
              <button
                key={item.id}
                type="button"
                className={`sp-sb-btn ${isActive ? 'active' : ''}`}
                title={item.title}
                aria-label={`Open ${item.title} group`}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => setActiveTab(getDefaultTabForDashboardGroup(item.id))}
                data-testid={`sidebar-group-${item.id}`}
              >
                <Icon size={17} />
              </button>
            );
          })}
        </nav>

        <div className="sp-main">
          <div className="sp-tabbar scrollbar-hide" data-testid="tab-bar">
            <nav
              className="scrollbar-hide"
              style={{ display: 'flex', alignItems: 'stretch', flex: 1, gap: 6, overflowX: 'auto' }}
            >
              {DASHBOARD_TAB_GROUPS.map((group) => {
                const nav = GROUP_NAV.find((item) => item.id === group.id)!;
                const Icon = nav.icon;
                const isActive = activeGroup === group.id;
                return (
                  <button
                    key={group.id}
                    type="button"
                    className={`sp-tab ${isActive ? 'active' : ''}`}
                    aria-current={isActive ? 'page' : undefined}
                    onClick={() => setActiveTab(getDefaultTabForDashboardGroup(group.id))}
                    data-testid={`tab-group-${group.id}`}
                  >
                    <Icon size={12} />
                    {group.label}
                  </button>
                );
              })}
            </nav>
          </div>

          <div
            className="sp-tabbar scrollbar-hide"
            data-testid="sub-tab-bar"
            style={{ minHeight: 34, borderTop: '1px solid rgba(255,255,255,0.04)' }}
          >
            <nav
              className="scrollbar-hide"
              style={{ display: 'flex', alignItems: 'stretch', flex: 1, gap: 4, overflowX: 'auto' }}
            >
              {activeGroupTabs.map((tabId) => {
                const tab = TAB_DETAILS[tabId];
                const Icon = tab.icon;
                const isActive = activeTab === tabId;
                return (
                  <button
                    key={tabId}
                    type="button"
                    className={`sp-tab ${isActive ? 'active' : ''}`}
                    aria-current={isActive ? 'page' : undefined}
                    onClick={() => setActiveTab(tabId)}
                    data-testid={`tab-${tabId}`}
                  >
                    <Icon size={10} />
                    {tab.label}
                  </button>
                );
              })}
            </nav>
          </div>

          <div
            className="flex-1 overflow-auto"
            style={{ padding: '14px 16px' }}
            data-testid="tab-content"
          >
            <ErrorBoundary key={activeTab} fallbackLabel={`Tab "${activeTab}" failed to render`}>
              {activeTab === 'watchlist' && <WatchlistTab />}
              {activeTab === 'portfolio' && <PortfolioTab />}
              {activeTab === 'positions' && <PositionsTab />}
              {activeTab === 'preflight' && <PreflightTab />}
              {activeTab === 'risk-center' && <RiskCenterTab />}
              {activeTab === 'orders' && <OrdersExecutionTab />}
              {activeTab === 'reconciliation' && <ReconciliationTab />}
              {activeTab === 'compliance' && <ComplianceAuditTab />}
              {activeTab === 'history' && <HistoryTab />}
              {activeTab === 'logs' && <LogsTab />}
              {activeTab === 'brokers' && <BrokersTab />}
              {activeTab === 'foreign' && <ForeignTab />}
              {activeTab === 'traces' && <TracesTab />}
              {activeTab === 'incidents' && <IncidentsOpsTab />}
              {activeTab === 'analytics' && <PortfolioAnalyticsTab />}
              {activeTab === 'admin' && <AdminIAMTab />}
              {activeTab === 'slo' && <SLODashboardTab />}
              {activeTab === 'settings' && <SettingsTab />}
            </ErrorBoundary>
          </div>
        </div>
      </div>
    </div>
  );
}
