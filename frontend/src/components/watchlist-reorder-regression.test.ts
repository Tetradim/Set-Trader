import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const watchlistPath = path.join(root, 'src', 'components', 'tabs', 'WatchlistTab.tsx');
const watchlistSource = fs.readFileSync(watchlistPath, 'utf8');

assert.match(
  watchlistSource,
  /const previousTickers = Object\.values\(currentTickers\);/,
  'Watchlist drag reorder should keep the previous ticker order for rollback',
);

assert.match(
  watchlistSource,
  /useStore\.getState\(\)\.setTickers\(reorderedTickers\);/,
  'Watchlist drag reorder should update local sort_order immediately after drop',
);

assert.match(
  watchlistSource,
  /apiFetch\('\/api\/tickers\/reorder',\s*\{\s*method:\s*'POST',\s*body:\s*JSON\.stringify\(\{\s*order:\s*reordered\s*\}\)\s*\}\)/s,
  'Watchlist drag reorder should post the backend-supported order payload',
);

assert.doesNotMatch(
  watchlistSource,
  /JSON\.stringify\(\{\s*symbols:\s*reordered\s*\}\)/,
  'Watchlist drag reorder must not post the unsupported symbols payload',
);

assert.match(
  watchlistSource,
  /useStore\.getState\(\)\.setTickers\(previousTickers\);/,
  'Watchlist drag reorder should roll back local order if persistence fails',
);
