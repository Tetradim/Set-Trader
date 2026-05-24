# Sentinel Pulse Release Code Cleanup Audit

Date: 2026-05-23
Branch reviewed: `Beta-Maximum`

This audit is a hard cleanup pass for beta release readiness. It focuses on dead code, stale transition code, overly large modules, security-sensitive leftovers, and files whose interface is broader than their implementation earns.

## Executive Findings

1. `backend/server.py` still defines `/api/logs/stream`, `/api/logs/recent`, and `/api/logs/client-error` directly on `app` after the authenticated `/api` router is mounted. These endpoints are outside the router dependency model and should move into `backend/routes/logs.py` with explicit auth.
2. Password hashing exists in two places and uses raw SHA-256 in both `backend/auth.py` and `backend/routes/auth.py`. This should move to one password module using `bcrypt` or `passlib`.
3. `backend/trading_engine.py` is the largest runtime file at 1,584 lines. It mixes market-hours policy, risk checks, order idempotency, execution, trailing stops, Edge updates, Telegram notifications, and persistence side effects.
4. `frontend/src/components/ConfigModal.tsx` and `frontend/src/components/tabs/SettingsTab.tsx` are both about 800 lines and should be split into focused panels/hooks.
5. Many `frontend/src/components/ui/*` primitives are installed but unused. They add audit noise and bundle/test maintenance cost.
6. `backend/broker_manager.py` still contains legacy XOR credential fallback. If beta testers are starting fresh, this should become an explicit one-time migration tool, then be removed from normal runtime.
7. Frontend debug `console.log` calls remain in `useStore.ts`, `useWebSocket.ts`, `ForeignTab.tsx`, and `SettingsTab.tsx`. These should route through the authenticated client logger or be gated behind a debug flag.
8. Several files are "future system" scaffolding rather than complete release behavior: `backend/config.py` vault support, `backend/win_launcher.py` tray/hotkey stubs, and in-memory API keys in `backend/auth.py`.

## Release Fix Order

1. Move and authenticate all log endpoints.
2. Consolidate password hashing and remove raw SHA-256 for new credentials.
3. Remove or gate frontend console logging.
4. Remove unused UI primitives and unused frontend files.
5. Split `TradingEngine` into smaller modules with tests around existing behavior before moving code.
6. Split `SettingsTab` and `ConfigModal`.
7. Convert legacy credential fallback into a migration command or remove if no beta installs need it.
8. Expand Foreign markets from backend source of truth, not hardcoded frontend lists.
9. Normalize launcher/build scripts to one supported Windows launcher path.

## Backend Core Files

| File | Current role | Cleanup note | Priority |
| --- | --- | --- | --- |
| `backend/server.py` | FastAPI app bootstrap, middleware, router mounting, settings endpoints, log endpoints | Too much behavior in one file. Move log endpoints to `routes/logs.py`, settings endpoints to `routes/settings.py`, and keep app assembly only. Direct app log endpoints need auth. | High |
| `backend/trading_engine.py` | Main trading loop and execution state | Split into market-hours policy, order lifecycle, position manager, trailing/rebracket module, and notification adapter. Preserve behavior with regression tests first. | High |
| `backend/broker_manager.py` | Broker credential storage, live connection, failover, idempotency | Remove normal-runtime legacy XOR fallback after migration plan. Persist API/broker failure state more explicitly. | High |
| `backend/auth.py` | JWT, RBAC, process-local sessions/API keys | Remove duplicate raw password helpers if routes own DB auth. Persist API keys or do not expose them as durable beta feature. | High |
| `backend/routes/auth.py` | Login/bootstrap/user/API-key routes | Replace SHA-256 password hashing with bcrypt/passlib. Keep all password logic in one auth module. | High |
| `backend/deps.py` | Lazy global dependency registry | Acceptable transitional module, but global mutable state makes tests harder. Long-term: use FastAPI app state/dependency factories. | Medium |
| `backend/config.py` | Environment/vault config scaffold | Vault path is not implemented and production defaults mention internal hosts. Either finish it or remove from beta runtime docs to avoid false confidence. | Medium |
| `backend/runtime_secrets.py` | Desktop-persistent generated secrets | Keep. Confirm file permissions and log paths on Windows. | Medium |
| `backend/logging_config.py` | Structured logging setup | Keep, but route frontend logs through one authenticated endpoint and make log rotation limits explicit. | Medium |
| `backend/telemetry.py` | OpenTelemetry setup | Keep if build includes OTEL dependencies; otherwise make graceful no-op path obvious. | Low |
| `backend/audit_service.py` | Audit event persistence/querying | Keep. Review retention and export size limits before public beta. | Medium |
| `backend/price_service.py` | Price fetching, caching, market data | Medium refactor candidate. Needs clearer split between provider adapter, cache, and strategy market-data shaping. | Medium |
| `backend/risk_controls.py` | Risk/kill-switch model | Keep. Add route-level tests for all write operations. | Medium |
| `backend/resilience.py` | Retry/circuit/rate-limit primitives | Keep. Deprecated `cooldown_ms` compatibility should be removed after callers are updated. | Medium |
| `backend/markets.py` | Market registry and normalization | Needs expansion and should be frontend source of truth. | High |
| `backend/default_tickers.py` | Initial ticker seeding/backfill | Keep but review "legacy seed set" behavior after beta starts, because it can surprise real users. | Medium |
| `backend/schemas.py` | Pydantic/data models | Keep. Consider separating API request models from storage/trade record models. | Low |
| `backend/strategies.py` | Strategy support | Check overlap with `backend/strategies/loader.py`; consolidate if both still own discovery. | Medium |
| `backend/email_service.py` | SMTP feedback/error email | Keep if configured; otherwise UI should clearly mark email as unavailable. | Low |
| `backend/notification_service.py` | Notification abstraction | Check overlap with `telegram_service.py`; avoid two alert interfaces. | Medium |
| `backend/telegram_service.py` | Telegram bot integration | Keep. Avoid direct private `_broadcast_alert` calls from other modules. | Medium |
| `backend/slo_alerting.py` | SLO alert evaluation | Keep if visible in UI; otherwise document as ops-only. | Low |
| `backend/ws_manager.py` | WebSocket connection manager | Keep. Add bounded queue/backpressure tests if tester count grows. | Medium |
| `backend/alert_handler.py` | Alertmanager webhook integration | Keep but keep secret mandatory. Good beta hardening already present. | Medium |
| `backend/win_launcher.py` | Python Windows GUI launcher | Contains optional tray/hotkey `pass` stubs. Either implement or remove from beta package. | Medium |
| `backend/mac_launcher.py` | macOS launcher | Probably not useful for current Windows beta unless cross-platform installers are planned. Move to platform docs or remove from Windows package. | Low |
| `backend_test.py` | Legacy broad backend test script | Candidate for deletion after confirming all checks exist under `backend/tests/`. It is outside the normal test layout. | Medium |

## Backend Routes

| File | Current role | Cleanup note | Priority |
| --- | --- | --- | --- |
| `backend/routes/health.py` | Health/preflight checks | Keep unauthenticated health minimal; avoid leaking internal state. | Medium |
| `backend/routes/auth.py` | Auth/user/API-key routes | See auth section: password hashing and persistent API key storage are the main issues. | High |
| `backend/routes/tickers.py` | Ticker CRUD and reorder | Keep. Confirm all writes are authenticated via router dependency. | Medium |
| `backend/routes/trades.py` | Trade history/logs | Keep. Ensure filters and limits cap large responses. | Medium |
| `backend/routes/bot.py` | Start/stop/settings/test alert | Settings should move to its own route module if still in `server.py`. | Medium |
| `backend/routes/ws.py` | WebSocket endpoint | Currently included without auth dependency at router mount. Add token validation to WebSocket handshake. | High |
| `backend/routes/system.py` | Preflight/system/resilience views | Keep. The comment "replaces legacy rate_limiter" signals old naming; clean wording. | Low |
| `backend/routes/markets.py` | Market metadata/quotes/FX | Needs to drive Foreign UI dynamically. | High |
| `backend/routes/strategies.py` | Strategy metadata/config | Keep. Ensure custom strategy loading cannot import arbitrary user files in beta without guardrails. | Medium |
| `backend/routes/edge.py` | Pulse-Edge API | Keep explicit Edge API-key dependency. Rate limiter is in-memory; acceptable for desktop beta but not multi-instance. | Medium |
| `backend/routes/risk.py` | Risk config/kill switch/order checks | Keep. Add audit events for kill-switch changes if missing. | Medium |
| `backend/routes/orders.py` | Order management/execution data | Keep. Confirm broker-access authorization, not only user auth. | Medium |
| `backend/routes/reconciliation.py` | Position/order reconciliation | Keep. Needs strong audit trail for sign-off actions. | Medium |
| `backend/routes/audit.py` | Audit search/export | Keep authenticated. Add export size limits if missing. | Medium |
| `backend/routes/ops.py` | Incidents/ops data | Keep. Determine whether this is real ops data or dashboard scaffolding. | Medium |
| `backend/routes/analytics.py` | Portfolio analytics | Keep. Add defensive defaults for empty portfolios. | Low |
| `backend/routes/slo.py` | SLO dashboard | Keep if used by monitoring tab. | Low |
| `backend/routes/notifications.py` | Notifications API | Check overlap with Telegram/email services. | Medium |
| `backend/routes/portfolio.py` | Portfolio summary | Keep. Confirm calculations are consistent with `TradingEngine` positions. | Medium |

## Backend Shared Modules

| File | Current role | Cleanup note | Priority |
| --- | --- | --- | --- |
| `backend/shared/mongo_client.py` | Edge Mongo adapter | Keep. Recent identity hardening is good. Add integration test when Edge repo is available. | Medium |
| `backend/shared/edge_integration.py` | Pulse-to-Edge update client | Keep. Backoff behavior should be tested with Edge-running and Edge-absent states. | Medium |
| `backend/shared/commands.py` | Command models | Keep if used by Edge/observation path; otherwise document owner. | Low |
| `backend/shared/commands_utils.py` | Command utilities | Large for a utility file. Consider moving command parsing/state transitions into a deeper command module. | Medium |
| `backend/shared/observations.py` | Observation models | Keep. | Low |
| `backend/shared/observation_service.py` | Observation persistence/service | Keep. Silent `pass` blocks should log at debug level. | Medium |
| `backend/shared/chart_pattern_detector.py` | Pattern detection | Looks isolated and only filename mention was low. Verify it is actually imported through strategy code; remove if orphaned. | Medium |
| `backend/shared/__init__.py` | Shared exports | Keep exports small; avoid hiding dependencies. | Low |

## Backend Brokers

| File | Current role | Cleanup note | Priority |
| --- | --- | --- | --- |
| `backend/brokers/base.py` | Broker adapter interface | Keep. Replace abstract `pass` with `raise NotImplementedError` where appropriate. | Low |
| `backend/brokers/registry.py` | Broker metadata and adapter lookup | Keep. This is the source of truth for broker UI fields. | Medium |
| `backend/brokers/alpaca_adapter.py` | Alpaca adapter | Keep if tested with real/sandbox creds. | Medium |
| `backend/brokers/ibkr_adapter.py` | IBKR adapter | Keep; clarify gateway assumptions. | Medium |
| `backend/brokers/robinhood_adapter.py` | Robinhood adapter | Higher operational risk. Confirm compatibility and terms before beta. | Medium |
| `backend/brokers/tda_adapter.py` | TD Ameritrade adapter | Likely stale due Schwab transition. Mark unsupported or remove. | High |
| `backend/brokers/thinkorswim_adapter.py` | Thinkorswim adapter | Verify current API path; likely needs explicit beta unsupported state if not live-tested. | High |
| `backend/brokers/tradestation_adapter.py` | TradeStation adapter | Keep if auth flow is complete. | Medium |
| `backend/brokers/tradier_adapter.py` | Tradier adapter | Keep if live test works. | Medium |
| `backend/brokers/wealthsimple_adapter.py` | Wealthsimple adapter | Keep if API assumptions are valid. | Medium |
| `backend/brokers/webull_adapter.py` | Webull adapter | Keep if dependency is packaged and login path works. | Medium |
| `backend/brokers/__init__.py` | Broker exports | Keep. | Low |

## Backend Strategies

| File | Current role | Cleanup note | Priority |
| --- | --- | --- | --- |
| `backend/strategies/base.py` | Strategy interface | Keep. Make supported markets pull from `markets.py` where possible. | Medium |
| `backend/strategies/loader.py` | Strategy discovery | Keep. Ensure it does not swallow import failures silently during beta. | Medium |
| `backend/strategies/custom/bollinger.py` | Bollinger strategy | Keep if listed in UI and tested. | Low |
| `backend/strategies/custom/macd.py` | MACD strategy | Keep. | Low |
| `backend/strategies/custom/macdv.py` | MACD volume strategy | Keep. File is relatively large; consider sharing MACD primitives. | Medium |
| `backend/strategies/custom/multi_indicator.py` | RSI/MACD combined strategy | Docstring says "demonstrates"; update wording to production language or remove if only example. | Medium |
| `backend/strategies/custom/pattern_scanner.py` | Pattern scanner strategy | Verify dependency on chart pattern detector. | Medium |
| `backend/strategies/custom/rsi.py` | RSI strategy | Keep. | Low |
| `backend/strategies/custom/sma_crossover.py` | SMA crossover strategy | Keep if strategy registry loads it; low mention count means verify. | Medium |
| `backend/strategies/custom/__init__.py` | Custom strategy package marker | Keep. | Low |
| `backend/strategies/presets/__init__.py` | Preset package marker | Keep only if presets are planned; otherwise remove empty package. | Low |

## Frontend Core

| File | Current role | Cleanup note | Priority |
| --- | --- | --- | --- |
| `frontend/src/main.tsx` | React entrypoint | Keep. | Low |
| `frontend/src/App.tsx` | App shell/auth/dashboard | Keep small; verify no tab state remains duplicated. | Medium |
| `frontend/src/index.css` | Global styles | Large. Remove dead legacy classes after UI stabilizes. | Medium |
| `frontend/src/stores/useStore.ts` | Zustand app state | Remove raw `console.log` calls or route through debug logger. Split ticker state/actions from account/UI state if growth continues. | High |
| `frontend/src/hooks/useWebSocket.ts` | WebSocket connection and message reducer | Remove raw `console.log`; add auth token to WebSocket handshake. | High |
| `frontend/src/lib/api.ts` | API fetch wrapper | Keep. Consider central response schema/error typing. | Medium |
| `frontend/src/lib/clientLogger.ts` | Authenticated UI logger | Keep. Typed values are opt-in; for public beta default should remain off. | Medium |
| `frontend/src/lib/wsLogger.ts` | WebSocket logger helper | Low mention count; verify usage or remove. | Medium |
| `frontend/src/lib/dashboard-tabs.ts` | Dashboard tab/group source | Keep. | Low |
| `frontend/src/lib/market-utils.ts` | Market display helpers | Needs to derive from backend market metadata instead of duplicated suffix map. | High |
| `frontend/src/lib/ticker-card-utils.ts` | Ticker-card helper logic | Keep. | Low |
| `frontend/src/lib/hooks.ts` | Shared hooks | Verify usage. Remove if only template leftover. | Low |
| `frontend/src/lib/utils.ts` | Classname utility | Keep if UI primitives remain. | Low |

## Frontend Components

| File | Current role | Cleanup note | Priority |
| --- | --- | --- | --- |
| `frontend/src/components/Dashboard.tsx` | Dashboard layout | Keep. Ensure group/tab state is single source of truth. | Medium |
| `frontend/src/components/DashboardNavigation.tsx` | Group/tab navigation | Keep. Good consolidation target for keyboard/a11y tests. | Medium |
| `frontend/src/components/DashboardTabContent.tsx` | Lazy tab loading | Keep. | Low |
| `frontend/src/components/dashboardConfig.tsx` | Tab labels/icons | Keep; consider merging with `dashboard-tabs.ts` to reduce duplicated tab metadata. | Medium |
| `frontend/src/components/Header.tsx` | Header/status controls | Keep. | Low |
| `frontend/src/components/AuthGate.tsx` | Login/bootstrap UI | Keep. Should handle lockout/rate-limit messages after backend auth hardening. | Medium |
| `frontend/src/components/BetaRegistrationModal.tsx` | Beta registration UI | Low mention count; verify it is reachable. Remove if registration workflow is not part of beta. | Medium |
| `frontend/src/components/FeedbackDialog.tsx` | Feedback capture | Keep if email endpoint is configured; otherwise disable or label unavailable. | Medium |
| `frontend/src/components/ErrorBoundary.tsx` | UI error boundary | Keep. Route errors through `clientLogger`. | Medium |
| `frontend/src/components/TickerCard.tsx` | Main ticker card shell | Recently split; keep moving logic into ticker-card submodules. | Medium |
| `frontend/src/components/ConfigModal.tsx` | Per-ticker config modal | Split into tab panel files and a hook for `handleFieldChange`. | High |
| `frontend/src/components/TradeLogSidebar.tsx` | Trade log drawer/sidebar | Low mention count; verify reachable from dashboard. Remove if replaced by Logs/History tabs. | Medium |
| `frontend/src/components/AddTickerDialog.tsx` | Add ticker flow | Needs dynamic market list from backend. | High |
| `frontend/src/components/TunnelSVG.tsx` | Visual asset/component | Verify usage; remove if no longer visible. | Low |

## Frontend Ticker-Card Submodules

| File | Current role | Cleanup note | Priority |
| --- | --- | --- | --- |
| `frontend/src/components/ticker-card/TickerCardHeader.tsx` | Header controls | Keep. | Low |
| `frontend/src/components/ticker-card/TickerCardFooter.tsx` | Footer/status controls | Keep. | Low |
| `frontend/src/components/ticker-card/TickerSparkline.tsx` | Live mini chart | Keep; user explicitly wants this live trendline. | Low |
| `frontend/src/components/ticker-card/TickerResizeHandles.tsx` | Resize handles | Keep. Add pointer/e2e tests if resize issues continue. | Medium |
| `frontend/src/components/ticker-card/TickerQuickBrackets.tsx` | Quick bracket controls | Keep. | Low |
| `frontend/src/components/ticker-card/ConfigWidgets.tsx` | Reusable config controls | Keep but split if shared with Settings grows. | Medium |
| `frontend/src/components/ticker-card/StrategyConfigSection.tsx` | Strategy config UI | Keep. Remove raw console error or route to logger. | Medium |

## Frontend Tabs

| File | Current role | Cleanup note | Priority |
| --- | --- | --- | --- |
| `frontend/src/components/tabs/WatchlistTab.tsx` | Primary trading board | Keep. Further split add-card/footer layout from ticker grid if it grows. | Medium |
| `frontend/src/components/tabs/PortfolioTab.tsx` | Portfolio overview | Keep. Verify calculations against backend portfolio route. | Medium |
| `frontend/src/components/tabs/PositionsTab.tsx` | Open positions/actions | Keep. Review manual price input safety. | Medium |
| `frontend/src/components/tabs/OrdersExecutionTab.tsx` | Orders view | Keep. | Low |
| `frontend/src/components/tabs/HistoryTab.tsx` | Trade history | Keep. | Low |
| `frontend/src/components/tabs/PreflightTab.tsx` | Release/system checks | Keep; useful for beta testers. | Low |
| `frontend/src/components/tabs/RiskCenterTab.tsx` | Risk controls | Keep. Route errors through logger. | Medium |
| `frontend/src/components/tabs/ReconciliationTab.tsx` | Reconciliation UI | Keep. | Low |
| `frontend/src/components/tabs/ComplianceAuditTab.tsx` | Audit search/export | Keep. | Low |
| `frontend/src/components/tabs/LogsTab.tsx` | App/trade logs | Keep. Depends on authenticated log endpoints. | High |
| `frontend/src/components/tabs/BrokersTab.tsx` | Broker setup/test UI | Large. Split credentials form, test result, and broker list. | Medium |
| `frontend/src/components/tabs/ForeignTab.tsx` | Foreign market panel | Hardcoded market list. Make dynamic from `/api/markets`; remove debug logs. | High |
| `frontend/src/components/tabs/TracesTab.tsx` | Trace viewer | Keep if backend traces route exists and is enabled. | Low |
| `frontend/src/components/tabs/IncidentsOpsTab.tsx` | Ops/incidents view | Keep if data is real. If scaffold only, hide from beta. | Medium |
| `frontend/src/components/tabs/PortfolioAnalyticsTab.tsx` | Analytics dashboard | Keep. | Low |
| `frontend/src/components/tabs/AdminIAMTab.tsx` | Admin/user controls | Keep, but should not be visible to non-admin users. | High |
| `frontend/src/components/tabs/SLODashboardTab.tsx` | SLO dashboard | Keep if metrics are live. | Low |
| `frontend/src/components/tabs/SettingsTab.tsx` | Global settings | Split into account, risk, Edge, trading mode, Telegram, and broker allocation panels. Remove raw debug logs. | High |

## Frontend UI Primitive Files

Only these primitives appear used by current source: `badge.tsx`, `button.tsx`, `card.tsx`, `checkbox.tsx`, `dialog.jsx`, `input.jsx`, and `switch.jsx`.

Unused cleanup candidates: `accordion.tsx`, `alert.tsx`, `alert-dialog.tsx`, `aspect-ratio.tsx`, `avatar.tsx`, `breadcrumb.tsx`, `calendar.tsx`, `carousel.tsx`, `collapsible.tsx`, `command.tsx`, `context-menu.jsx`, `drawer.jsx`, `dropdown-menu.jsx`, `form.jsx`, `hover-card.jsx`, `input-otp.jsx`, `label.jsx`, `menubar.jsx`, `navigation-menu.jsx`, `pagination.jsx`, `popover.jsx`, `progress.jsx`, `radio-group.jsx`, `resizable.jsx`, `scroll-area.jsx`, `select.jsx`, `separator.jsx`, `sheet.jsx`, `skeleton.jsx`, `slider.jsx`, `sonner.jsx`, `table.jsx`, `tabs.jsx`, `textarea.jsx`, `toast.jsx`, `toaster.jsx`, `toggle.jsx`, `toggle-group.jsx`, `tooltip.jsx`.

Before deleting, run `npm.cmd run build` because dynamic/import alias usage can evade simple text search.

## Launch, Installer, and Ops Files

| File | Cleanup note | Priority |
| --- | --- | --- |
| `Launch-Sentinel-Pulse.ps1` | Current primary launcher. Keep as only supported launch path if batch wrapper calls it. | High |
| `Launch-Sentinel-Pulse.bat` | Wrapper. Keep only if needed for users who double-click. | Medium |
| `Setup-And-Launch.bat` | Confirm it calls the primary launcher and does not duplicate browser-open behavior. | Medium |
| `Start-MongoDB.ps1` | Keep if used by installer/launcher; otherwise fold into primary launcher. | Medium |
| `Start-MongoDB.bat` | Wrapper candidate; remove if not used. | Low |
| `build-installer.ps1` | Keep. Add local build workflow docs so testers do not redownload installers. | Medium |
| `build-windows.ps1` | Keep if it produces packaged app. Remove overlap with installer script where possible. | Medium |
| `setup.iss` | Inno Setup definition. Keep. Ensure uninstall cleanup list includes desktop logs/installers. | High |
| `.github/workflows/*` | Keep concurrency/no-op test fixes. Add timeout-minutes to any long job. | Medium |
| `docker-compose.yml` / `docker-compose.prod.yml` | Keep if still supported; otherwise beta docs should not promise Docker path. | Low |
| `backend/Dockerfile*`, `frontend/Dockerfile*`, `frontend/nginx.conf` | Keep if Docker beta path is supported. | Low |
| `grafana/dashboards/sentinel-pulse.json` | Keep as optional ops artifact. | Low |
| `backend/rules/*.yml`, `backend/alertmanager.yml` | Keep if Alertmanager integration is supported; otherwise mark advanced/optional. | Low |

## Tests and Static Checks

The `backend/tests/` suite is broad and valuable, especially static release-hygiene tests. Cleanup should keep these tests and add new ones before removing legacy behavior.

High-value additions:

1. Static test that every `/api/logs/*` endpoint requires auth.
2. Static test that frontend code has no unguarded `console.log`.
3. Unit test for bcrypt/password migration path.
4. UI/static test that `ForeignTab` derives market cards from `/api/markets`.
5. Static test that unsupported broker adapters are marked unavailable, not silently partial.
6. Launcher static test confirming only one browser open path is active.

## Dead-Code Candidates To Verify First

These are not deletion instructions yet. They require one build/test pass after removal.

1. Most `frontend/src/components/ui/*` primitives listed above.
2. `frontend/src/components/BetaRegistrationModal.tsx` if no beta registration workflow is reachable.
3. `frontend/src/components/TradeLogSidebar.tsx` if Logs/History tabs replaced it.
4. `frontend/src/lib/wsLogger.ts` if not imported by current WebSocket path.
5. `backend_test.py` if all coverage exists under `backend/tests/`.
6. `backend/mac_launcher.py` for Windows-only beta packaging.
7. `backend/win_launcher.py` tray/hotkey stubs if GUI launcher is not shipped.
8. Empty `backend/strategies/presets/` package if no presets are planned.
9. TD Ameritrade/Thinkorswim adapters if current API support is not real.
10. `backend/config.py` vault scaffold if the beta installer is local-desktop only.

## Recommended Next Cleanup Batch

Batch 1 should be small and release-critical:

1. Create `backend/routes/logs.py`.
2. Move `/api/logs/stream`, `/api/logs/recent`, `/api/logs/client-error`, and `/api/logs/client-events` into it.
3. Mount logs router with `Depends(get_current_user)`, except no public log routes.
4. Remove unguarded frontend `console.log` from `useStore.ts`, `useWebSocket.ts`, `ForeignTab.tsx`, and `SettingsTab.tsx`.
5. Add static tests for both rules.

## Completed Refactor Batch

The first cleanup batch is implemented:

1. `TradingEngine` is split into behavior mixins under `backend/trading/` for idempotency, engine state, order lifecycle, ticker evaluation, strategy signals, bracket management, and trade accounting.
2. `backend/routes/edge.py`, `backend/resilience.py`, and `backend/server.py` have their contract/logging/primitive behavior extracted to smaller modules.
3. `ConfigModal`, `SettingsTab`, and `BrokersTab` are split into focused components. Current backend/frontend source scan shows no `.py`, `.ts`, or `.tsx` source file over 500 lines in `backend/` or `frontend/src/`.
4. Foreign markets are driven by backend market metadata instead of a hardcoded frontend list, with expanded exchange coverage and ticker examples for 24/7 global session handoff.
5. Frontend raw console logging in touched UI paths now routes through the authenticated UI logger.
6. Log stream/recent/client event routes are mounted behind the authenticated API dependency.
7. New password hashes use bcrypt, with login-time upgrade support for legacy hashes.

This batch reduces public-beta risk without changing trading behavior.
