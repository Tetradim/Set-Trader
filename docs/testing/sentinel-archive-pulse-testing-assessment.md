# Sentinel Archive as a Sentinel Pulse Test Harness

**Assessment date:** 2026-07-19  
**Pulse baseline reviewed:** `Beta-Maximum` at `ad42284e9c43456e79179f2577d3ff08b6845beb`  
**Archive baseline reviewed:** `main` at `bd9a7c59f704ed757c9f619b2d96ad6e6e746633`

## Executive verdict

Sentinel Archive **can become a strong end-to-end test harness for Sentinel Pulse**, but the correct integration point is Archive's vendor-neutral `archive.general.v1` replay and virtual-broker API. Archive's older Pulse-compatible handoff simulator should **not** be used as evidence that Pulse itself selected, submitted, filled, reconciled, or exited a trade.

Three distinct claims must remain separate:

| Test claim | Can Archive support it now? | Confidence and qualification |
| --- | --- | --- |
| Replay recorded prices through Pulse's native decision code | **Yes, partially** | Archive's native profitability study imports Pulse's `TradingEngine` and calls `evaluate_ticker()` once per recorded bar. It is useful for strategy regression and walk-forward research, but it stubs infrastructure and bypasses the real broker/fill lifecycle. |
| Validate Edge/Pulse handoff contracts without running Pulse | **Yes** | Archive's legacy simulator accepts `edge.pulse.handoff.v1` and simulates the result. This tests the contract and Archive, not Pulse's runtime. |
| Run the real Pulse service against recorded data and a virtual broker | **Not wired yet, but feasible** | Archive General API already supplies the needed replay, order, fill, account, position, and reporting primitives. Pulse needs an Archive broker adapter, replay-aware market-history source, asynchronous fill synchronization, and a virtual clock. |

The most important conclusion is that **replaying close prices alone is not enough to certify Pulse**. A credible full-stack test must ensure that:

1. Pulse receives only market information released up to the virtual timestamp.
2. Pulse's own strategy and risk code creates the order.
3. Pulse sends the order through its normal broker manager and safety gateway.
4. Archive, acting only as a broker, accepts, rejects, partially fills, fills, or cancels it.
5. Pulse consumes the resulting broker truth and updates its own state once.
6. Pulse and Archive independently agree on orders, fills, positions, cash, and P&L at the end of the run.

## Review scope and evidence standard

This assessment is based on static review of both repositories, their tests, documentation, and recent committed study artifacts. It did **not** execute the repositories locally. At the time of review, Archive's latest `main` commit had no attached GitHub status checks, so the presence of test files is treated as implementation evidence rather than a claim that the latest suite passed in CI.

The review intentionally distinguishes:

- code that runs Pulse's native decision logic;
- code that merely imitates a Pulse endpoint or handoff result;
- code that can act as an external market and broker for the real Pulse process;
- historical research results versus operational safety certification.

## What Sentinel Archive currently contains

Archive has two different simulation architectures plus an external study harness. They serve different purposes and should not be described as one test engine.

### 1. Legacy Pulse/Edge handoff simulator

Primary code:

- `sentinel_archive/core.py`
- Pulse-compatible and Edge-compatible routes in `sentinel_archive/api.py`
- simulator checks in `sentinel_archive/paper_burnin.py`

This engine:

- imports OHLCV bars;
- advances replay by timestamp batches;
- stores a current close price;
- accepts `edge.pulse.handoff.v1` payloads;
- applies its own buy, sell, regular stop, trailing stop, take-profit, DCA, stop-buying, and emergency-exit behavior;
- maintains an in-memory simulated account;
- rejects handoffs marked `mode=live`;
- supports artificial fill ratios, commission, slippage, and allocation caps.

This is valuable for testing:

- handoff schema compatibility;
- Core or Edge workflows when Pulse is unavailable;
- idempotency of handoff IDs;
- UI and operator flows against a safe local service;
- Archive's own stop/trailing/account behavior.

It is **not** valid evidence that Pulse worked because Archive itself interprets the action and mutates the simulated account. Pulse's `TradingEngine`, broker manager, risk controls, state persistence, order-result handling, and reconciliation are not in the loop.

### 2. `archive.general.v1` replay and virtual brokerage API

Primary code:

- `sentinel_archive/general_api/models.py`
- `sentinel_archive/general_api/service.py`
- `sentinel_archive/general_api/router.py`
- `docs/GENERAL_API.md`

This is the correct foundation for testing Pulse. It has an explicit non-strategy boundary: replay cannot create an order, and every order must be submitted by an authenticated participant.

Implemented capabilities relevant to Pulse include:

- recorded or synthetic OHLCV CSV import with SHA-256 dataset identity;
- synchronized multi-symbol replay on one virtual clock;
- manual one-batch stepping and accelerated automatic playback;
- participant registration with isolated accounts and tokens;
- symbol subscriptions and future-data isolation;
- REST cursor polling and WebSocket event delivery;
- market, limit, and stop orders;
- next-bar execution semantics;
- volume-participation partial fills;
- commissions and slippage;
- idempotent client order IDs;
- reduce-only orders;
- OCO sibling cancellation;
- stock/crypto cash accounting;
- futures tick size, multiplier, and initial-margin handling;
- order, fill, account, position, and report endpoints;
- attributable reporting with `archive_generated_order_count: 0`.

Archive deliberately resolves an ambiguous OHLC bar conservatively: when the same bar touches both sides of an OCO bracket, stops are processed before limits. This is deterministic and avoids profit-biased assumptions, although it still cannot reveal the true intrabar path.

### 3. Native profitability replay study

Primary code and outputs:

- `scripts/run_native_profitability_study.py`
- `reports/sentinel-native-profitability-2026-07-17/report.md`
- `reports/sentinel-native-profitability-2026-07-17/report.json`

This study is more relevant to Pulse than the legacy simulator because it imports Pulse's native `TradingEngine` and calls `evaluate_ticker()` over recorded bars. It also uses a prior-data-only moving-average implementation, fingerprints its datasets, separates tuning and validation windows, and avoids inventing orders for bots that do not expose a candle-to-order loop.

Its limitations are material:

- it deliberately bypasses `trading/__init__.py` and therefore the final composed live-execution patch stack;
- it supplies a fake in-memory Mongo-like database;
- it stubs WebSocket, Telegram, and broker manager services;
- it sets `simulate_24_7`, removes trade and re-entry cooldowns, and overrides market/opening-window gates;
- it samples Pulse once per recorded candle close;
- it does not wait for General API broker fill acknowledgements;
- it applies modeled friction after Pulse's native paper fills instead of exercising an external broker lifecycle;
- it does not launch the FastAPI server, frontend, MongoDB, or normal startup/recovery sequence.

Therefore the study is useful for **strategy behavior, parameter selection, no-lookahead research, and regression comparisons**, but it is not a full-stack execution or safety certification.

## Existing Archive tests reviewed

Archive includes service-level and HTTP tests for the General API.

`tests/test_general_api_service.py` verifies, among other cases:

- replay without bot orders creates no P&L;
- Archive never reports Archive-generated orders;
- Pulse, Iron, and Edge participants can share one replay while accounts and private broker events remain isolated;
- a risk-controller directive can halt new opening orders while still allowing a reducing exit;
- client order IDs are idempotent;
- an ambiguous OCO bar fills the stop first and cancels the target;
- limited bar volume creates attributable partial fills over multiple bars.

`tests/test_general_api_http.py` verifies:

- participant routes require a bot token;
- unreleased future bars are not returned;
- an HTTP-submitted market order fills on the next released bar;
- account and report endpoints expose the resulting broker truth;
- the API specification declares that Archive contains no strategy logic.

These tests cover the virtual broker itself. They do not yet connect a running Pulse instance to that broker.

## Pulse compatibility analysis

### Broker interface compatibility is good

Pulse's `BrokerAdapter` contract already has the main operations Archive exposes:

- connection check;
- account retrieval;
- position retrieval;
- order placement;
- order cancellation;
- quote retrieval.

Pulse's `BrokerOrder` also has compatible fields for symbol, side, type, quantity, limit price, stop price, client/idempotency identifiers, broker order ID, status, fill price, and fill quantity.

An `ArchiveBrokerAdapter` can map these operations without changing Pulse's strategy layer.

### Pulse's registry is currently closed over known brokers

`backend/brokers/registry.py` hard-codes supported broker records and the adapter factory. Archive is not present. A real integration needs:

- an `archive` broker record;
- a factory branch for `ArchiveBrokerAdapter`;
- configuration fields for base URL, run ID, participant ID, and participant token;
- an explicit designation that Archive is simulation-only.

### The main blocker is asynchronous fill lifecycle

Archive accepts an order first and makes it eligible against a later released bar. A submit response can therefore be `accepted`, while the eventual result arrives as `partially_filled`, `filled`, `canceled`, or `rejected` after replay advances.

Pulse's current execution path is primarily immediate-result oriented:

- `accepted`, `new`, and `pending` are recognized as pending;
- a pending result causes `_place_live_order_or_raise()` to record a pending intent and raise instead of publishing a local trade;
- the engine mutates positions and records a trade only after the placement method returns as confirmed;
- there is no general background worker that consumes later broker fill events and completes the original engine action.

A simplistic Archive adapter that only returns the initial `accepted` response would therefore exercise order submission but not complete Pulse's position/accounting flow. A correct integration needs an asynchronous lifecycle:

1. submit the Pulse order with the Pulse idempotency key as Archive's `client_order_id`;
2. persist the pending intent and Archive order ID;
3. consume Archive events or poll the order/fill endpoints;
4. publish each new partial fill exactly once;
5. update Pulse's broker snapshot and authoritative position through reconciliation;
6. clear the pending intent when the order reaches a terminal state;
7. resume strategy eligibility only according to the final or partial state.

The adapter must not advance Archive's replay clock itself. Market-clock ownership belongs to the test coordinator so an order cannot secretly consume the next bar or create lookahead behavior.

### A quote adapter alone is insufficient

Pulse's `evaluate_ticker()` requests both:

- `PriceService.get_price(symbol)`; and
- `PriceService.get_avg_price(symbol, days)`.

Signal strategies can also request enriched OHLCV history through `get_enriched_market_data()` and `get_ohlcv()`.

Pulse's current internal replay feeds replay close values into `get_price()`, but `get_avg_price()` and historical OHLCV still use yfinance. During a historical replay this can produce three problems:

- the run is not offline or deterministic;
- the moving average can differ between executions;
- current provider history can include observations after the virtual replay timestamp, creating lookahead contamination.

The Archive integration therefore needs a replay-aware history source, not only `get_quote()`. It should maintain released bars per symbol and answer moving-average and strategy-history requests strictly from data at or before the current virtual timestamp.

### Pulse needs a virtual clock for time rules

Pulse contains behavior based on wall-clock `datetime.now()`, including:

- trade cooldowns;
- re-entry cooldowns;
- market-hours gates;
- opening-window and post-opening-window behavior;
- wait-a-day rules;
- auto-rebracket cooldowns;
- order-rate windows and timestamped persistence.

Accelerating a recorded day while those rules use the computer's current clock does not reproduce the recorded day. The existing native study works around this by disabling or overriding several rules, which means those rules are not actually tested.

A full replay harness needs an injectable clock interface. In Archive mode, Pulse should read Archive's virtual timestamp. In normal operation, it should read the real UTC clock. Tests must be able to advance the clock without sleeping.

### Safety boundary must be explicit

Archive must never be treated as a live broker. Recommended rules:

- the adapter refuses to initialize unless Pulse is in paper/simulation mode;
- a dedicated `SENTINEL_PULSE_ENABLE_ARCHIVE_EXECUTION=true` flag is required;
- Archive credentials are never accepted for any other broker ID;
- a run cannot mix Archive and real-money broker adapters;
- switching Pulse to live mode disconnects or disables Archive automatically;
- replay startup verifies no real broker order route is enabled;
- UI and health payloads display `ARCHIVE REPLAY`, not `LIVE`;
- test reports record the Pulse commit, Archive commit, dataset checksum, settings snapshot, and safety flags.

## Recommended integration architecture

### Component A: `ArchiveBrokerAdapter`

Suggested location: `backend/brokers/archive_adapter.py`

Configuration:

```json
{
  "base_url": "http://127.0.0.1:9200/api/general",
  "run_id": "replay-...",
  "participant_id": "pulse-test",
  "bot_token": "...",
  "poll_interval_ms": 50
}
```

Required mappings:

| Pulse method | Archive operation |
| --- | --- |
| `check_connection()` | `GET /spec`, `GET /runs/{run_id}`, and authenticated participant market/account read |
| `get_account()` | `GET /runs/{run_id}/participants/{participant_id}/account` |
| `get_positions()` | account positions from the same endpoint |
| `place_order()` | `POST /runs/{run_id}/participants/{participant_id}/orders` |
| `cancel_order()` | `DELETE /runs/{run_id}/participants/{participant_id}/orders/{order_id}` |
| `get_quote()` | latest released bar from `/market/latest` |
| `get_open_orders()` | list orders filtered to accepted/partially-filled states |
| order status | `GET /orders/{order_id}` or broker events |
| fills | `GET /fills` or `broker.order_*` event stream |

Mapping rules:

- Pulse idempotency key becomes Archive `client_order_id`.
- `BUY`/`SELL` and order type enums are normalized to lowercase Archive values.
- Pulse `STOP_LIMIT` must be rejected until Archive explicitly supports the same semantics.
- Archive decimal strings must be converted without losing quantity precision.
- `reduce_only` should be set for Pulse exits.
- broker order IDs must be preserved in Pulse audit records.
- repeated event reads must be deduplicated by Archive event sequence and fill ID.

### Component B: replay-aware price and history service

The market-data client should consume `market.bar` events and maintain, per symbol:

- current released OHLCV bar;
- ordered released-bar history;
- current virtual timestamp;
- event cursor/sequence;
- dataset identity and data kind.

It should implement:

- current price from released close;
- moving averages from released historical closes only;
- OHLCV DataFrames from released history only;
- no fallback to live broker feeds or yfinance while Archive replay is active;
- an explicit error when required warm-up history has not been released.

Warm-up data should be part of the dataset and released before the scored test window, or loaded into a separate immutable pre-window history that is known to precede the first decision timestamp.

### Component C: broker-event and reconciliation worker

A background task should:

- consume events by durable sequence cursor;
- handle accepted, rejected, partially filled, filled, canceled, and replay-completed events;
- persist its last consumed sequence;
- deduplicate fill IDs across reconnects;
- update pending intents;
- trigger authoritative broker reconciliation;
- compare Pulse and Archive positions after every fill;
- stop the run on unexplained divergence.

WebSocket is appropriate for interactive playback. Cursor-based REST polling is preferable for deterministic CI because the cursor is explicit and reconnect behavior is easier to assert.

### Component D: deterministic coordinator

A coordinator script or pytest fixture should own the sequence:

1. launch Archive and Pulse against isolated test storage;
2. import a fingerprinted dataset into Archive;
3. create a run;
4. register Pulse as a trader participant;
5. configure the Archive adapter and replay price source in Pulse;
6. seed Pulse ticker settings and risk state;
7. release one timestamp batch;
8. wait until Pulse has consumed that sequence and completed one evaluation;
9. assert any submitted orders;
10. release the next batch so eligible orders can fill;
11. wait until Pulse has consumed fills and reconciled;
12. continue until replay completion;
13. compare independent final reports;
14. save a machine-readable evidence bundle.

The coordinator should use barriers and cursors rather than arbitrary sleeps.

### Component E: evidence bundle

Each run should emit:

```text
outputs/<run-id>/
  manifest.json
  archive-report.json
  pulse-settings.json
  pulse-trades.jsonl
  pulse-audit.jsonl
  archive-events.jsonl
  reconciliation.json
  verdict.md
```

`manifest.json` should include:

- Pulse and Archive commit SHAs;
- dataset checksum and provenance;
- instrument specifications;
- replay interval and date range;
- strategy and ticker configuration;
- risk settings;
- execution assumptions;
- expected scenario assertions;
- whether any external network or broker was enabled.

## Minimum test matrix for Archive-backed Pulse testing

| Scenario | Market setup | Expected Pulse/Archive result |
| --- | --- | --- |
| No-signal control | Flat prices that never reach a rule | Zero Pulse orders, zero Archive fills, unchanged cash and P&L |
| Market entry | Pulse submits after bar N | Accepted at N, filled at bar N+1 open, one matching Pulse fill |
| Limit entry not touched | Next-bar low remains above buy limit | Order stays open or expires according to TIF; no Pulse position |
| Limit entry touched | Next-bar low crosses buy limit | Fill at deterministic Archive limit/open rule |
| Gap-through limit | Next bar opens better than limit | Fill at next open according to Archive rule |
| Stop exit | Next-bar low crosses stop | Reducing sell fills; position and P&L reconcile |
| Trailing exit | Released highs raise high-water mark, later low triggers | One exit only, no stale trailing state |
| Partial fill | Low volume restricts participation | Multiple unique fills; Pulse quantity equals cumulative broker quantity after each fill |
| Partial scale-in | Multiple configured buy legs | Each leg uses its configured allocation; weighted entry reconciles |
| Partial scale-out | Multiple sell legs | Remaining quantity never goes negative or double-decrements |
| Duplicate submission | Retry same client order ID | One Archive order and no duplicate Pulse position mutation |
| Pending reconnect | Disconnect after accepted, before fill | Cursor resumes; eventual fill applied once |
| OCO ambiguity | One bar touches stop and target | Stop-first result, target canceled, documented adverse assumption |
| Reduce-only oversell | Exit quantity exceeds holding | Archive rejection; Pulse retains authoritative position |
| Insufficient buying power | Entry exceeds account capacity | Broker rejection propagated to Pulse audit and strategy state |
| Kill switch | Activate global or symbol control before signal | Pulse submits no Archive order |
| Restricted symbol | Mark symbol restricted | Pulse submits no Archive order |
| Order-rate limit | Generate rapid signals under virtual clock | Rate control blocks excess orders using virtual 60-second window |
| Multi-symbol batch | Several symbols share timestamp | All see the same virtual time; no future symbol bar leaks |
| Multi-broker allocation | Archive plus controlled fake adapter, or multiple isolated Archive participants | Correct per-broker quantities; one failure cannot corrupt successful broker truth |
| Archive timeout | Inject HTTP delay/error | Circuit breaker and audit behavior occur without duplicate order |
| Empty position snapshot | Archive reports no position after exit | Pulse clears stale broker position |
| Pulse restart | Restart after fills with persisted cursor and order IDs | No duplicate fill; restored position equals Archive |
| Archive restart | Restart Archive during a run | Test must currently fail closed because General API state is in memory; later persistence should make this recoverable |
| Replay completion | Final batch consumed | No live-price fallback, run stops, reports reconcile |
| Live-mode attempt | Change Pulse to live during Archive run | Hard refusal and prominent safety event |

## Other ways to test Pulse

Archive should be one layer in a broader test program, not the only test mechanism.

### 1. Native unit and contract tests

Continue fast pytest coverage for:

- order quantity calculations;
- bracket targets;
- partial-leg allocation;
- weighted average entry;
- P&L accounting;
- risk units and thresholds;
- order-status normalization;
- idempotency;
- multi-broker aggregation;
- state serialization and restoration.

Pulse already has useful coverage in files such as:

- `test_broker_manager_order_results.py`;
- `test_broker_execution_preflight.py`;
- `test_live_broker_truth_guards.py`;
- `test_order_mode_routing.py`;
- `test_engine_stress_simulation.py`;
- `test_replay_service_units.py`.

The existing stress simulation is useful because it runs deterministic price tapes through bracket, partial-fill, and rebracket paths. Its fake database and broker results mean it remains an in-process integration test, not external broker truth.

### 2. Golden event-tape tests

Commit small, human-reviewable fixtures with expected results:

```text
backend/tests/fixtures/replay/
  simple_round_trip.csv
  partial_fill.csv
  oco_ambiguous.csv
  gap_stop.csv
  multi_symbol.csv
  expected/*.json
```

A golden result should contain decisions, orders, fills, positions, P&L, and final risk state. Changes require an intentional fixture update, making behavioral drift visible in review.

### 3. Property-based testing

Use Hypothesis to generate prices, fills, quantities, and order transitions while asserting invariants:

- quantity is finite and nonnegative for long-only symbols;
- sell fills never exceed available quantity unless shorting is explicitly enabled;
- the same fill ID cannot affect state twice;
- weighted average entry remains within the range of contributing fill prices;
- cash plus market value and realized/unrealized P&L reconcile within tolerance;
- a canceled or rejected order cannot later mutate a position without a new broker event;
- an OCO group cannot leave two filled exits for the same protected quantity;
- replay never invokes a real broker adapter.

### 4. Model-based order lifecycle tests

Represent each order as a state machine:

```text
created -> accepted -> partially_filled -> filled
                    -> canceled
                    -> rejected
                    -> expired
```

Generate legal and illegal transition sequences and compare Pulse state to a small reference model. This is especially important because live brokers use different status names and can repeat or reorder notifications.

### 5. Full HTTP black-box tests

Launch the real Pulse FastAPI service with:

- an isolated MongoDB database;
- authentication enabled;
- test-only secrets;
- no external broker access;
- Archive or a strict fake broker server.

Drive only public APIs and verify health, settings, replay, bot control, trades, risk center, and reconciliation. This catches startup composition, dependency wiring, auth, persistence, and route behavior that in-process engine tests miss.

### 6. Broker adapter conformance suite

Every adapter should pass the same reusable contract tests:

- authentication success/failure;
- account mapping;
- quote validation;
- position mapping;
- market/limit/stop order request mapping;
- client order ID preservation;
- accepted/pending/partial/filled/rejected status mapping;
- cancel behavior;
- timeout behavior;
- malformed response handling;
- no secret leakage in exceptions or audit records.

Archive can be the deterministic reference adapter for many of these tests.

### 7. Fault injection and chaos tests

Inject:

- connection reset after order submission;
- duplicate HTTP response;
- delayed fill event;
- fill event before order-status poll;
- stale quote;
- invalid or non-finite price;
- partial fill followed by cancel;
- empty broker position response;
- one failed broker in a multi-broker order;
- Mongo write failure;
- process restart between acceptance and fill.

The required outcome is not always continued trading. A safe, explicit halt with reconcilable evidence is often the correct result.

### 8. Snapshot and restart recovery

Persist a known state, restart Pulse, and verify:

- open positions;
- trailing highs;
- partial leg completion;
- pending orders and idempotency keys;
- broker snapshots;
- risk exposures and rolling order-rate state;
- replay cursor and virtual timestamp;
- daily P&L.

Then reconnect to Archive and prove no order or fill is duplicated.

### 9. Walk-forward and differential research

Use separate periods for:

- parameter selection;
- validation;
- final untouched evaluation.

Run the same recorded sequence through:

1. Pulse native paper behavior;
2. Pulse with Archive broker fills;
3. a small independent reference model.

Differences should be reported at the first divergent event rather than hidden in final P&L. Profitability research must include zero-order configurations, open positions, slippage, commission, drawdown, and dataset provenance.

### 10. Paper-broker burn-in

Archive's `paper_burnin.py` already contains guarded Alpaca paper drills and a controlled Pulse broker disconnect/reconnect drill. These are useful after deterministic testing, with explicit operator authorization.

A paper burn-in should cover several market sessions and collect:

- order acceptance, fill, cancellation, and rejection;
- reconciliation latency;
- stale/open order cleanup;
- restart recovery;
- broker status transitions;
- residual position/order checks.

Paper behavior is still not proof of live fill quality, but it validates network, credentials, account mapping, and real broker response handling.

### 11. Shadow mode

Run Pulse against live market data while disabling broker writes. Record the orders Pulse would have sent, then compare them with later market movement and with an Archive replay of the same session. Shadow mode is useful for operational observation without placing orders, but it must be labeled as hypothetical execution.

### 12. Frontend and operator-flow tests

Use Playwright for:

- mode labels and live/paper/archive truth;
- replay controls;
- broker connection fields;
- risk kill-switch requests;
- confirmation dialogs;
- disabled live actions during Archive replay;
- reconnect and error toasts;
- position/trade updates after partial fills.

### 13. Load and soak tests

Run many symbols and long datasets to measure:

- event backlog;
- evaluation latency;
- Mongo growth;
- WebSocket pressure;
- rate-limit correctness;
- memory growth in pending-order and idempotency caches;
- reconciliation duration.

### 14. Security tests

Verify:

- Archive bot tokens are masked and never logged;
- broker credentials never appear in replay datasets or evidence bundles;
- participant tokens cannot read another account's broker events;
- replay cannot enable live mode;
- SSRF protections restrict configurable Archive URLs to approved local/test targets when appropriate;
- malformed event payloads fail closed.

## Recommended implementation phases

### Phase 0 — Documentation and ownership

This assessment. Agree that the General API, not the legacy facade, is the integration target. Define ownership of the adapter, lifecycle worker, and coordinator.

### Phase 1 — Adapter contract without full replay

- Add `ArchiveBrokerAdapter` behind a dedicated feature flag.
- Use mocked Archive HTTP responses.
- Pass broker adapter conformance tests.
- Prove live mode refuses the adapter.
- Do not claim end-to-end replay yet.

### Phase 2 — Deterministic one-symbol end-to-end test

- Add the virtual clock.
- Add released-bar price and history source.
- Add pending-order/fill event synchronization.
- Run a manually stepped buy and sell through real Pulse HTTP, MongoDB, broker manager, and Archive.
- Reconcile final reports.

### Phase 3 — Execution safety scenarios

- partial fills;
- duplicate/retry;
- stop and OCO ambiguity;
- reduce-only rejection;
- disconnect/reconnect;
- empty position clearing;
- Pulse restart;
- multi-broker allocation.

### Phase 4 — Strategy and portfolio replay

- multiple symbols on one virtual clock;
- warm-up history;
- custom signal strategies;
- partial scale-in/scale-out;
- risk and kill-switch scenarios;
- walk-forward reports and differential comparisons.

### Phase 5 — Persistence and long-running certification

- persist Archive General API runs or implement snapshot export/import;
- restart both services mid-run;
- nightly replay suites;
- multi-session paper-broker burn-in;
- signed evidence bundles for release candidates.

## CI layout

Recommended tiers:

| Tier | Trigger | Contents |
| --- | --- | --- |
| Fast | Every pull request | unit, property smoke, adapter contract, static safety checks |
| Integration | Every pull request or protected branches | Pulse engine with fake Mongo/services, golden tapes, restart snapshots |
| Archive E2E | Protected branches/nightly | real Pulse + Mongo + Archive, manually stepped scenarios |
| Research | Scheduled/manual | multi-day and walk-forward studies, differential reports |
| Broker paper | Manual and scheduled during market sessions | explicitly authorized paper account drills only |
| Release readiness | Release candidate | all deterministic gates plus reviewed paper evidence and operator checklist |

A profitability result must never replace execution-safety gates. A run can be profitable while double-counting fills, using future data, overselling, or silently falling back to live prices.

## Acceptance criteria for claiming "Archive tested Pulse"

The claim should only be made when all of the following are true:

- the running Pulse service, not a reimplemented strategy, generated every tested order;
- Pulse consumed only released Archive market data;
- moving averages and OHLCV history were bounded by virtual time;
- Pulse's normal risk and broker-manager path handled the order;
- Archive generated no orders;
- every fill had an originating Pulse order;
- pending and partial fills were applied once;
- Pulse and Archive final positions, quantities, average entries, and P&L reconciled;
- the run used no real broker adapter or live-price fallback;
- commits, configuration, dataset checksum, and event logs were preserved;
- the scenario assertions passed automatically;
- any OHLC intrabar ambiguity was disclosed.

Until then, wording should be specific, such as:

- "Pulse native strategy logic was replayed over recorded candle closes";
- "Archive's Pulse handoff simulator passed its contract checks";
- "Pulse submitted an order to Archive, but fill synchronization was not exercised";
- "A full Pulse-to-Archive broker replay passed and reconciled."

## Final recommendation

Proceed with Archive integration, but build it as an **external simulation broker and virtual market**, not as a replacement Pulse implementation.

The highest-value first milestone is a single deterministic test in which:

1. Archive releases a recorded SPY bar.
2. The real Pulse service evaluates its configured ticker.
3. Pulse submits one order through `BrokerConnectionManager` to `ArchiveBrokerAdapter`.
4. Archive releases the next bar and produces a fill.
5. Pulse consumes that fill, records one trade, and reconciles one position.
6. A later bar causes Pulse to submit an exit.
7. Both systems finish flat with matching realized P&L and an evidence bundle.

That milestone will expose the most important architectural gaps—virtual time, historical-data isolation, pending fills, and broker-truth reconciliation—while staying small enough to review and trust.
