import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const watchlistPath = path.join(root, 'src', 'components', 'tabs', 'WatchlistTab.tsx');
const addTickerDialogPath = path.join(root, 'src', 'components', 'AddTickerDialog.tsx');

const watchlistSource = fs.readFileSync(watchlistPath, 'utf8');
const addTickerDialogSource = fs.readFileSync(addTickerDialogPath, 'utf8');

assert.match(
  addTickerDialogSource,
  /type AddTickerDialogProps = \{\s*trigger\?: React\.ReactNode;\s*\}/s,
  'AddTickerDialog should accept a custom trigger so every Add Ticker surface opens the same dialog',
);

assert.match(
  watchlistSource,
  /import \{ AddTickerDialog \} from '@\/components\/AddTickerDialog';/,
  'WatchlistTab should import AddTickerDialog for the grid Add Ticker card',
);

assert.match(
  watchlistSource,
  /<AddTickerDialog\s+trigger=\{\s*<button[\s\S]*data-testid="watchlist-add-ticker-card"[\s\S]*className="sp-add-ticker"/,
  'Watchlist Add Ticker card should be a dialog trigger button, not a static div',
);

assert.doesNotMatch(
  watchlistSource,
  /<div className="sp-add-ticker">/,
  'Watchlist Add Ticker card must not be a non-interactive div',
);

assert.match(
  addTickerDialogSource,
  /apiFetch\('\/api\/tickers',\s*\{\s*method:\s*'POST',[\s\S]*body:\s*JSON\.stringify\(\{\s*symbol:\s*sym,\s*base_power:\s*basePower,\s*market\s*\}\)/,
  'AddTickerDialog should submit through the authenticated REST ticker endpoint',
);

assert.doesNotMatch(
  addTickerDialogSource,
  /send\('ADD_TICKER'/,
  'AddTickerDialog should not silently drop ticker creation when WebSocket is unavailable',
);
