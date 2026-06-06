import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const dashboardPath = path.join(root, 'src', 'components', 'Dashboard.tsx');
const tabContentPath = path.join(root, 'src', 'components', 'DashboardTabContent.tsx');
const configPath = path.join(root, 'src', 'components', 'dashboardConfig.tsx');
const addTickerDialogPath = path.join(root, 'src', 'components', 'AddTickerDialog.tsx');
const indexCssPath = path.join(root, 'src', 'index.css');

const dashboardSource = fs.readFileSync(dashboardPath, 'utf8');
const indexCssSource = fs.readFileSync(indexCssPath, 'utf8');

assert.ok(
  dashboardSource.split(/\r?\n/).length <= 115,
  'Dashboard.tsx should stay focused by delegating tab metadata and tab content rendering',
);

assert.ok(fs.existsSync(tabContentPath), 'Dashboard tab content should live in DashboardTabContent.tsx');
assert.ok(fs.existsSync(configPath), 'Dashboard navigation metadata should live in dashboardConfig.tsx');
assert.match(dashboardSource, /className="sp-tab-content flex-1 overflow-auto"/);
assert.match(indexCssSource, /\.sp-layout \{[^}]*position:relative;[^}]*z-index:1;/);
assert.match(indexCssSource, /\.sp-main \{[^}]*position:relative;[^}]*z-index:1;/);
assert.match(indexCssSource, /\.sp-tab-content \{[^}]*position:relative;[^}]*z-index:1;/);

const tabContentSource = fs.readFileSync(tabContentPath, 'utf8');

assert.match(tabContentSource, /lazy\(\(\) => import\('\.\/tabs\/PortfolioTab'\)/);
assert.match(tabContentSource, /lazy\(\(\) => import\('\.\/tabs\/SettingsTab'\)/);
assert.doesNotMatch(tabContentSource, /lazy\(\(\) => import\('\.\/tabs\/WatchlistTab'\)/);
assert.doesNotMatch(tabContentSource, /className="sp-panel"/);
assert.match(tabContentSource, /TabLoadingState/);

for (const fileName of [
  'AdminIAMTab.tsx',
  'ComplianceAuditTab.tsx',
  'IncidentsOpsTab.tsx',
  'PortfolioAnalyticsTab.tsx',
  'PreflightTab.tsx',
  'ReconciliationTab.tsx',
  'RiskCenterTab.tsx',
  'SLODashboardTab.tsx',
]) {
  const tabSource = fs.readFileSync(path.join(root, 'src', 'components', 'tabs', fileName), 'utf8');
  assert.match(tabSource, /TabLoadingState/, `${fileName} should show a named loading panel instead of a blank spinner`);
}

const addTickerDialogSource = fs.readFileSync(addTickerDialogPath, 'utf8');
assert.match(addTickerDialogSource, /if \(!open \|\| marketsLoaded\) return;/);
assert.match(addTickerDialogSource, /\[open, marketsLoaded\]/);
