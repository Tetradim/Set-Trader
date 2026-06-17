import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const sectionPath = path.join(root, 'src', 'components', 'settings', 'BrokerAllocationsSection.tsx');
const source = fs.readFileSync(sectionPath, 'utf8');

assert.doesNotMatch(
  source,
  /tickersWithBrokers\s*=\s*tickers\.filter/,
  'Settings allocation controls must not hide watchlist tickers that have no broker assignment',
);

assert.match(
  source,
  /tickers\.map\(\(ticker\)\s*=>\s*\(/,
  'Settings allocation controls should render one allocation card for every ticker in the store',
);

assert.match(
  source,
  /data-testid=\{`alloc-base-input-\$\{ticker\.symbol\}`\}/,
  'Every allocation card should expose a direct base buy-power input for adding or removing ticker money',
);

assert.match(
  source,
  /apiFetch\(`\/api\/tickers\/\$\{encodeURIComponent\(symbol\)\}`,\s*\{[\s\S]*method:\s*'PUT'[\s\S]*base_power/s,
  'Base allocation edits should persist through the authenticated REST ticker update endpoint',
);
