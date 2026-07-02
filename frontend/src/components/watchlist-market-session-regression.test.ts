import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const watchlistPath = path.join(root, 'src', 'components', 'tabs', 'WatchlistTab.tsx');
const watchlistSource = fs.readFileSync(watchlistPath, 'utf8');

assert.match(
  watchlistSource,
  /getUsEquitySession/,
  'Watchlist Session status should use the US equities session formatter instead of hardcoded Pre-Market text',
);

assert.doesNotMatch(
  watchlistSource,
  /sp-mkt-status pre">\s*Pre-Market|label:\s*'24\/7'|key:\s*'Crypto'|Crypto:/,
  'Watchlist market strip should not show a hardcoded Pre-Market session or a Crypto 24/7 market',
);
