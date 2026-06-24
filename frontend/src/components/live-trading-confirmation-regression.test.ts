import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();

const settingsTab = fs.readFileSync(path.join(root, 'src', 'components', 'tabs', 'SettingsTab.tsx'), 'utf8');
const tradingModeSection = fs.readFileSync(path.join(root, 'src', 'components', 'settings', 'TradingModeSection.tsx'), 'utf8');
const watchlistTab = fs.readFileSync(path.join(root, 'src', 'components', 'tabs', 'WatchlistTab.tsx'), 'utf8');

for (const [name, source] of [
  ['SettingsTab', settingsTab],
  ['TradingModeSection', tradingModeSection],
  ['WatchlistTab', watchlistTab],
] as const) {
  assert.match(
    source,
    /requestLiveTradingPayload/,
    `${name} should route settings payloads through live-trading confirmation`,
  );
}

assert.match(
  tradingModeSection,
  /isLiveTradingMode\(\{\s*simulate247,\s*liveDuringMarketHours\s*\}\)/s,
  'Trading mode badge should match backend live-mode semantics',
);

assert.doesNotMatch(
  tradingModeSection,
  /SET_SIMULATE_24_7|useWebSocket/,
  'Trading mode changes should use the confirmed settings API path only',
);

assert.doesNotMatch(
  watchlistTab,
  /setTradingMode\(checked \? 'paper' : 'live'\)/,
  'Watchlist should not treat simulate_24_7=false alone as live trading',
);
