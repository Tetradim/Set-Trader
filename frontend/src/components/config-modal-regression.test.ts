import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const configModalPath = path.join(root, 'src', 'components', 'ConfigModal.tsx');
const configModalSource = fs.readFileSync(configModalPath, 'utf8');

assert.match(
  configModalSource,
  /const incrementStep = useStore\(\(s\) => s\.incrementStep\);/,
  'ConfigModal must read incrementStep from the store before rendering ticker config tabs',
);

assert.match(
  configModalSource,
  /const decrementStep = useStore\(\(s\) => s\.decrementStep\);/,
  'ConfigModal must read decrementStep from the store before rendering ticker config tabs',
);

assert.match(
  configModalSource,
  /<RulesTab ticker=\{ticker\} onChange=\{handleFieldChange\} incStep=\{incrementStep\} decStep=\{decrementStep\} \/>/,
  'RulesTab should receive the configured step sizes used by ticker-card inputs',
);

assert.match(
  configModalSource,
  /apiFetch\(`\/api\/tickers\/\$\{ticker\.symbol\}`,\s*\{\s*method:\s*'PUT'/s,
  'ConfigModal should persist ticker config changes through the authenticated REST update endpoint',
);

assert.match(
  configModalSource,
  /updateTicker\(ticker\.symbol,\s*updates\)/,
  'ConfigModal should optimistically update local ticker state while persistence completes',
);

assert.match(
  configModalSource,
  /persistTickerUpdate\(\{ broker_ids \}\)/,
  'Broker selection should use the same persistent ticker update path as other config fields',
);
