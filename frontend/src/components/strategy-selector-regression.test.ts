import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const strategyPath = path.join(root, 'src', 'components', 'ticker-card', 'StrategyConfigSection.tsx');
const strategySource = fs.readFileSync(strategyPath, 'utf8');

assert.doesNotMatch(
  strategySource,
  /\{s\.name\}\s*-\s*\{s\.description\?\.slice/,
  'Strategy dropdown options should show strategy names only, not long descriptions',
);

assert.match(
  strategySource,
  /data-testid="strategy-help-toggle"/,
  'Strategy selector should provide a compact help control for the selected strategy explanation',
);

assert.match(
  strategySource,
  /data-testid="strategy-help-panel"/,
  'Selected strategy explanation should render outside the native select menu',
);
