import { strict as assert } from 'node:assert';

import { getUsEquitySession } from './market-session';

const regularSession = getUsEquitySession(new Date('2026-07-02T15:00:00.000Z'));
assert.equal(regularSession.label, 'Market Open');
assert.equal(regularSession.status, 'open');

const preMarket = getUsEquitySession(new Date('2026-07-02T12:45:00.000Z'));
assert.equal(preMarket.label, 'Pre-Market');
assert.equal(preMarket.status, 'pre');

const afterHours = getUsEquitySession(new Date('2026-07-02T21:30:00.000Z'));
assert.equal(afterHours.label, 'After-Hours');
assert.equal(afterHours.status, 'after');
