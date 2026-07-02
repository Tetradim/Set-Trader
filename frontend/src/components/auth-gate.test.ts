import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const authGatePath = path.join(root, 'src', 'components', 'AuthGate.tsx');
const authGateSource = fs.readFileSync(authGatePath, 'utf8');

assert.match(authGateSource, /mode === 'setup'\s*\?\s*\{ username, password \}\s*:\s*\{ username, password \}/);
assert.match(authGateSource, /status\.auth_disabled/);
assert.match(authGateSource, /setAuthDisabled\(true\)/);
assert.match(authGateSource, /setMode\('ready'\)/);
assert.match(authGateSource, /<span className="mb-1 block text-\[#bdb4a0\]">Username<\/span>/);
assert.doesNotMatch(authGateSource, />Username or email</);
assert.doesNotMatch(authGateSource, />Username \(email\)</);
assert.doesNotMatch(authGateSource, />Email<\/span>/);
assert.doesNotMatch(authGateSource, /type="email"/);
assert.doesNotMatch(authGateSource, /minLength=\{mode === 'setup' \? 12 : undefined\}/);
