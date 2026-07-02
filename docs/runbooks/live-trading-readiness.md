# Live Trading Readiness Runbook

This runbook is the operator checklist for moving Sentinel Pulse from paper testing toward real-money broker routing. Do not place live orders during readiness checks. A live cutover is allowed only after the preflight, broker, risk, audit, and rollback checks below are complete.

Sentinel Pulse is the only Sentinel component that may talk to broker APIs. Sentinel Edge, Sentinel Core, and Sentinel Archive must remain paper/simulation inputs unless Pulse is explicitly confirmed for live broker routing.

## Default Stance

- Keep `dry-run` or paper mode active until the final cutover step.
- Keep `Simulate 24/7` enabled for replay, backtesting, and readiness drills.
- Do not store broker secrets in screenshots, tickets, logs, browser console output, or shared chat.
- Do not place live orders to prove connectivity. Use broker credential tests, paper accounts, account read endpoints, and preflight checks.
- Treat any unknown state as paper-only until it is reconciled against Pulse state and the broker portal.

## Required Preflight

1. Start Pulse with the intended deployment configuration and verify the dashboard loads.
2. Open the Preflight tab or call `GET /api/preflight`.
3. Confirm these preflight items are pass or explicitly accepted for paper-only testing:
   - MongoDB persistence is reachable.
   - Authentication is enabled for operator routes.
   - `ALERT_WEBHOOK_SECRET` or the configured alert path is present when external alerts are expected.
   - `SENTINEL_PULSE_LIVE_TRADING_OPERATOR_SECRET` is configured before any live cutover.
   - Account balance and global daily drawdown are configured.
   - Broker configuration is present before any live cutover.
4. Review `GET /api/audit-logs?event_type=SETTING_CHANGED&limit=20` for recent settings changes.
5. Verify that no live-mode rejection or confirmation audit row contains the phrase `ENABLE LIVE TRADING`; audit entries should record mode labels and requested fields, not the confirmation text.

## Broker And Account Checks

1. Use only the broker account intended for this cutover.
2. Validate API credentials with the broker test endpoint or broker UI. Do not place live orders for credential validation.
3. Confirm account permissions in the broker portal:
   - Trading enabled only for intended asset classes.
   - Buying power and cash match the expected account.
   - Margin, options, or short permissions are disabled unless deliberately required.
4. Confirm every ticker has the intended `broker_ids` and `broker_allocations`.
5. Confirm unsupported broker adapters are unavailable in `/api/brokers`; unsupported adapters must not be credential-tested, connected, or selected for live order routing.
6. Confirm high-risk unofficial broker adapters are disabled unless specifically approved; approval requires setting `SENTINEL_PULSE_ENABLE_EXPERIMENTAL_BROKERS=true` before startup.
7. Verify broker reconciliation:
   - Pulse positions match broker positions.
   - Pulse open orders match broker open orders.
   - Any broker-side open order not known to Pulse is cancelled or documented before cutover.

## Risk Controls

1. Set account balance to the real cutover allocation, not the total brokerage account if only a sleeve is being traded.
2. Configure global daily drawdown.
3. Review per-ticker `base_power`, broker allocations, stop offsets, trailing settings, and max loss fields.
4. Confirm risk controls and kill switch routes are reachable:
   - Risk Center UI.
   - `GET /api/risk/kill-switches`.
   - `POST /api/risk/kill-switches`.
5. Run a paper-mode strategy pass and verify the trade log records `trading_mode` as `paper`.

## Live Confirmation

Pulse requires both controls when a settings change would transition from paper to live broker routing:

- the exact phrase `ENABLE LIVE TRADING`;
- the configured `SENTINEL_PULSE_LIVE_TRADING_OPERATOR_SECRET` value.

Required live-mode state:

- `Simulate 24/7` is disabled.
- live during market hours is enabled.
- `dry-run` is not active.
- The operator has typed `ENABLE LIVE TRADING` into the confirmation prompt.
- The operator has entered the live trading operator secret configured on the Pulse backend.

If the phrase is missing or wrong, Pulse must reject the change with `live_trading_confirmation_required`, leave mode flags unchanged, and write a failed `SETTING_CHANGED` audit event. If the backend secret is not configured, Pulse must reject the change with `live_trading_operator_secret_unconfigured`. If the supplied secret is missing or wrong, Pulse must reject the change with `live_trading_operator_secret_required`. Audit entries must not contain either the phrase or the secret.

## Cutover Steps

1. Confirm the bot is stopped.
2. Confirm there are no unexpected Pulse positions, pending sells, or broker-side open orders.
3. Confirm alerts are working.
4. Confirm audit logs are readable via `/api/audit-logs`.
5. Disable `Simulate 24/7`.
6. Enable live during market hours.
7. Type `ENABLE LIVE TRADING` and enter the operator secret only after the checks above are complete.
8. Start with the smallest intended allocation and one low-risk broker before expanding.
9. Watch the first evaluation cycle. If any unexpected order intent appears, stop immediately.

## Emergency Stop And Panic Stop

Use this panic stop sequence for any unexpected live behavior:

1. Click Stop All in the Watchlist controls or call `POST /api/bot/stop`.
2. Activate the global kill switch from Risk Center or the risk API.
3. Open the broker portal and cancel all open orders directly.
4. Confirm broker positions and open orders from the broker portal, not only from Pulse.
5. Record the incident in audit/ops notes with timestamp, broker, symbols, and current exposure.
6. Keep live mode disabled until broker reconciliation is complete.

## Rollback

1. Re-enable `Simulate 24/7`.
2. Disable live during market hours.
3. Confirm `GET /api/settings` returns `trading_mode: paper`.
4. Stop the bot and keep the global kill switch active until the issue is understood.
5. Review `/api/audit-logs` for:
   - failed live confirmation attempts,
   - successful live confirmation attempts,
   - bot start/stop events,
   - broker errors,
   - circuit breaker events.
6. Reconcile Pulse trades, Pulse positions, broker positions, and broker open orders.
7. Do not resume live trading until the cause and corrective change are documented.

## Post-Cutover Monitoring

- Watch audit logs, trade logs, broker errors, and circuit breaker state.
- Watch broker portal activity independently of Pulse.
- Confirm fills are terminal/filled before treating internal Pulse positions as real.
- Confirm alerts fire for circuit breakers and critical broker errors.
- Run a reconciliation check after the first live session and before the next market open.
