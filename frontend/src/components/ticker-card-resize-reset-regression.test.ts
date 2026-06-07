import { strict as assert } from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const tickerCardPath = path.join(root, 'src', 'components', 'TickerCard.tsx');
const footerPath = path.join(root, 'src', 'components', 'ticker-card', 'TickerCardFooter.tsx');

const tickerCardSource = fs.readFileSync(tickerCardPath, 'utf8');
const footerSource = fs.readFileSync(footerPath, 'utf8');

assert.match(
  tickerCardSource,
  /const handleResetSize = useCallback\(\(\) => \{\s*setCardSize\(\{\s*width:\s*0,\s*height:\s*0\s*\}\);\s*\}, \[\]\);/s,
  'TickerCard should reset inline card dimensions back to the original CSS size',
);

assert.match(
  tickerCardSource,
  /hasCustomSize=\{cardSize\.width > 0 \|\| cardSize\.height > 0\}/,
  'TickerCard should only show reset-size control after custom dimensions exist',
);

assert.match(
  tickerCardSource,
  /onResetSize=\{handleResetSize\}/,
  'TickerCard should wire the reset-size footer button to the reset handler',
);

assert.match(
  footerSource,
  /RotateCcw/,
  'TickerCardFooter should use a reset/rotate icon for snap-back',
);

assert.match(
  footerSource,
  /aria-label=\{`Reset \$\{symbol\} card size`\}/,
  'TickerCardFooter reset button should be accessible by symbol',
);

assert.match(
  footerSource,
  /\{hasCustomSize && \(/,
  'TickerCardFooter should render reset-size only when the card has been resized',
);
