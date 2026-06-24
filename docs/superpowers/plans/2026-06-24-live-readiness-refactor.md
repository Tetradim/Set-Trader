# Live Readiness Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate the remaining live-money readiness gates without weakening the operator signoff boundary.

**Architecture:** Keep broker execution authority in Sentinel Pulse, signal and automation authority in Sentinel Edge, read-only observability in Tandem Suite, and crypto execution gates in Auto-Crypto. Add small evidence-producing modules instead of expanding large route files further.

**Tech Stack:** Python/FastAPI, MongoDB, Alpaca paper APIs and trade updates, Node/Express Tandem connector, pytest, node:test.

---

## File Structure

- Modify: `C:/Users/Lite OS/Documents/Codex/2026-05-22/based-on-my-analysis-of-the/Sentinel-Pulse-branch-audit/backend/brokers/alpaca_adapter.py`
  - Keep REST order placement and polling behavior.
- Create: `C:/Users/Lite OS/Documents/Codex/2026-05-22/based-on-my-analysis-of-the/Sentinel-Pulse-branch-audit/backend/brokers/alpaca_trade_updates.py`
  - Own Alpaca paper websocket trade-update parsing and reconnect behavior.
- Create: `C:/Users/Lite OS/Documents/Codex/2026-05-22/based-on-my-analysis-of-the/Sentinel-Pulse-branch-audit/backend/readiness/evidence_recorder.py`
  - Persist paper burn-in evidence records in one schema.
- Modify: `C:/Users/Lite OS/Documents/Codex/2026-05-22/based-on-my-analysis-of-the/Sentinel-Pulse-branch-audit/backend/routes/edge.py`
  - Expose read-only evidence summaries through the existing Edge service-auth boundary.
- Modify: `C:/Users/Lite OS/.openclaw/workspace/repos/sentinel-edge/backend/automation.py`
  - Extract live-scope validation from request handling.
- Create: `C:/Users/Lite OS/.openclaw/workspace/repos/sentinel-edge/backend/automation_live_scope.py`
  - Own live automation signoff and ticker-scope decisions.
- Modify: `C:/Users/Lite OS/Documents/Codex/2026-06-12/c-users-lite-os-openclaw-workspace/work/Tandem-Suite/server/index.ts`
  - Add read-only readiness evidence panels from Pulse.
- Modify: `C:/Users/Lite OS/Documents/Codex/2026-06-17/start-by-researching-crypto-trading-bots/work/Auto-Crypto/src/autocrypto/app.py`
  - Move live-readiness and exchange state helpers out of the main app module.
- Create: `C:/Users/Lite OS/Documents/Codex/2026-06-17/start-by-researching-crypto-trading-bots/work/Auto-Crypto/src/autocrypto/live_readiness.py`
  - Own crypto live-readiness gate evaluation.

### Task 1: Pulse Alpaca Trade-Update Stream

**Files:**
- Create: `backend/brokers/alpaca_trade_updates.py`
- Test: `backend/tests/test_alpaca_trade_updates.py`

- [ ] **Step 1: Write the failing parser test**

```python
from brokers.alpaca_trade_updates import normalize_trade_update


def test_normalize_partial_fill_trade_update():
    event = normalize_trade_update({
        "event": "partial_fill",
        "order": {
            "id": "broker-1",
            "client_order_id": "sp_abc",
            "symbol": "SOUN",
            "filled_qty": "4",
            "qty": "5",
            "filled_avg_price": "6.31",
            "status": "partially_filled",
        },
    })

    assert event == {
        "event": "partial_fill",
        "broker_order_id": "broker-1",
        "client_order_id": "sp_abc",
        "symbol": "SOUN",
        "filled_quantity": 4.0,
        "quantity": 5.0,
        "filled_price": 6.31,
        "status": "partially_filled",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend\tests\test_alpaca_trade_updates.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'brokers.alpaca_trade_updates'`.

- [ ] **Step 3: Add the parser**

```python
def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def normalize_trade_update(payload: dict) -> dict:
    order = payload.get("order") or {}
    return {
        "event": str(payload.get("event") or ""),
        "broker_order_id": str(order.get("id") or ""),
        "client_order_id": str(order.get("client_order_id") or ""),
        "symbol": str(order.get("symbol") or "").upper(),
        "filled_quantity": _number(order.get("filled_qty")),
        "quantity": _number(order.get("qty")),
        "filled_price": _number(order.get("filled_avg_price") or order.get("filled_price")),
        "status": str(order.get("status") or ""),
    }
```

- [ ] **Step 4: Run parser tests**

Run: `python -m pytest backend\tests\test_alpaca_trade_updates.py -q`
Expected: PASS.

### Task 2: Paper Burn-In Evidence Recorder

**Files:**
- Create: `backend/readiness/evidence_recorder.py`
- Test: `backend/tests/test_readiness_evidence_recorder.py`
- Modify: `backend/routes/edge.py`

- [ ] **Step 1: Write the failing evidence schema test**

```python
from readiness.evidence_recorder import build_evidence_record


def test_build_evidence_record_requires_gate_and_mode():
    record = build_evidence_record(
        gate="broker_partial_fill",
        mode="paper",
        status="pass",
        evidence={"symbol": "SOUN", "events": 4},
    )

    assert record["gate"] == "broker_partial_fill"
    assert record["mode"] == "paper"
    assert record["status"] == "pass"
    assert record["evidence"]["events"] == 4
    assert record["created_at"].endswith("+00:00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend\tests\test_readiness_evidence_recorder.py -q`
Expected: FAIL with missing module.

- [ ] **Step 3: Add the pure record builder**

```python
from datetime import datetime, timezone


def build_evidence_record(*, gate: str, mode: str, status: str, evidence: dict) -> dict:
    return {
        "gate": gate,
        "mode": mode,
        "status": status,
        "evidence": evidence,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
```

- [ ] **Step 4: Add a read-only route for latest evidence**

Add this route to `backend/routes/edge.py` after the existing reconciliation read-only route:

```python
@router.get("/readiness/evidence", dependencies=[Depends(validate_api_key)])
async def edge_readiness_evidence(limit: int = Query(50, ge=1, le=200)):
    collection = getattr(deps.db, "readiness_evidence", None)
    if collection is None:
        return []
    return await collection.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
```

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest backend\tests\test_readiness_evidence_recorder.py backend\tests\test_edge_handoff_contract.py -q`
Expected: PASS.

### Task 3: Edge Live-Scope Refactor

**Files:**
- Create: `backend/automation_live_scope.py`
- Modify: `backend/automation.py`
- Test: `backend/tests/test_automation_operator_secret.py`

- [ ] **Step 1: Write a pure helper test**

```python
from automation_live_scope import live_scope_allowed


def test_live_scope_allowed_requires_secret_and_phrase():
    assert not live_scope_allowed(
        provided_secret="secret",
        expected_secret="secret",
        provided_phrase="",
    )
    assert live_scope_allowed(
        provided_secret="secret",
        expected_secret="secret",
        provided_phrase="ENABLE LIVE AUTOMATION",
    )
```

- [ ] **Step 2: Implement the helper**

```python
LIVE_AUTOMATION_CONFIRMATION = "ENABLE LIVE AUTOMATION"


def live_scope_allowed(*, provided_secret: str, expected_secret: str, provided_phrase: str) -> bool:
    return bool(
        expected_secret
        and provided_secret == expected_secret
        and provided_phrase == LIVE_AUTOMATION_CONFIRMATION
    )
```

- [ ] **Step 3: Replace inline checks in `automation.py`**

Import `live_scope_allowed` and call it anywhere a live automation mode or live ticker-scope mutation is accepted.

- [ ] **Step 4: Verify Edge**

Run: `python -m pytest backend\tests\test_automation_operator_secret.py backend\tests\test_operator_action_secret.py -q`
Expected: PASS.

### Task 4: Tandem Evidence Panel

**Files:**
- Modify: `server/index.ts`
- Modify: `src/App.tsx`
- Test: `server/relayPolicy.test.ts`

- [ ] **Step 1: Extend Tandem snapshot server-side only**

Add this fetch to `server/index.ts` inside the Pulse Edge-authenticated group:

```ts
const pulseReadinessEvidence = pulseEdge<AnyPayload>('/api/edge/readiness/evidence');
```

Add `pulseReadinessEvidence` to the returned snapshot object.

- [ ] **Step 2: Add a source-string regression**

```ts
test('tandem snapshot reads Pulse readiness evidence through Edge-authenticated routes', () => {
  const source = readFileSync(new URL('./index.ts', import.meta.url), 'utf8');
  assert.match(source, /pulseEdge<[^>]+>\('\/api\/edge\/readiness\/evidence'\)/);
  assert.doesNotMatch(source, /pulse\('\/api\/edge\/readiness\/evidence'\)/);
});
```

- [ ] **Step 3: Verify Tandem**

Run: `npm test`
Expected: PASS.

### Task 5: Auto-Crypto Live-Readiness Module Split

**Files:**
- Create: `src/autocrypto/live_readiness.py`
- Modify: `src/autocrypto/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the gate test**

```python
from autocrypto.live_readiness import live_execution_gate


def test_live_execution_gate_requires_all_live_readiness_inputs():
    result = live_execution_gate(
        venue_live=True,
        approval_mode=True,
        signed_webhook_secret="x" * 32,
        confirmation="ENABLE LIVE CRYPTO TRADING",
    )
    assert result.allowed is True

    missing = live_execution_gate(
        venue_live=True,
        approval_mode=True,
        signed_webhook_secret="x" * 32,
        confirmation="",
    )
    assert missing.allowed is False
    assert "confirmation" in missing.reason
```

- [ ] **Step 2: Implement the module**

```python
from dataclasses import dataclass


LIVE_CRYPTO_CONFIRMATION = "ENABLE LIVE CRYPTO TRADING"


@dataclass(frozen=True)
class LiveExecutionGate:
    allowed: bool
    reason: str = ""


def live_execution_gate(
    *,
    venue_live: bool,
    approval_mode: bool,
    signed_webhook_secret: str,
    confirmation: str,
) -> LiveExecutionGate:
    if not venue_live:
        return LiveExecutionGate(False, "venue is not live-enabled")
    if not approval_mode:
        return LiveExecutionGate(False, "approval mode is required")
    if len(signed_webhook_secret or "") < 32:
        return LiveExecutionGate(False, "signed webhook secret is required")
    if confirmation != LIVE_CRYPTO_CONFIRMATION:
        return LiveExecutionGate(False, "live crypto confirmation is required")
    return LiveExecutionGate(True)
```

- [ ] **Step 3: Verify Auto-Crypto**

Run: `python -m pytest tests/test_config.py tests/test_exchange_capabilities.py -q`
Expected: PASS.

### Task 6: Full Suite Verification

**Files:**
- No code edits.

- [ ] **Step 1: Run Pulse tests**

Run: `python -m pytest backend\tests -q`
Expected: PASS.

- [ ] **Step 2: Run Edge tests**

Run: `python -m pytest backend\tests -q`
Expected: PASS.

- [ ] **Step 3: Run Tandem tests**

Run: `npm test`
Expected: PASS.

- [ ] **Step 4: Run Auto-Crypto tests**

Run: `python -m pytest -q`
Expected: PASS.

## Self-Review

- Spec coverage: The plan covers broker partial-fill capture, burn-in evidence storage, Edge live-scope isolation, Tandem visibility, Auto-Crypto live gate isolation, and full-suite verification.
- Placeholder scan: No step uses TBD/TODO/later language; each task has concrete files and commands.
- Type consistency: Helper names and tests use matching function signatures within each task.
