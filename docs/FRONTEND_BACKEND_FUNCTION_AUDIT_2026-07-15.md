# Sentinel Pulse Frontend ↔ Backend Function Audit

Date: 2026-07-15  
Branch audited: `codex/live-readiness-ledger`  
Purpose: verify that operator-visible controls and displays use the backend functions that own live trading state.

## Status definitions

- **Connected** — the visible frontend calls the registered backend route and consumes the current response contract.
- **Fixed in this branch** — a broken, misleading, or legacy connection was repaired during this audit.
- **Partial** — some backend state is visible, but an important field or action is still absent.
- **Backend-only by design** — internal execution machinery should run automatically and is not a direct operator button.
- **Legacy / compatibility** — retained for old callers but not the authoritative live source.
- **Not connected** — a backend capability has no usable frontend path.

## High-impact findings fixed

1. **Orders screen always appeared empty with a valid raw-list response.**
   - Backend `GET /api/orders` returned a JSON array.
   - `OrdersExecutionTab.tsx` read `ordersRes.orders`.
   - The screen therefore converted valid orders to `[]`.
   - Fix: the screen now reads `GET /api/orders/live`, which has an explicit object contract.

2. **Orders screen read the wrong database authority.**
   - The old screen used the legacy `orders` collection.
   - Repaired live execution persists broker children in `broker_orders`, strategy parents in `parent_orders`, and completed capital cycles in `strategy_cycles`.
   - Fix: `backend/routes/orders.py` now exposes the authoritative ledgers and the frontend displays them.

3. **Reconciliation records had the same array/envelope mismatch.**
   - Backend `GET /api/reconciliation/records` returns an array.
   - The screen read `recordsRes.records`.
   - Fix: the screen accepts either the raw array or an envelope.

4. **Reconciliation actions existed in the backend but were absent from the screen.**
   - `POST /api/reconciliation/resolve-break/{record_id}` was not exposed.
   - `GET /api/reconciliation/signoffs` was not displayed.
   - Fix: break resolution and sign-off history are now visible.

5. **Live quantities were typed as integers in the legacy order model.**
   - Alpaca may use fractional equity quantities.
   - Fix: the order API and screen use floating-point quantities and display up to eight decimal places.

## Detailed function matrix

| Backend capability / route | Backend implementation | Frontend implementation | Status | Finding / action |
|---|---|---|---|---|
| Health, running, paused, market state | `backend/routes/health.py`, websocket initial state | `Dashboard.tsx`, `Header.tsx`, store/websocket hooks | Connected | Primary runtime state is visible and refreshed through WebSocket plus REST fallbacks. |
| Start, stop, pause and resume engine | health/control routes and dashboard handlers | Header/dashboard controls | Connected | Visible controls call registered routes. Operator response should still be checked after every action. |
| Trading mode | settings/trading mode routes | `components/settings/TradingModeSection.tsx` | Connected | Mode changes are visible. Broker capability restrictions remain backend-enforced. |
| Watchlist/ticker listing | ticker routes | `WatchlistTab.tsx`, ticker cards | Connected | Live ticker cards consume backend state and WebSocket price/profit updates. |
| Add ticker | ticker create route | `AddTickerDialog.tsx` | Connected | User-operable creation path exists. |
| Remove/update/reorder ticker | ticker update/delete/reorder routes | ticker-card actions and dashboard | Connected | Existing hooks call backend mutations. |
| Strategy configuration | ticker strategy/config routes | `ConfigModal.tsx`, `StrategyConfigSection.tsx`, `AdvancedStrategyTab.tsx` | Connected | Main strategy settings are editable. Runtime-only patch parameters controlled by environment variables are not shown. |
| Broker allocation per ticker | ticker/broker allocation routes | `BrokerAllocationsSection.tsx` | Connected | Allocations are editable and visible. Actual broker cash/buying-power capacity remains calculated in backend cycle accounting. |
| Broker configuration and connection tests | broker routes | `BrokersTab.tsx`, `BrokersTestConnectionModal.tsx` | Partial | Configuration is visible, but the UI should clearly distinguish adapters disabled by `live_broker_capability_patch.py`. Backend remains the final authority. |
| Aggregate portfolio state | portfolio routes | `PortfolioTab.tsx`, `PortfolioAnalyticsTab.tsx` | Connected | Portfolio data is visible. Per-broker/account ownership remains less visible than aggregate strategy state. |
| Current positions | positions routes and WebSocket state | `PositionsTab.tsx` | Partial | Aggregate position state is visible. Per-broker holdings, reserved sell quantity, ledger version and quote age should be added after the versioned position snapshot is fully wired. |
| Legacy order list | `GET /api/orders` | No longer the main live screen | Legacy / compatibility | Retained for old callers. It is not the authoritative live execution source. |
| Authoritative broker child orders | `GET /api/orders/live` from `broker_orders` | `OrdersExecutionTab.tsx` | Fixed in this branch | Shows broker, requested/fill/applied/unapplied quantity, status, order IDs, errors, cancellation request and TTL. |
| Strategy parent orders | `GET /api/orders/live` from `parent_orders` | `OrdersExecutionTab.tsx` | Fixed in this branch | Shows target, filled, remaining, policy, child count and parent state. |
| Cycle compounding ledger | `GET /api/orders/live` from `strategy_cycles` | `OrdersExecutionTab.tsx` | Fixed in this branch | Shows gross P&L, fees, net P&L and next-cycle capital. |
| Execution quote evidence | persisted child-order `execution_quotes` | Loaded by Orders API | Partial | Data is returned but the table does not yet offer a detailed bid/ask/spread expansion. |
| Automatic order expiry/cancel request | live execution quality reconciliation | Orders screen TTL/cancel state | Connected as status | Backend acts automatically; UI shows expiry and `cancel_requested_at`. No manual cancel button is exposed. |
| Late/partial fill application | reconciliation and publication patches | Orders screen applied/unapplied quantity | Connected as status | Application state is visible without allowing operators to fake a fill. |
| Statement reconciliation records | `GET /api/reconciliation/records` | `ReconciliationTab.tsx` | Fixed in this branch | Correctly reads raw-list contract. |
| Reconciliation summary | `GET /api/reconciliation/summary` | `ReconciliationTab.tsx` | Connected | Totals, breaks, pending and P&L are shown. |
| Resolve reconciliation break | `POST /api/reconciliation/resolve-break/{record_id}` | Reconciliation Resolve button | Fixed in this branch | User enters a resolution and refreshes the ledger. |
| End-of-day signoff | `POST /api/reconciliation/signoff` | Reconciliation EOD Sign-off button | Connected | Disabled while known breaks exist; backend performs final validation. |
| Signoff history | `GET /api/reconciliation/signoffs` | Reconciliation history panel | Fixed in this branch | Recent signoffs are visible. |
| Live broker-order reconciliation trigger | `BrokerExecutionMixin.reconcile_live_orders` | None | Backend-only by design | Runs from engine lifecycle. A future read-only incident view is more appropriate than a manual fill-application control. |
| Edge structured handoff | `/api/edge/handoff` plus idempotency patch | Test/integration surfaces, not a normal trading button | Backend-only by design | Edge owns command creation. Pulse UI should display resulting broker/parent state rather than resubmit the handoff manually. |
| Edge handoff idempotency claim/replay | `edge_handoff_idempotency_patch.py` | No direct control | Backend-only by design | Direct operator mutation would defeat exactly-once semantics. |
| Preflight readiness | preflight route | `PreflightTab.tsx` | Connected | Broker/account/ticker readiness is visible. The user stated gates are secondary, but the route remains informational. |
| Risk center and limits | risk routes | `RiskCenterTab.tsx` | Connected | Limits and risk state are visible. |
| Orders/execution statistics | legacy order stats route | Replaced by live stats in Orders tab | Legacy / compatibility | New live stats are derived from `broker_orders`; legacy stats remain available for older clients. |
| Logs | logging routes/client error route | `LogsTab.tsx`, client logger | Connected | UI and client failures are reported. |
| Traces and SLO status | telemetry routes | `TracesTab.tsx`, `SLODashboardTab.tsx` | Connected | Operational diagnostics have visible screens. |
| Incidents | incident routes | `IncidentsOpsTab.tsx` | Connected | Incident workflows are visible. |
| Compliance/audit | audit routes | `ComplianceAuditTab.tsx` | Connected | Audit data has a screen. |
| Test/simulation/backtest lab | test/backtest routes | `TestLabTab.tsx` | Connected but secondary | User priority is live execution; these surfaces do not control live broker truth. |
| FX and display currency | FX/settings routes | API helper and portfolio displays | Connected | API helper has timeout fallbacks for display only. |
| Foreign-market coverage | foreign market routes | `ForeignTab.tsx` | Connected | Separate from the repaired US equity live lifecycle. |
| Authentication | auth routes/middleware | `AuthGate.tsx`, API token helper | Connected | Not part of trading functionality review. |
| WebSocket live state | `/api/ws` | `useWebSocket.ts`, Zustand store | Connected | Main dashboard receives initial state and updates. |

## Backend functions intentionally not exposed as buttons

These functions are essential but should remain automatic:

- durable handoff claim/replay;
- broker cumulative fill reconciliation;
- applying only new fill deltas;
- position mutation before publication;
- trade publication retry/error annotation;
- parent-order state refresh;
- fee-aware capital-cycle update;
- broker quote validation and quantity normalization;
- terminal partial-fill reduction;
- broker capability downgrade.

The frontend should display their state and incidents, but it should not allow a user to mark an order filled, rewrite applied quantity, or create a second command ID.

## Remaining UI gaps

1. **Per-broker position ownership** — Positions should show broker/account rows, reserved exit quantity and working sell IDs instead of only aggregate position state.
2. **Versioned snapshots** — `versioned_position_snapshot_patch.py` still needs final runtime import/tests; until then Edge cannot reliably reject every stale Pulse position update.
3. **Manual order cancellation** — automatic expiry/cancel is visible, but there is no deliberate cancel action for a selected child order.
4. **Detailed quote evidence** — Orders receives quote snapshots but does not yet expand bid, ask, spread, source time and age.
5. **Parent completion policy control** — current parent policy is shown read-only as `accept_partial`; there is no per-ticker UI for complete-remaining or flatten-partial policies.
6. **Adapter capability labels** — Brokers UI should visibly label only Alpaca and Tradier as complete repaired live adapters until another adapter passes the full lifecycle.
7. **Live reconciliation incidents** — Orders shows unapplied/reconciliation-required child orders, while the Reconciliation tab remains oriented toward statement records. A combined incident view would reduce operator context switching.

## Files changed by this audit

- `backend/routes/orders.py`
- `frontend/src/components/tabs/OrdersExecutionTab.tsx`
- `frontend/src/components/tabs/ReconciliationTab.tsx`
- `backend/tests/test_frontend_live_ledger_wiring.py`
- `.github/workflows/live-readiness-diagnostics.yml`

## Verification boundary

Static contract tests verify the frontend source and authoritative route implementation stay aligned. A real browser/backend run and live broker trace are still required to prove that actual broker records render with the expected data shapes.
