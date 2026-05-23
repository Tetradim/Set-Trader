import { lazy, Suspense } from 'react';
import { WatchlistTab } from './tabs/WatchlistTab';
import type { DashboardTabId } from '@/lib/dashboard-tabs';

const PortfolioTab = lazy(() => import('./tabs/PortfolioTab').then((module) => ({ default: module.PortfolioTab })));
const PositionsTab = lazy(() => import('./tabs/PositionsTab').then((module) => ({ default: module.PositionsTab })));
const HistoryTab = lazy(() => import('./tabs/HistoryTab').then((module) => ({ default: module.HistoryTab })));
const LogsTab = lazy(() => import('./tabs/LogsTab').then((module) => ({ default: module.LogsTab })));
const SettingsTab = lazy(() => import('./tabs/SettingsTab').then((module) => ({ default: module.SettingsTab })));
const BrokersTab = lazy(() => import('./tabs/BrokersTab').then((module) => ({ default: module.BrokersTab })));
const TracesTab = lazy(() => import('./tabs/TracesTab').then((module) => ({ default: module.TracesTab })));
const ForeignTab = lazy(() => import('./tabs/ForeignTab').then((module) => ({ default: module.ForeignTab })));
const RiskCenterTab = lazy(() => import('./tabs/RiskCenterTab').then((module) => ({ default: module.RiskCenterTab })));
const PreflightTab = lazy(() => import('./tabs/PreflightTab').then((module) => ({ default: module.PreflightTab })));
const OrdersExecutionTab = lazy(() => import('./tabs/OrdersExecutionTab').then((module) => ({ default: module.OrdersExecutionTab })));
const ReconciliationTab = lazy(() => import('./tabs/ReconciliationTab').then((module) => ({ default: module.ReconciliationTab })));
const ComplianceAuditTab = lazy(() => import('./tabs/ComplianceAuditTab').then((module) => ({ default: module.ComplianceAuditTab })));
const IncidentsOpsTab = lazy(() => import('./tabs/IncidentsOpsTab').then((module) => ({ default: module.IncidentsOpsTab })));
const PortfolioAnalyticsTab = lazy(() => import('./tabs/PortfolioAnalyticsTab').then((module) => ({ default: module.PortfolioAnalyticsTab })));
const AdminIAMTab = lazy(() => import('./tabs/AdminIAMTab').then((module) => ({ default: module.AdminIAMTab })));
const SLODashboardTab = lazy(() => import('./tabs/SLODashboardTab').then((module) => ({ default: module.SLODashboardTab })));

function TabFallback() {
  return (
    <div className="sp-panel" style={{ padding: 16 }}>
      Loading tab...
    </div>
  );
}

function LazyTabContent({ activeTab }: { activeTab: DashboardTabId }) {
  switch (activeTab) {
    case 'portfolio': return <PortfolioTab />;
    case 'positions': return <PositionsTab />;
    case 'preflight': return <PreflightTab />;
    case 'risk-center': return <RiskCenterTab />;
    case 'orders': return <OrdersExecutionTab />;
    case 'reconciliation': return <ReconciliationTab />;
    case 'compliance': return <ComplianceAuditTab />;
    case 'history': return <HistoryTab />;
    case 'logs': return <LogsTab />;
    case 'brokers': return <BrokersTab />;
    case 'foreign': return <ForeignTab />;
    case 'traces': return <TracesTab />;
    case 'incidents': return <IncidentsOpsTab />;
    case 'analytics': return <PortfolioAnalyticsTab />;
    case 'admin': return <AdminIAMTab />;
    case 'slo': return <SLODashboardTab />;
    case 'settings': return <SettingsTab />;
    case 'watchlist':
    default:
      return <WatchlistTab />;
  }
}

export function DashboardTabContent({ activeTab }: { activeTab: DashboardTabId }) {
  if (activeTab === 'watchlist') {
    return <WatchlistTab />;
  }

  return (
    <Suspense fallback={<TabFallback />}>
      <LazyTabContent activeTab={activeTab} />
    </Suspense>
  );
}
