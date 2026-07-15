# Sentinel Pulse live-functional repair log

Branch: `codex/live-readiness-ledger`
PR: #12
Review scope: live-money equities execution and Edge-to-Pulse commands. Security, paper trading, and release gates are secondary to functional execution.

## Verified baseline before this repair cycle

- Build Sentinel Pulse: passing at `7b6bb677280b4ee959737dcfb0d138b9e3265c4d`.
- Pulse Live Readiness Diagnostics: passing at the same commit.

## Findings from post-fix review

### P0 — durable Edge idempotency is not loaded

`backend/trading/edge_handoff_idempotency_patch.py` implements durable command claims and replay, but `backend/trading/__init__.py` does not import it. Direct unit imports test helpers without proving the running `/api/edge/handoff` route is protected.

Planned fix:

1. Load the idempotency implementation before router registration.
2. Create the unique database index at application startup.
3. Add an application-level duplicate POST test proving one broker submission.
4. Prefer direct route behavior over global FastAPI monkey patches.

### P0/P1 — multi-broker partial success has no parent completion policy

Child orders are tracked, but a parent target can remain partly complete forever after mixed fills/rejections.

Planned fix:

- Add parent-order state with target quantity/notional, cumulative fills, remaining quantity, child orders, expiry and completion policy.
- Permit only the remaining quantity to be retried.

### P1 — stale working orders lack strategy invalidation/cancel-replace

Pending orders block duplicates correctly, but there is no complete order-age, quote-deviation or signal-invalidation policy.

Planned fix:

- Add `valid_until`, maximum deviation, cancel/replace attempts and session expiry.

### P1 — live execution is scalar-price based

The engine can use cached/yfinance prices and two-decimal targets without current bid/ask/spread/tick-size evidence.

Planned fix:

- Use broker executable quotes for live triggers.
- Add quote age, spread and liquidity checks.
- Use Decimal and broker tick/quantity increments.

### P1 — Tradier silently truncates fractional quantity

The adapter converts quantity with `int(order.quantity)`.

Planned fix:

- Add broker capability metadata and normalize quantity before parent planning.

### P1 — cycle compounding is not fully broker-cash based

Profitable exits increase strategy capital, but the next cycle does not yet cap against settled cash, buying power, fees, reservations and partial positions.

Planned fix:

- Add durable cycle accounting and compound realized net P&L only.

## Repair order

1. Runtime idempotency wiring and application test.
2. Parent/child completion state.
3. Broker quote and quantity capability contracts.
4. Cancel/replace lifecycle.
5. Net cycle-capital accounting.
6. Full workflow run and source review.

## Status

In progress.
