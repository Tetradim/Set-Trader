import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const tickerCardPath = path.join(root, 'src', 'components', 'TickerCard.tsx');
const chartPath = path.join(root, 'src', 'components', 'ticker-card', 'TickerSparkline.tsx');
const bracketsPath = path.join(root, 'src', 'components', 'ticker-card', 'TickerQuickBrackets.tsx');
const resizePath = path.join(root, 'src', 'components', 'ticker-card', 'TickerResizeHandles.tsx');

const tickerCardSource = fs.readFileSync(tickerCardPath, 'utf8');

assert.ok(
  tickerCardSource.split(/\r?\n/).length <= 260,
  'TickerCard.tsx should stay focused by delegating chart, quick bracket, and resize UI',
);

assert.ok(fs.existsSync(chartPath), 'Ticker sparkline rendering should live in ticker-card/TickerSparkline.tsx');
assert.ok(fs.existsSync(bracketsPath), 'Ticker quick bracket editing should live in ticker-card/TickerQuickBrackets.tsx');
assert.ok(fs.existsSync(resizePath), 'Ticker resize handles should live in ticker-card/TickerResizeHandles.tsx');
