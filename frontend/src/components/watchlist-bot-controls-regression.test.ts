import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const watchlistPath = path.join(root, 'src', 'components', 'tabs', 'WatchlistTab.tsx');
const watchlistSource = fs.readFileSync(watchlistPath, 'utf8');

assert.match(
  watchlistSource,
  /const runBotAction = useCallback\(async \(action: 'start' \| 'pause' \| 'stop'\) => \{[\s\S]*apiFetch\(`\/api\/bot\/\$\{action\}`,[\s\S]*method:\s*'POST'/,
  'Watchlist bot action helper should call authenticated REST bot endpoints',
);

assert.match(
  watchlistSource,
  /action === 'start' \? \{ enable_all: true \} : \{ disable_all: true \}/,
  'Watchlist Start All and Stop controls should send explicit all-ticker intent',
);

assert.match(
  watchlistSource,
  /if \(Array\.isArray\(result\.tickers\)\) useStore\.getState\(\)\.setTickers\(result\.tickers\)/,
  'Watchlist bot controls should apply returned ticker enabled states',
);

assert.match(
  watchlistSource,
  /onClick=\{\(\) => runBotAction\('start'\)\}/,
  'Watchlist Start All control should use the REST bot action helper',
);

assert.match(
  watchlistSource,
  /onClick=\{\(\) => runBotAction\('pause'\)\}/,
  'Watchlist Pause control should use the REST bot action helper',
);

assert.match(
  watchlistSource,
  /onClick=\{\(\) => runBotAction\('stop'\)\}/,
  'Watchlist Stop control should use the REST bot action helper',
);

assert.match(
  watchlistSource,
  /body:\s*JSON\.stringify\(\{\s*simulate_24_7:\s*checked\s*\}\)/s,
  'Paper/Live controls and Simulate 24/7 toggle should persist through /api/settings',
);

assert.doesNotMatch(
  watchlistSource,
  /label:\s*'Trailing Stop'|key:\s*'trailing'/,
  'Watchlist Bot Controls should not expose a local-only Trailing Stop toggle',
);

assert.match(
  watchlistSource,
  /body:\s*JSON\.stringify\(\{\s*live_during_market_hours:\s*checked\s*\}\)/s,
  'Live During Market Hours should persist through /api/settings',
);

assert.match(
  watchlistSource,
  /body:\s*JSON\.stringify\(\{\s*paper_after_hours:\s*checked\s*\}\)/s,
  'Paper After Hours should persist through /api/settings',
);

assert.doesNotMatch(
  watchlistSource,
  /SET_SIMULATE_247|SET_LIVE_DURING_MARKET_HOURS|SET_PAPER_AFTER_HOURS|SET_MODE/,
  'Watchlist bot controls should not send unsupported WebSocket settings commands',
);
