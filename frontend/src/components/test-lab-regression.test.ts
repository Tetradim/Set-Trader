import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const tabPath = path.join(root, 'src', 'components', 'tabs', 'TestLabTab.tsx');
const dashboardTabsPath = path.join(root, 'src', 'lib', 'dashboard-tabs.ts');
const tabContentPath = path.join(root, 'src', 'components', 'DashboardTabContent.tsx');
const configPath = path.join(root, 'src', 'components', 'dashboardConfig.tsx');

const tabSource = fs.readFileSync(tabPath, 'utf8');
const dashboardTabsSource = fs.readFileSync(dashboardTabsPath, 'utf8');
const tabContentSource = fs.readFileSync(tabContentPath, 'utf8');
const configSource = fs.readFileSync(configPath, 'utf8');

assert.match(dashboardTabsSource, /'test-lab'/, 'Test Lab should be a dashboard tab id');
assert.match(dashboardTabsSource, /tabs: \['watchlist', 'test-lab'/, 'Test Lab should live in the Trading group');
assert.match(tabContentSource, /import\('\.\/tabs\/TestLabTab'\)/, 'Test Lab should be lazily rendered');
assert.match(configSource, /'test-lab': \{ label: 'Test Lab'/, 'Test Lab should have navigation metadata');

assert.match(tabSource, /\/api\/replay\/sessions\?limit=100/, 'Test Lab should list recorded replay sessions');
assert.match(tabSource, /\/api\/replay\/status/, 'Test Lab should show active replay status');
assert.match(tabSource, /\/api\/replay\/sessions\/\$\{selectedSession\.session_id\}\/start/, 'Test Lab should start selected recordings');
assert.match(tabSource, /\/api\/replay\/stop/, 'Test Lab should stop replay');
assert.match(tabSource, /\/api\/bot\/start/, 'Test Lab should start bots for a test');
assert.match(tabSource, /\/api\/bot\/stop/, 'Test Lab should stop bots for a test');
assert.match(tabSource, /enable_all: false/, 'Test Lab should not reactivate every ticker when starting selected tests');
assert.match(tabSource, /disable_all: true/, 'Test Lab stop should deactivate all ticker bots');
assert.match(tabSource, /selectedSymbols/, 'Test Lab should expose symbol checkboxes');
assert.match(tabSource, /simulate_24_7: true/, 'Test Lab should force simulation mode before replay');
