# Pulse continuous bracket replay — non-penny summary

The replay used AMD, MU, AMAT, KLAC, AVGO, TSLA, META, MSFT, GOOGL, AMZN, PLTR, SOFI, HOOD, COIN, and RIVN. BIYA, SLND, CJMB, BNRG, and BATL were excluded.

Test dimensions: $2,000 starting power per ticker; native positive-profit compounding and fixed controls; dollar gaps from $0.01 to $1.00; percentage gaps from 0.01% to 0.50%; re-bracket on/off; no trailing, delayed trailing, and trailing active at entry; Pulse-only and actual 30-minute Edge authorization; 0–10 basis-point cost cases.

Results:

- A universal one-cent target was negative even at ideal zero-cost threshold fills because these higher-priced symbols produced roughly a 50% cycle win rate and one cent was a very small percentage move.
- Best full-month Pulse challenger: 0.30%, re-bracket on, trailing active at entry. Ideal threshold result: +$5,756.16 on $30,000, or +19.19%. Fixed-power control: +15.19%.
- Best fixed-dollar challenger: $1.00, re-bracket on, trailing active at entry. Ideal result: +14.74%.
- Untouched final-nine-session result for the training-selected 0.30% profile: +7.29% at zero cost and +4.86% at 1 bp. A 0.50% profile returned +2.45% at 2 bps.
- No sufficiently active profile remained profitable at 5 or 10 bps.
- Edge reduced activity and profit; it remains useful as an optional authorization control rather than the continuous strategy's main entry engine.
- Sampled-close stop execution turned the strongest ideal profile negative. Quote, tick, or second-level validation is required before live integration.

No live settings or live execution paths were changed.
