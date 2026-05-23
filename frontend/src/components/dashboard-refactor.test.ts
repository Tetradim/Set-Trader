import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const dashboardPath = path.join(root, 'src', 'components', 'Dashboard.tsx');
const tabContentPath = path.join(root, 'src', 'components', 'DashboardTabContent.tsx');
const configPath = path.join(root, 'src', 'components', 'dashboardConfig.tsx');

const dashboardSource = fs.readFileSync(dashboardPath, 'utf8');

assert.ok(
  dashboardSource.split(/\r?\n/).length <= 115,
  'Dashboard.tsx should stay focused by delegating tab metadata and tab content rendering',
);

assert.ok(fs.existsSync(tabContentPath), 'Dashboard tab content should live in DashboardTabContent.tsx');
assert.ok(fs.existsSync(configPath), 'Dashboard navigation metadata should live in dashboardConfig.tsx');

const tabContentSource = fs.readFileSync(tabContentPath, 'utf8');

assert.match(tabContentSource, /lazy\(\(\) => import\('\.\/tabs\/PortfolioTab'\)/);
assert.match(tabContentSource, /lazy\(\(\) => import\('\.\/tabs\/SettingsTab'\)/);
assert.doesNotMatch(tabContentSource, /lazy\(\(\) => import\('\.\/tabs\/WatchlistTab'\)/);
