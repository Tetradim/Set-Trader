export const DASHBOARD_TAB_IDS = [
  'watchlist',
  'portfolio',
  'positions',
  'history',
  'preflight',
  'risk-center',
  'orders',
  'reconciliation',
  'compliance',
  'logs',
  'brokers',
  'foreign',
  'traces',
  'incidents',
  'analytics',
  'admin',
  'slo',
  'settings',
] as const;

export type DashboardTabId = (typeof DASHBOARD_TAB_IDS)[number];

const DASHBOARD_TAB_ID_SET = new Set<string>(DASHBOARD_TAB_IDS);

export const DASHBOARD_TAB_GROUPS = [
  {
    id: 'trading',
    label: 'Trading',
    defaultTab: 'watchlist',
    tabs: ['watchlist', 'portfolio', 'positions', 'orders', 'history'],
  },
  {
    id: 'risk',
    label: 'Risk',
    defaultTab: 'preflight',
    tabs: ['preflight', 'risk-center', 'reconciliation', 'compliance'],
  },
  {
    id: 'monitoring',
    label: 'Monitoring',
    defaultTab: 'logs',
    tabs: ['logs', 'traces', 'incidents', 'slo', 'analytics'],
  },
  {
    id: 'integrations',
    label: 'Integrations',
    defaultTab: 'brokers',
    tabs: ['brokers', 'foreign'],
  },
  {
    id: 'settings',
    label: 'Settings',
    defaultTab: 'settings',
    tabs: ['settings', 'admin'],
  },
] as const;

export type DashboardGroupId = (typeof DASHBOARD_TAB_GROUPS)[number]['id'];

export function isDashboardTabId(value: string): value is DashboardTabId {
  return DASHBOARD_TAB_ID_SET.has(value);
}

export function normalizeDashboardTabId(value: string): DashboardTabId {
  return isDashboardTabId(value) ? value : 'watchlist';
}

export function getDashboardGroupForTab(tabId: DashboardTabId): DashboardGroupId {
  return DASHBOARD_TAB_GROUPS.find((group) => group.tabs.includes(tabId as never))?.id ?? 'trading';
}

export function getTabsForDashboardGroup(groupId: DashboardGroupId): readonly DashboardTabId[] {
  return DASHBOARD_TAB_GROUPS.find((group) => group.id === groupId)?.tabs ?? DASHBOARD_TAB_GROUPS[0].tabs;
}

export function getDefaultTabForDashboardGroup(groupId: DashboardGroupId): DashboardTabId {
  return DASHBOARD_TAB_GROUPS.find((group) => group.id === groupId)?.defaultTab ?? 'watchlist';
}
