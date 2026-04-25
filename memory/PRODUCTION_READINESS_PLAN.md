# Sentinel Pulse Production Readiness Plan (Firm-Grade)

## 1) Current feature inventory (what exists today)

### Core trading + risk
- Bracket engine (buy/sell/stop/trailing), auto-rebracket, opening-bell modes, partial fills, and strategy plugins.
- Multi-broker execution + per-broker allocations.
- Circuit-breaker + rate-limit controls per broker.
- International market support and FX conversion modes.

### Existing dashboard tabs and what they do
- **Watchlist**: live/inactive ticker cards, drag reorder, mode toggles, quick broker assignment.
- **Positions**: open positions summary + manual sell and pending sell cancellation.
- **History**: grouped trade history with detailed execution metadata.
- **Logs**: filtered audit log viewer and local log file explorer.
- **Brokers**: broker catalog, connection testing, risk badges, basic resilience status/config.
- **Foreign**: market-hours display for non-US exchanges + currency display control.
- **Traces**: in-memory OpenTelemetry span viewer.
- **Settings**: trading mode, Telegram, account balance, input step sizes, broker allocations.

---

## 2) What is holding this back from firm-grade production use

## A. Security and governance gaps (highest priority)
1. **No authentication/authorization boundary on API/WS for operator actions**.
2. **No RBAC** (trader, risk officer, admin roles).
3. **No SSO/OIDC integration** (Okta/Azure AD/etc.).
4. **No signed audit trail / tamper evidence** for compliance-grade forensics.
5. **No mandatory approval workflow for high-risk actions** (live mode, config changes, strategy deploy).
6. **Secrets posture needs hardening** (vault/KMS-backed secrets, rotation, scoped credentials).

## B. Reliability + operational risk
1. **Single-process runtime pattern** (engine, API, websocket in one app) increases blast radius.
2. **No explicit HA / failover topology** (active/passive, leader election, warm standby).
3. **No durable job/event queue** for execution and reconciliation workflows.
4. **No deterministic state machine/replay log** for post-mortem and recovery.
5. **No explicit DR plan** (RPO/RTO targets, restore drills, regional recovery).

## C. Trading controls expected by firms
1. **No pre-trade risk gateway** (max notional/order, fat-finger checks, restricted symbols).
2. **No real-time exposure limits at portfolio/account/sector/asset-class level**.
3. **No kill-switch hierarchy** (desk/account/strategy/global).
4. **No post-trade reconciliation dashboard** (broker confirms/fills vs internal ledger).
5. **No model governance lifecycle** for strategies (versioning, approval, rollback, drift monitoring).

## D. Monitoring + SRE maturity gaps
1. Metrics/traces are present but **no formal SLO/error-budget framework**.
2. **No production alert routing/on-call policy definition** (PagerDuty/Opsgenie runbooks).
3. **No synthetic checks/canary environment**.
4. **No full runbook catalog** (degraded broker, stale prices, delayed fills, market halt).

## E. UX / dashboard productization gaps
1. Dashboard is feature-rich but **missing firm-ops tabs for governance and oversight**.
2. **Charts are tactical (small sparkline context) vs analytical (execution quality / attribution)**.
3. **No workspace personalization** (saved layouts, linked filters, role-specific views).
4. **No formal design system + accessibility QA gate** for polished enterprise rollout.

---

## 3) Missing tabs to add (and why)

1. **Risk Center**
   - Live exposure ladder (symbol/sector/broker).
   - Limits panel (hard/soft), breach timeline, acknowledgements.
   - Kill switches and approvals.

2. **Orders & Execution**
   - Parent/child order state machine view.
   - Fill timeline, reject reasons, slippage vs benchmark.
   - Broker routing diagnostics.

3. **Reconciliation**
   - Internal ledger vs broker statements/confirmations.
   - Break detection and resolution workflow.
   - End-of-day sign-off.

4. **Compliance & Audit**
   - Immutable event log explorer.
   - Operator action attestations.
   - Export bundles for review/audits.

5. **Strategy Lab / Model Ops**
   - Strategy version registry.
   - Backtest/forward-test comparison.
   - Approval gate and staged rollout controls.

6. **Incidents / Ops Console**
   - Service health topology.
   - Alert feed with severity + owner.
   - One-click runbook links + mitigation actions.

7. **Portfolio Analytics**
   - PnL attribution (strategy, sector, market, broker).
   - Drawdown, Sharpe-like metrics, turnover, hit-rate regime analysis.

8. **Admin / IAM**
   - Users, roles, API keys, session policy, IP allowlist.

---

## 4) Dashboard and chart refactor direction

## Information architecture
- Split UI into two modes:
  1) **Trader cockpit** (fast execution + watchlist + positions)
  2) **Supervisor console** (risk/compliance/ops/reconciliation)
- Persistent left navigation with tab groups: Trading, Risk, Analytics, Operations, Admin.

## Charting improvements (from mini-chart to decision-grade)
1. **Timeframe controls**: 1m/5m/15m/1h/1d plus session boundaries.
2. **Overlays**: entries/exits/stops/rebrackets, broker fill markers, strategy signals.
3. **Execution-quality panel**: slippage, expected vs actual fill, latency histogram.
4. **Comparative benchmarks**: symbol vs index / sector ETF.
5. **Drawdown curve + underwater chart** for strategy and portfolio.
6. **Cross-filter interaction**: clicking a trade filters logs, traces, broker events.
7. **Chart virtualization/performance**: windowed rendering for large datasets.

## UX polish checklist
- Unified typography scale and spacing tokens.
- Role-based dashboard presets.
- Keyboard command palette (jump to ticker, flatten, pause, kill).
- Accessibility pass: color contrast, focus order, aria labels, reduced-motion support.
- Empty/loading/error states standardized with actionable guidance.

---

## 5) Suggested phased roadmap

## Phase 0 (2–4 weeks): Production baseline
- Add auth (OIDC), RBAC, secure sessions, API key scopes.
- Enforce environment separation (dev/stage/prod) and secret vault integration.
- Add formal release/versioning, config migration discipline, and rollback plan.

## Phase 1 (4–8 weeks): Risk + controls
- Implement pre-trade risk gateway and hierarchical kill switches.
- Build **Risk Center** and **Orders & Execution** tabs.
- Add reconciliation service prototype and EOD report.

## Phase 2 (4–8 weeks): Reliability + operations
- Decompose runtime into independent services (API, engine, market-data worker, execution worker).
- Introduce durable event bus/queue and idempotent processing.
- Add SLOs, on-call alerting, and incident runbooks.

## Phase 3 (4–8 weeks): Compliance + analytics polish
- Immutable audit chain + approvals and attestation flows.
- Launch **Compliance**, **Incidents**, **Portfolio Analytics**, and **Admin** tabs.
- Upgrade charting/attribution stack and role-based workspaces.

## Phase 4 (ongoing): Institutional hardening
- Pen tests, chaos drills, DR rehearsals, model risk governance cadence.
- Execution venue analysis and smart-routing improvements.

---

## 6) “Done” definition for firm-ready milestone
A firm would typically require all of the following to be true:
- Security controls: OIDC + RBAC + secrets governance + audit immutability.
- Risk controls: pre-trade/post-trade controls + kill switches + reconciled books.
- Reliability: HA architecture, tested backup/restore, documented incident response.
- Compliance: complete traceability of who changed what, when, and why.
- Product quality: role-specific workflows, robust charts/analytics, consistent UX.

