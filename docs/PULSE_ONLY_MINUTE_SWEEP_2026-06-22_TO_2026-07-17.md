# Pulse-only minute-candle bracket sweep

## Scope

This replay removes Sentinel Edge from the decision loop and starts Pulse with all 20 test tickers configured for the full period.

- Period: 2026-06-22 13:30 UTC through 2026-07-17 20:00 UTC
- Interval: one-minute OHLCV
- Regular-session bars: 127,858
- Trading sessions: 19
- Tickers configured at start: 20
- Starting capital: $10,000
- Base power: $500 per ticker
- Pulse strategy: native custom bracket behavior
- Edge decisions and handoffs: none
- Auto-rebracket: off, matching `TickerConfig` default
- Re-entry cooldown: five minutes
- Positive-profit compounding: enabled, matching `TickerConfig` default
- Cost assumption: 10 basis points per completed round trip

The 20 configured symbols were:

`AMD`, `MU`, `AMAT`, `KLAC`, `AVGO`, `TSLA`, `META`, `MSFT`, `GOOGL`, `AMZN`, `PLTR`, `SOFI`, `HOOD`, `COIN`, `RIVN`, `BIYA`, `SLND`, `CJMB`, `BNRG`, and `BATL`.

The five penny-stock breakout symbols were `BIYA`, `SLND`, `CJMB`, `BNRG`, and `BATL`.

## Replay assumptions

Pulse production calculates a buy target from its average price, then calculates sell and stop targets from the filled entry. To avoid look-ahead while using only the supplied month of bars, the replay uses the expanding mean of prior completed session closes, capped at 30 sessions. The first session is seeded from its regular-session open.

Percentage mode uses:

- Buy target: average × (1 − width)
- Sell target: entry × (1 + width)
- Stop target: entry × (1 − 2 × width)

Dollar mode uses Pulse absolute-price fields causally as:

- Buy target: average − $X
- Sell target: entry + $X
- Stop target: entry − $2X

Limit orders fill at the target when crossed, with opening-gap price improvement. When a one-minute candle touches both target and stop and order sequence is unknowable, the replay conservatively applies the stop first. Remaining positions are liquidated at the final historical minute for a closed-period comparison.

## Percentage sweep

| Symmetric width | Net return | Net P&L | Max drawdown | Trades | Win rate | Profit factor |
|---:|---:|---:|---:|---:|---:|---:|
| 0.25% | -38.2672% | -$3,826.72 | 38.5180% | 4,801 | 62.2162% | 0.6628 |
| 0.50% | -17.0788% | -$1,707.88 | 17.1845% | 2,409 | 63.7609% | 0.8361 |
| 0.75% | +16.3356% | +$1,633.56 | 5.9619% | 1,508 | 65.3183% | 1.1642 |
| 0.90% | +19.5079% | +$1,950.79 | 6.2502% | 1,251 | 65.0679% | 1.2011 |
| 1.00% | +24.2606% | +$2,426.06 | 7.1442% | 1,089 | 65.7484% | 1.2469 |
| 1.10% | +26.0275% | +$2,602.75 | 7.7255% | 968 | 66.4256% | 1.2564 |
| **1.20%** | **+29.3430%** | **+$2,934.30** | **6.8044%** | **861** | **67.1312%** | **1.3071** |
| 1.25% | +20.3911% | +$2,039.11 | 6.1107% | 817 | 66.8299% | 1.2342 |
| 1.50% | +18.8572% | +$1,885.72 | 5.5396% | 650 | 66.6154% | 1.2578 |
| 2.00% | +17.2268% | +$1,722.68 | 7.0996% | 424 | 65.3302% | 1.3178 |
| 3.00% | +22.1538% | +$2,215.38 | 5.6200% | 229 | 67.6856% | 1.6433 |
| 4.00% | +16.3789% | +$1,637.89 | 5.2122% | 137 | 67.8832% | 1.7358 |
| 5.00% | +13.9941% | +$1,399.41 | 4.0755% | 94 | 68.0851% | 1.7909 |

### Percentage interpretation

The overall winner is 1.20%, but the five breakout penny stocks generated +$3,416.67 while the other 15 stocks generated -$482.37. The penny names were selected because they broke out during the test month, so this is an intentionally biased squeeze stress test rather than representative universe selection.

Excluding those five penny stocks, the strongest tested percentage width was 4.00%, with approximately +$112.45. The broader non-penny universe therefore supports a looser range than the overall penny-dominated result.

At the 1.20% winner:

- Completed trades: 861
- Sell-target exits: 578
- Stop exits: 275
- Period-end exits: 8
- Penny-stock trades: 429
- Fixed-$500-power control: +$1,195.91, or +11.9591%

The fixed-power control remains profitable, so the direction is not solely caused by compounding. However, Pulse compounds only positive realized P&L and does not reduce configured base power after losses; this can make the native compounded result exceed a capital-constrained account simulation.

## Dollar sweep

| Symmetric cash width | Net return | Net P&L | Max drawdown | Trades | Symbols traded | Profit factor |
|---:|---:|---:|---:|---:|---:|---:|
| $0.05 | -41.1586% | -$4,115.86 | 43.2533% | 7,775 | 20 | 0.4143 |
| $0.10 | -40.5554% | -$4,055.54 | 40.5915% | 7,503 | 19 | 0.3523 |
| $0.25 | -39.7097% | -$3,970.97 | 39.7791% | 6,600 | 16 | 0.3056 |
| $0.50 | -32.6466% | -$3,264.66 | 32.7422% | 5,113 | 15 | 0.3770 |
| $1.00 | -23.7412% | -$2,374.12 | 23.8549% | 3,400 | 15 | 0.5399 |
| $3.00 | -11.1328% | -$1,113.28 | 11.1462% | 1,186 | 13 | 0.6970 |
| $5.00 | -5.6413% | -$564.13 | 7.7933% | 622 | 13 | 0.8072 |
| $10.00 | -1.4043% | -$140.43 | 5.3320% | 223 | 12 | 0.9213 |
| $20.00 | +0.3165% | +$31.65 | 4.0727% | 69 | 8 | 1.0364 |
| **$30.00** | **+0.6516%** | **+$65.16** | **3.7082%** | **35** | **4** | **1.1010** |
| $50.00 | -0.3099% | -$30.99 | 2.8385% | 13 | 3 | 0.9102 |
| $75.00 | +0.6401% | +$64.01 | 1.5286% | 8 | 2 | 1.3304 |
| $100.00 | +0.1598% | +$15.98 | 2.3666% | 5 | 2 | 1.1165 |

### Dollar interpretation

The best single global dollar width was $30, producing +$65.16 with compounding. The fixed-power control produced +$100.14. It traded only four high-priced symbols and did not trade any penny stock.

A single cash width is not suitable for a universe whose historical prices range from less than $1 to more than $1,000. The best observed width differs sharply by price bucket:

- Below $5: $0.05
- $5–$25: $1.00
- $25–$100: $8.00
- $100 and above: $30.00

Those bucket values are descriptive and heavily in-sample; they are not promoted settings.

## Conclusion

- Pulse-only percentage brackets were strongest at 1.20% for the complete, breakout-biased universe.
- For the 15 non-penny stocks, 4.00% was the stronger tested range.
- Tight percentage ranges of 0.25% and 0.50% overtraded and lost heavily after costs.
- A global dollar bracket performed poorly because the universe contains radically different price scales.
- $30 was the best global cash width, but its small sample and four-symbol coverage are inadequate for promotion.
- No live Pulse settings were changed.

Before any promotion, repeat the percentage result on a universe selected before the test window, separate penny stocks into their own risk profile, and validate the non-penny 3%–5% region on independent months.