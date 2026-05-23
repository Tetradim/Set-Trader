# Branch Consolidation Audit

Source repository: `Tetradim/Sentinel-Pulse`
Default source branch reviewed: `main-2`

## Summary

The source repository had ten remote branches. Most were already ancestors of
`main-2` and did not contain code that needed a separate port. Four older fix
branches had unique commits, but their branch snapshots were based on an older
tree, so they were reviewed commit-by-commit instead of merged wholesale.

## Branch Review

| Branch | Status | Action |
| --- | --- | --- |
| `Sentinel-Prod` | Ancestor of `main-2` | No separate import needed. |
| `Split` | Ancestor of `main-2` | No separate import needed. |
| `codex/use-skill-templates-for-claude` | Ancestor of `main-2` | No separate import needed. |
| `rename-to-sentinel-pulse` | Ancestor of `main-2` | No separate import needed. |
| `main` | Merge branch with no effective file delta versus `main-2` | No separate import needed. |
| `fix/issues-1-5` | Unique commit found | Selectively ported useful fixes. |
| `fix/ui-feedback-color-theme` | Unique commit found | Useful live config/color work reviewed; current UI already covered most styling changes. |
| `fix/mongodb-check-system` | Unique commit found | Current launcher already includes broader MongoDB detection, including 8.x/7.x paths and port 27017 checks. |
| `fix/add-brokers-tab-to-config-modal` | Unique commit found | Selectively ported broker selector into ticker config modal. |

## Ported Items

- WebSocket ticker add now reports duplicate symbols and insert failures with
  `TICKER_ERROR` instead of silently swallowing errors.
- The frontend WebSocket hook dispatches `ticker-error`, and the Add Ticker
  dialog reopens with the backend error.
- `ConfigModal` now receives a symbol and reads the live ticker from the store,
  so modal values update as ticker state changes.
- The ticker config modal now includes a `Brokers` tab with a broker selector.
- Settings account balance load/save no longer overwrites a missing/null backend
  value with `0` before the user edits it.

## Not Ported

- The old branch removal of default ticker seeding was not imported. The current
  code centralizes default ticker seeding in `backend/default_tickers.py` and
  only seeds fresh or legacy-default watchlists.
- Old Vite proxy and hard-coded relative API changes were not imported. The
  current frontend keeps `VITE_BACKEND_URL` support and authenticated REST/WS
  token handling.
- Older theme contrast tweaks were not imported wholesale because the current UI
  has since moved to a broader dashboard design pass.

## Remote Branch Cleanup Guidance

After the consolidated code is pushed to the target main branch and verified in
GitHub Actions, these source branches can be considered cleanup candidates:

- `Sentinel-Prod`
- `Split`
- `codex/use-skill-templates-for-claude`
- `fix/add-brokers-tab-to-config-modal`
- `fix/issues-1-5`
- `fix/mongodb-check-system`
- `fix/ui-feedback-color-theme`
- `main`
- `rename-to-sentinel-pulse`

Do not delete remote branches until the consolidated main branch is pushed and
the release package has been verified from that branch.
