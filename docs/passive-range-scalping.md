# Passive Range Scalping

Passive range mode is an opt-in execution path for repeatedly capturing a configured price range with resting limit orders. It does not use the normal five-second price-triggered bracket path.

## Order lifecycle

1. Pulse immediately submits or simulates a resting buy limit.
2. Pulse waits for cumulative broker fill evidence; a quote touch is not treated as a live fill.
3. After a confirmed buy fill, Pulse immediately rests a sell limit for the confirmed quantity.
4. After a confirmed sell fill, Pulse records the completed cycle and optionally compounds the result.
5. Pulse waits for `passive_reentry_seconds`, then arms the next buy.

Live mode currently requires exactly one positively allocated broker per ticker and is implemented for Alpaca and Tradier. Unsupported adapters fail closed because they cannot provide the required order-status evidence.

## QSI example

The following ticker update configures an exact $0.9550 buy and $0.9660 sell with whole-share sizing:

```json
{
  "base_power": 500,
  "buy_percent": false,
  "buy_offset": 0.955,
  "buy_order_type": "limit",
  "sell_percent": false,
  "sell_offset": 0.966,
  "sell_order_type": "limit",
  "stop_percent": false,
  "stop_offset": 0.92,
  "stop_order_type": "market",
  "price_tick_size": 0.0001,
  "passive_range_enabled": true,
  "passive_reentry_seconds": 5,
  "passive_order_ttl_seconds": 300,
  "passive_cancel_on_partial": true,
  "passive_fractional_shares": false,
  "passive_paper_min_touches": 2
}
```

Send the document with:

```text
PUT /api/tickers/QSI
Content-Type: application/json
```

With $500 of buying power, whole-share sizing submits 523 shares because 523 × $0.9550 is below $500 while 524 shares would exceed it. A target-to-target completed cycle has gross P&L of:

```text
523 × ($0.9660 - $0.9550) = $5.753
```

## Price precision

Pulse now builds passive prices with `Decimal` and normalizes to an explicit tick size. When `price_tick_size` is zero, the conservative inference is:

- below $1: `0.0001`
- at or above $1: `0.01`

Set the field explicitly when the broker or venue requires a different increment. Buy limits round down to the configured tick and sell limits round up, preventing Pulse from bidding above or offering below the requested target.

## Partial fills

`passive_cancel_on_partial` defaults to `true`. When a live order is partially filled, Pulse cancels the remainder and manages only the confirmed quantity. This avoids leaving an expanding entry order working while Pulse is already offering filled shares for sale.

If the sell partially fills, Pulse records the confirmed sold quantity and rests a new sell for the remaining position.

## Range-break protection

Passive positions use the existing ticker stop configuration. When the current price reaches the stop:

1. Pulse cancels the resting sell.
2. Live mode requires confirmed cancellation before sending a market exit.
3. The market exit must return terminal broker fill evidence.
4. The completed cycle is stored with `exit_reason: "stop"`.

A failed sell cancellation blocks the market exit to prevent an accidental double-sell. This fail-closed state requires operator attention.

## Paper behavior

Paper mode is intentionally conservative but remains a simulator:

- a buy fills only when ask is at or below the buy limit;
- a sell fills only when bid is at or above the sell limit;
- when bid/ask is unavailable, last price is used;
- `passive_paper_min_touches` requires repeated qualifying evaluations before a fill.

Paper fills do not model exchange queue priority. Profitable paper results therefore require live shadow testing before capital is enabled.

## Durable state and telemetry

Working order and cycle state is persisted in `passive_range_state`. Completed cycles are written to `passive_range_cycles` with:

- target and actual entry/exit prices;
- confirmed quantity;
- gross P&L;
- cycle start, fill, and completion timestamps;
- duration;
- exit reason;
- paper/live mode.

The broker order remains the source of truth in live mode. Pulse does not recycle capital from a pending order or a price touch.

## Initial operating limits

Use these controls for the first live validation:

- one ticker;
- one production-supported broker;
- the smallest practical allocation;
- whole shares;
- a defined stop below the range;
- no automatic averaging down;
- review every cycle against the broker order history.

The mode should remain paper or shadow-only until quote timestamps, order acknowledgements, partial fills, cancellations, and completed cycles agree with the broker account.
