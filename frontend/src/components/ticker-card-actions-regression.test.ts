import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const tickerCardPath = path.join(root, 'src', 'components', 'TickerCard.tsx');
const tickerCardActionsPath = path.join(root, 'src', 'hooks', 'useTickerCardActions.ts');
const tickerCardSource = fs.readFileSync(tickerCardPath, 'utf8');
const tickerCardActionsSource = fs.readFileSync(tickerCardActionsPath, 'utf8');
const combinedSource = `${tickerCardSource}\n${tickerCardActionsSource}`;

assert.match(
  combinedSource,
  /await apiFetch\(`\/api\/tickers\/\$\{encodeURIComponent\(ticker\.symbol\)\}`,\s*\{\s*method:\s*'PUT'[\s\S]*body:\s*JSON\.stringify\(\{\s*enabled:\s*!isActive\s*\}\)/,
  'Ticker card pause/resume button should persist through the authenticated REST ticker update endpoint',
);

assert.match(
  combinedSource,
  /await apiFetch\(`\/api\/tickers\/\$\{encodeURIComponent\(ticker\.symbol\)\}`,\s*\{\s*method:\s*'DELETE'\s*\}\)/,
  'Ticker card delete button should remove tickers through the authenticated REST ticker delete endpoint',
);

assert.doesNotMatch(
  tickerCardSource,
  /send\('UPDATE_TICKER',\s*\{\s*symbol:\s*ticker\.symbol,\s*enabled:/,
  'Ticker card pause/resume should not silently drop when WebSocket is unavailable',
);

assert.doesNotMatch(
  tickerCardSource,
  /send\('DELETE_TICKER'/,
  'Ticker card delete should not silently drop when WebSocket is unavailable',
);
