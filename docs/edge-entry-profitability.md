# Edge Entry Profitability Enforcement

Pulse preserves the strategy edge supplied by Sentinel Edge. A valid trade card is necessary but not sufficient: the entry must still be executable inside the price and cost limits carried by Edge.

## Contract

The public handoff remains `edge.pulse.handoff.v1`. BUY handoffs use the existing nested `edge.execution_intent.v2` object with an additional `edge.entry_policy.v1` block.

The policy includes:

- Edge reference and ideal entry price.
- Maximum acceptable executable entry price.
- Expected value after Edge's baseline cost estimate.
- Baseline estimated round-trip cost.
- Maximum execution-cost allowance.
- Minimum expected value that must remain after updated execution costs.
- Maximum spread allowance.
- Trade-card and position identity.
- Entry trigger state.

## Two guard points

### Handoff preflight

Before Pulse changes ticker capital or creates execution state, it validates the current handoff price and any quote supplied in metadata.

### Fresh broker quote

For live orders, Pulse validates the policy again against the fresh executable bid/ask obtained for each assigned broker immediately before placement. The BUY-side executable price is the ask.

This second check is essential because Edge's decision can be valid while the market becomes untradeable before broker submission.

## Cost model

Pulse records:

- Reference price.
- Observed and executable price.
- Bid, ask, and spread percentage.
- Adverse movement from the Edge reference.
- Configured fee estimate.
- Configured slippage buffer.
- Estimated execution cost.
- Incremental cost above Edge's original estimate.
- Expected value remaining after the incremental cost.

The calculation uses the larger of spread percentage and adverse movement, then adds configured fees and slippage buffer. This avoids double-counting a last/mid reference while remaining conservative.

## Outcomes

- `ENTRY_REJECTED_MAXIMUM_ENTRY_PRICE`: executable ask exceeded the trade-card ceiling.
- `ENTRY_DEFERRED_POOR_LIQUIDITY`: spread or quote quality was temporarily unsuitable.
- `ENTRY_REJECTED_SLIPPAGE_LIMIT`: estimated execution cost exceeded the strategy allowance.
- `ENTRY_REJECTED_EXPECTED_VALUE_ERODED`: the entry would leave less expected value than Edge requires.
- `ENTRY_DEFERRED_PRICE_UNAVAILABLE`: Pulse could not establish a positive executable price.

A rejected or deferred entry does not count as accepted and does not advance the Edge trade card.

## Audit

Pulse persists `edge_entry_policy_audit` on the ticker with:

- Normalized policy.
- Handoff preflight measurement.
- Fresh broker execution checks.
- Structured rejection details.
- Final response status and reason.

## Runtime settings

- `PULSE_ESTIMATED_ROUND_TRIP_FEES_BPS`
- `PULSE_EXECUTION_SLIPPAGE_BUFFER_BPS`
- Existing live quote controls such as `PULSE_MAX_LIVE_SPREAD_PCT` and `PULSE_MAX_LIVE_QUOTE_AGE_SECONDS` remain active as broader safety limits.

## Profitability hypothesis

A correct forecast can still lose money when Pulse pays too much to enter. These guards should improve realized expectancy by preventing price chasing, wide-spread entries, and fills whose updated cost consumes the remaining strategy edge.

Promotion requires replay and paper evidence showing that avoided execution losses exceed missed-opportunity cost after fees.
