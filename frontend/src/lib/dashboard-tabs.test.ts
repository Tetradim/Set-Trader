import { strict as assert } from 'node:assert';
import {
  getDashboardGroupForTab,
  getDefaultTabForDashboardGroup,
  getTabsForDashboardGroup,
  isDashboardTabId,
  normalizeDashboardTabId,
} from './dashboard-tabs';

assert.equal(isDashboardTabId('watchlist'), true);
assert.equal(isDashboardTabId('not-real'), false);
assert.equal(normalizeDashboardTabId('orders'), 'orders');
assert.equal(normalizeDashboardTabId('preflight'), 'preflight');
assert.equal(normalizeDashboardTabId(''), 'watchlist');
assert.equal(normalizeDashboardTabId('not-real'), 'watchlist');
assert.equal(getDashboardGroupForTab('orders'), 'trading');
assert.equal(getDashboardGroupForTab('logs'), 'monitoring');
assert.equal(getDashboardGroupForTab('admin'), 'settings');
assert.equal(getDefaultTabForDashboardGroup('risk'), 'preflight');
assert.deepEqual(getTabsForDashboardGroup('integrations'), ['brokers', 'foreign']);
