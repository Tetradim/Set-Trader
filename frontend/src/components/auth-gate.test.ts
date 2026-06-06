import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const authGatePath = path.join(root, 'src', 'components', 'AuthGate.tsx');
const authGateSource = fs.readFileSync(authGatePath, 'utf8');

assert.match(authGateSource, /mode === 'setup'\s*\?\s*\{ username, email, password \}\s*:\s*\{ username, password \}/);
assert.match(authGateSource, /<span className="mb-1 block text-\[#bdb4a0\]">Username<\/span>/);
assert.doesNotMatch(authGateSource, />Username or email</);
assert.doesNotMatch(authGateSource, />Username \(email\)</);
