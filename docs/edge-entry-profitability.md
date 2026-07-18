# Edge Entry Profitability Enforcement

Pulse preserves the strategy edge supplied by Sentinel Edge. A valid trade card is necessary but not sufficient: the entry must still be executable inside the price and cost limits carried by Edge.

## Contract

The public handoff remains `edge.pulse.handoff.v1`. BUY handoffs use the existing nested `edge.execution_intent.v2` object with an `edge.entry_policy.v1` block and nested `edge.execution_style.v1` policy.

The entry policy includes:

- Edge reference and ideal entry price.
- Maximum acceptable executable entry price.
- Expected value after Edge's baseline cost estimate.
- Baseline estimated round-trip cost.
- Maximum execution-cost allowance.
- Minimum expected value that must remain after updated execution costs.
- Maximum spread allowance.
- Trade-card and position identity.
- Entry trigger state.
- ORB confirmation and short-squeeze state.

The execution-style policy includes:

- Preferred and allowed execution styles.
- Passive-limit price offset.
- Timed-limit price buffer and timeout.
- Breakout stop trigger.
- Post-fill measurement horizons.
- Strategy, ORB, and squeeze context used for attribution.

## Two profitability guard points

### Handoff preflight

Before Pulse changes ticker capital or creates execution state, it validates the current handoff price and any quote supplied in metadata. Pulse also selects a valid style that can satisfy Edge's maximum entry.

### Fresh broker quote

For live orders, Pulse validates the policy and reselects exact order prices against fresh executable bid/ask data immediately before placement. The BUY-side executable price is the ask.

This second check is essential because Edge's decision can be valid while the market becomes untradeable before broker submission.

## Execution styles

### Passive limit

`passive_limit` places a day limit near the bid without crossing above Edge's ideal reference. It is intended for pullback, continuation, and reversal entries where fill quality is more important than immediate participation.

A passive order can remain broker-pending. Pulse treats that as accepted-but-reconciliation-pending, not as a fill. The position is not advanced until durable broker evidence confirms quantity and price.

### Timed limit

`timed_limit` places a bounded marketable limit using the fresh ask plus Edge's configured buffer. Alpaca and Tradier poll the order until the configured deadline and cancel an unfilled remainder when the timeout expires.

The order cannot exceed `maximum_entry_price`, even when its configured buffer would otherwise do so.

### Breakout stop-limit

`breakout_stop_limit` uses the Edge trigger—normally an ORB high or confirmed squeeze trigger—as the stop price and places a capped limit above it. It is selected for confirmed ORB breakouts and `short_squeeze_breakout` theses.

If the required trigger context is missing, Pulse falls back to `timed_limit`; it does not manufacture an ungrounded stop trigger.

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
- `ENTRY_DEFERRED_EXECUTION_STYLE_UNAVAILABLE`: no allowed style could satisfy the required quote or trigger inputs.

A rejected or deferred entry does not count as accepted and does not advance the Edge trade card.

## Attribution

Pulse writes `pulse.execution_attribution.v1` records containing:

- Selected style and broker order type.
- Arrival bid, ask, spread, and reference price.
- Limit and stop prices.
- Fill price and quantity.
- Fill slippage in basis points.
- Missed-fill classification for canceled, expired, rejected, deferred, or failed zero-fill orders.
- Post-fill movement at the Edge-requested horizons, initially 30, 60, and 300 seconds.

Attribution is persisted on the ticker, trade record, broker-order ledger, and `execution_attributions` collection. A filled trade opens a marking watch; subsequent ticker evaluations record each due post-fill horizon once.

The experiment compares styles using:

- Median and tail fill slippage.
- Fill rate and missed-fill rate.
- Partial-fill and reconciliation rate.
- Post-fill movement after 30, 60, and 300 seconds.
- Net expectancy after execution costs.
- Adverse selection: whether faster fills are followed by negative immediate movement.

## Audit

Pulse persists `edge_entry_policy_audit` on the ticker with:

- Normalized entry and execution-style policy.
- Handoff preflight measurement.
- Fresh broker execution checks.
- Style selection history.
- Structured rejection details.
- Final response status and reason.
- Initial execution attribution.

## Runtime settings

- `PULSE_ESTIMATED_ROUND_TRIP_FEES_BPS`
- `PULSE_EXECUTION_SLIPPAGE_BUFFER_BPS`
- Edge-provided `timeout_seconds`, `passive_offset_bps`, and `aggressive_limit_buffer_bps`
- Existing live quote controls such as `PULSE_MAX_LIVE_SPREAD_PCT` and `PULSE_MAX_LIVE_QUOTE_AGE_SECONDS` remain active as broader safety limits.

## Profitability hypothesis

A correct forecast can still lose money when Pulse pays too much to enter. Style selection should improve realized expectancy by matching urgency to the thesis: passive fills for pullbacks, bounded timed participation for ordinary trends, and stop-limit confirmation for ORB or squeeze breakouts.

Promotion requires replay and paper evidence showing that each style improves net expectancy relative to the alternatives after accounting for missed winners, partial fills, fees, and adverse selection. No style is promoted solely because it fills more often.
