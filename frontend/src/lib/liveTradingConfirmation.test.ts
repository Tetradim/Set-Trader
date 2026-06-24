import { strict as assert } from 'node:assert';
import {
  LIVE_TRADING_CONFIRMATION,
  addLiveTradingConfirmation,
  isCandidateLiveTradingMode,
  isLiveTradingMode,
  needsLiveTradingConfirmation,
} from './liveTradingConfirmation';

assert.equal(
  isLiveTradingMode({ simulate247: false, liveDuringMarketHours: false }),
  false,
  'Simulation off is still paper mode until live-during-market-hours is enabled',
);

assert.equal(
  isLiveTradingMode({ simulate247: false, liveDuringMarketHours: true }),
  true,
  'Live mode requires simulation off and live-during-market-hours enabled',
);

assert.equal(
  isCandidateLiveTradingMode(
    { simulate247: true, liveDuringMarketHours: true },
    { simulate_24_7: false },
  ),
  true,
  'Turning simulation off while live market-hours is enabled creates a live candidate',
);

assert.equal(
  needsLiveTradingConfirmation(
    { simulate247: false, liveDuringMarketHours: false },
    { live_during_market_hours: true },
  ),
  true,
  'Enabling live market-hours while simulation is already off needs confirmation',
);

assert.deepEqual(
  addLiveTradingConfirmation(
    { simulate247: false, liveDuringMarketHours: false },
    { live_during_market_hours: true },
    LIVE_TRADING_CONFIRMATION,
    'operator-secret',
  ),
  {
    live_during_market_hours: true,
    live_trading_confirmation: LIVE_TRADING_CONFIRMATION,
    live_trading_operator_secret: 'operator-secret',
  },
  'Exact confirmation and operator secret should be attached to live-transition payloads',
);

assert.equal(
  addLiveTradingConfirmation(
    { simulate247: false, liveDuringMarketHours: false },
    { live_during_market_hours: true },
    LIVE_TRADING_CONFIRMATION,
    '',
  ),
  null,
  'Missing operator secret should cancel live-transition payloads',
);

assert.equal(
  addLiveTradingConfirmation(
    { simulate247: false, liveDuringMarketHours: false },
    { live_during_market_hours: true },
    'enable live trading',
    'operator-secret',
  ),
  null,
  'Incorrect confirmation should cancel live-transition payloads',
);

assert.deepEqual(
  addLiveTradingConfirmation(
    { simulate247: false, liveDuringMarketHours: true },
    { simulate_24_7: true },
    '',
  ),
  { simulate_24_7: true },
  'Paper-mode updates should not need live confirmation',
);
