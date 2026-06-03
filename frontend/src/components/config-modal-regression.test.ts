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
