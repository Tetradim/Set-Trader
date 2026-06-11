import type { ComponentType } from 'react';
import {
  Activity,
  BarChart3,
  Bell,
  Briefcase,
  Crosshair,
  FlaskConical,
  Globe,
  History,
  LayoutDashboard,
  List,
  Plug,
  Scale,
  ScrollText,
  Settings,
  Shield,
  ShieldCheck,
  Target,
  Users,
} from 'lucide-react';
import type { DashboardGroupId, DashboardTabId } from '@/lib/dashboard-tabs';

type IconComponent = ComponentType<{ size?: number }>;

export const GROUP_NAV: Array<{ id: DashboardGroupId; icon: IconComponent; title: string }> = [
  { id: 'trading', icon: LayoutDashboard, title: 'Trading' },
  { id: 'risk', icon: ShieldCheck, title: 'Risk' },
  { id: 'monitoring', icon: Activity, title: 'Monitoring' },
  { id: 'integrations', icon: Plug, title: 'Integrations' },
  { id: 'settings', icon: Settings, title: 'Settings' },
];

export const TAB_DETAILS: Record<DashboardTabId, { label: string; icon: IconComponent }> = {
  watchlist: { label: 'Watchlist', icon: LayoutDashboard },
  'test-lab': { label: 'Test Lab', icon: FlaskConical },
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
