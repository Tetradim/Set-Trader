# Pulse Scalp Follow v2 — paper replay result

## What was tested

- A sticky runtime zone that re-centers only after confirmed migration.
- The center never follows price tick-for-tick.
- Buy, target and stop freeze atomically after entry.
- Re-centering is blocked during position ownership and exit cooldown.
- Trend-pause and re-center-rate limits prevent chasing a running market.
- All positions liquidate before the next session.

## Validation split

- 127,858 regular-session one-minute bars, 20 symbols, 19 sessions.
- First 10 sessions selected parameters; final 9 sessions were untouched.
- Primary model uses Pulse replay semantics: minute close rounded to cents.
- Fixed $500 power per symbol and 10-basis-point total round-trip cost.
- SPY/QQQ were not in the inherited artifact; the closest SPY-style width and a liquid-stock proxy were tested.

## Recommended paper pilot from the training half

- Runtime half-width: 0.30% of center.
- Re-center trigger: max(6 x half-width, causal ATR14).
- Confirmation: 3 closes upward; 5 closes plus stabilization downward.
- Re-center cooldown: 15 minutes; maximum 4 per hour.
- Stop: 1.5R.
- No 60-minute forced exit; end-of-day liquidation remains mandatory.
- Loss cooldown: 15 minutes.

## Untouched second-half result

- Total P&L: **$923.66** (9.24%).
- Trades: **556**; win rate **60.25%**; profit factor **1.435**.
- Drawdown: **$787.36 / 7.39%**.
- Liquid-proxy P&L: **$2.11**.
- Ordinary-stock P&L: **-$93.32**; penny-stock P&L: **$1,016.98**.
- Re-centers: **154** (121 up / 33 down).

## Operational controls

| Profile | P&L | Trades | Drawdown | Ordinary P&L | Penny P&L | Re-centers |
|---|---:|---:|---:|---:|---:|---:|
| Step-follow v2 pilot | $923.66 | 556 | 7.39% | -$93.32 | $1,016.98 | 154 |
| Static zone | $495.53 | 378 | 3.96% | -$16.87 | $512.40 | 0 |
| Continuous chase bug | $0.00 | 0 | 0.00% | $0.00 | $0.00 | 0 |
| No trend pause | $1,105.09 | 525 | 7.14% | -$78.28 | $1,183.36 | 113 |
| Native positive compounding | $1,424.32 | 556 | 10.76% | -$98.40 | $1,522.73 | 154 |

## Original SPY-like tight width

- The closest tested width was 0.075% of price, approximately a $0.56 half-width at SPY $750.
- It was not selected by the training period.
- On the untouched test it produced:
  - Close-sampled P&L **-$216.45**, 1,750 trades, profit factor 0.931.
  - OHLC-touch sensitivity **-$2,941.76**, 2,714 trades.
- The one-minute candle often crosses both a tight target and stop. Without quote/tick sequencing, stop-first or target-first assumptions dominate the result.

## Cost sensitivity for ordinary stocks

| Total round-trip cost | Ordinary-stock P&L |
|---:|---:|
| 0 bps | $89.18 |
| 2 bps | $52.68 |
| 5 bps | -$2.07 |
| 10 bps | -$93.32 |

The liquid proxy earned $114.61 before costs, $92.11 at 2 bps, $58.36 at 5 bps, and $2.11 at 10 bps. The result is therefore execution-cost sensitive even before quote-sequence uncertainty is considered.

## Why Pulse won and lost

### Exit attribution

| Exit | Trades | Net P&L | Average P&L | Average hold |
|---|---:|---:|---:|---:|
| Profit target | 306 | $2,883.05 | $9.42 | 39.7 min |
| End of day | 84 | -$166.09 | -$1.98 | 245.7 min |
| Hard stop | 166 | -$1,793.30 | -$10.80 | 39.9 min |

The profile won by producing enough roughly $9.42 target exits to overcome approximately $10.80 hard-stop losses and the round-trip cost. Ordinary stocks did not generate enough gross expectancy to absorb the assumed 10-basis-point cost.

### Re-center attribution

| Last center direction | Trades | Net P&L | Win rate |
|---|---:|---:|---:|
| Up | 194 | $392.77 | 62.89% |
| Initial daily zone | 326 | $387.89 | 58.28% |
| Down | 36 | $143.00 | 63.89% |

Unlike the previous implementation, both upward and downward step-follow entries were profitable in the aggregate. The remaining concern is concentration in the five ex-post-selected penny breakouts, not a negative re-center direction.

## Conclusion

1. The new state machine fixes the mechanical problem: the zone moved in discrete steps and the continuous-follow control placed zero trades.
2. Step-follow restored trading after market migration and beat a static zone on total P&L.
3. It did not establish broad ordinary-stock profitability at the inherited 10-basis-point cost assumption.
4. The exact tight SPY-style scalp cannot be validated reliably with one-minute candles; tick or quote data is required.
5. The safest next test is SPY/QQQ-only paper replay with bid/ask or tick sequencing, end-of-day liquidation, and the controller kept behind an explicit paper-only flag.
6. No live settings were changed.
