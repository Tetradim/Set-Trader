import {
  DASHBOARD_TAB_GROUPS,
  type DashboardGroupId,
  type DashboardTabId,
  getDefaultTabForDashboardGroup,
  getTabsForDashboardGroup,
} from '@/lib/dashboard-tabs';
import { GROUP_NAV, TAB_DETAILS } from './dashboardConfig';

interface DashboardNavigationProps {
  activeGroup: DashboardGroupId;
  activeTab: DashboardTabId;
  onTabChange: (tabId: DashboardTabId) => void;
}

export function DashboardTabBars({ activeGroup, activeTab, onTabChange }: DashboardNavigationProps) {
  return (
    <>
      <div className="sp-tabbar scrollbar-hide" data-testid="tab-bar">
        <nav className="scrollbar-hide" style={{ display: 'flex', alignItems: 'stretch', flex: 1, gap: 6, overflowX: 'auto' }}>
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
                onClick={() => onTabChange(getDefaultTabForDashboardGroup(group.id))}
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
        <nav className="scrollbar-hide" style={{ display: 'flex', alignItems: 'stretch', flex: 1, gap: 4, overflowX: 'auto' }}>
          {getTabsForDashboardGroup(activeGroup).map((tabId) => {
            const tab = TAB_DETAILS[tabId];
            const Icon = tab.icon;
            const isActive = activeTab === tabId;
            return (
              <button
                key={tabId}
                type="button"
                className={`sp-tab ${isActive ? 'active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => onTabChange(tabId)}
                data-testid={`tab-${tabId}`}
              >
                <Icon size={10} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>
    </>
  );
}
