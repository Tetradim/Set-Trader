# Pulse-only auto-rebracket replay — June 22 to July 17, 2026

## Scope

- Edge absent.
- All 20 test tickers configured in Pulse at the start.
- 127,858 regular-session one-minute bars across 19 sessions.
- Pulse-faithful price input: replay close rounded to cents, rather than an intrabar high/low touch assumption.
- Default auto-rebracket: $2.00 threshold, $0.80 spread, $0.10 buffer, $0.50 minimum drift, 10 samples, no cooldown.
- 10-basis-point round-trip cost assumption.
- Native positive-only compounding and fixed-$500-power controls both tested.

## Direct percentage result

| Profile | Net P&L | Return | Max drawdown | Trades | Re-brackets |
|---|---:|---:|---:|---:|---:|
| 2% re-bracket off, native | $5,498.63 | 54.99% | 6.50% | 562 | 0 |
| 2% default re-bracket on, native | $5,203.25 | 52.03% | 34.85% | 1,256 | 1,853 |
| 2% re-bracket off, fixed power | $1,475.99 | 14.76% | 5.62% | 562 | 0 |
| 2% default re-bracket on, fixed power | $820.87 | 8.21% | 6.59% | 1,256 | 1,853 |

Default auto-rebracket did not improve the 2% percentage profile. In the fixed-power control it reduced profit by **$655.12** and increased drawdown by **0.97 percentage points**.

## Why the default percentage profile wins and loses

- Original-bracket entries earned **$5,475.76**.
- Re-bracketed `DOWN` entries earned **$1,532.82**.
- Re-bracketed `UP` entries lost **$1,805.33**, despite an 84.5% win rate.
- `UP` entries averaged roughly +0.63% on winners and -4.57% on losers. The small $0.80 absolute target created by re-bracketing did not match the still-percentage-based stop.
- Target exits produced **$23,359.60**; stops lost **$18,079.07**.
- 1,094 of 1,853 re-brackets occurred during the five-minute re-entry cooldown, and 248 occurred immediately after an exit.
- Re-bracket events were concentrated in high-priced names: MU 447, AMD 264, and AMAT 243. The same absolute dollar settings barely affect most sub-$2 stocks.

## Cash-mode result is not a valid $75 strategy result

The apparent cash winner was $75 with default re-bracket on:

- Native P&L: **$5,963.43**.
- Fixed-power P&L: **$6,342.43**.
- Penny contribution in fixed power: **$6,665.66**.
- Ordinary-stock contribution: **-$323.23**.

This happens because re-bracketing replaces the $75 buy/sell setup with a $0.80 absolute buy/sell spread while the original cash stop remains entry minus $150. On BIYA, the first re-bracketed position entered at $0.32, had a $1.12 target and an effectively unreachable $0.01 stop, then exited at $4.31. The result measures a bracket-mode mismatch plus a penny breakout, not a stable $75 cash strategy.

## Recommended-profile tests

- A 30-minute cooldown reduced the hybrid 2% penny/5% ordinary profile to 245 re-brackets and made re-bracketed entries positive, but fixed-power profit was **$1,577.28**; penny stocks contributed **$1,793.04** and ordinary stocks lost **$215.76**.
- Price-normalized re-brackets produced high in-sample fixed-power returns, but 6,654 events and all net profit came from the ex-post-selected penny breakouts. Ordinary stocks lost **$326.51**.
- The price-bucket cash profile with default re-bracket failed its second-half fixed-power test at **-$78.80**.

## Walk-forward results

The month was split into 10 training sessions and 9 test sessions.

| First-half selected profile | Second-half fixed-power P&L | Drawdown | Penny P&L | Ordinary P&L | Re-brackets |
|---|---:|---:|---:|---:|---:|
| 2% percentage, default re-bracket | $275.03 | 3.98% | $510.05 | -$235.02 | 862 |
| 2% penny / 5% ordinary, default re-bracket | $221.47 | 4.79% | $510.05 | -$288.57 | 457 |
| 2% penny / 5% ordinary, 60-minute cooldown | $280.89 | 5.19% | $510.05 | -$229.15 | 105 |
| Price-bucket cash, default re-bracket | -$78.80 | 5.80% | $101.96 | -$180.76 | 322 |
| Price-normalized re-bracket | $1,099.32 | 4.50% | $1,353.47 | -$254.16 | 3,217 |

No tested re-bracket profile made the ordinary 15-stock group profitable in the second-half test. Positive results remained dependent on the five penny stocks that were selected after observing their monthly breakouts.

## Operational conclusion

1. **Do not promote the current default auto-rebracket globally.** It increased trade count and drawdown while reducing fixed-power percentage profit.
2. **Do not interpret the cash-mode winner as valid.** Re-bracketing changes buy/sell mode but leaves the stop in its previous mode, creating incoherent risk.
3. **A 30–60 minute cooldown is safer than no cooldown**, but it has not established broad profitability.
4. **Price-normalized per-ticker settings need a separate penny-only paper experiment**, event-rate limits, and an independent month. They are too churn-heavy and selection-biased for promotion.
5. The next implementation target should make a re-bracket atomic: update buy, sell, and stop together; preserve an explicit reward/risk relationship; reject sell targets at or below the prospective entry; and prevent re-bracketing during re-entry cooldown unless explicitly enabled.
