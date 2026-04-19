"""
Tests for the resilience architecture (token-bucket rate limiting + circuit breakers).
Covers:
  - GET /api/rate-limits
  - GET /api/rate-limits/{broker_id}
  - POST /api/rate-limits/{broker_id}  (config update)
  - POST /api/circuit/{broker_id}/reset
  - GET /api/audit-logs
  - GET /api/health
  - Static code checks: rate_limiter.py removed, resilience imports correct
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

TEST_BROKER = "alpaca_test"  # synthetic broker id for testing


@pytest.fixture(scope="module")
def client():
    """Shared requests session."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealth:
    """Basic health check to confirm the server is up."""

    def test_health_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_health_response_structure(self, client):
        resp = client.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "online"
        assert "running" in data
        assert "paused" in data


# ---------------------------------------------------------------------------
# GET /api/rate-limits  (all brokers)
# ---------------------------------------------------------------------------

class TestGetAllRateLimits:
    """GET /api/rate-limits — resilience status for all tracked brokers."""

    def test_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/api/rate-limits")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_response_has_brokers_list(self, client):
        resp = client.get(f"{BASE_URL}/api/rate-limits")
        data = resp.json()
        assert "brokers" in data, f"Missing 'brokers' key in response: {data}"
        assert isinstance(data["brokers"], list)

    def test_broker_status_structure(self, client):
        """After we set a config for TEST_BROKER, it must appear in the list with correct fields."""
        # First ensure TEST_BROKER has a status
        client.post(
            f"{BASE_URL}/api/rate-limits/{TEST_BROKER}",
            params={"max_rps": 5.0, "burst": 10},
        )
        resp = client.get(f"{BASE_URL}/api/rate-limits")
        data = resp.json()
        brokers_map = {b["broker_id"]: b for b in data["brokers"]}
        assert TEST_BROKER in brokers_map, f"{TEST_BROKER} not found in brokers list"
        status = brokers_map[TEST_BROKER]
        assert "circuit_state" in status
        assert "recent_failures" in status
        assert "config" in status


# ---------------------------------------------------------------------------
# GET /api/rate-limits/{broker_id}
# ---------------------------------------------------------------------------

class TestGetBrokerRateLimit:
    """GET /api/rate-limits/{broker_id} — per-broker resilience status."""

    def test_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/api/rate-limits/{TEST_BROKER}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_response_contains_required_fields(self, client):
        resp = client.get(f"{BASE_URL}/api/rate-limits/{TEST_BROKER}")
        data = resp.json()
        # Must contain circuit_state, recent_failures, config sub-object
        assert "broker_id" in data, f"Missing 'broker_id': {data}"
        assert "circuit_state" in data, f"Missing 'circuit_state': {data}"
        assert "recent_failures" in data, f"Missing 'recent_failures': {data}"
        assert "config" in data, f"Missing 'config': {data}"

    def test_circuit_state_is_valid_value(self, client):
        resp = client.get(f"{BASE_URL}/api/rate-limits/{TEST_BROKER}")
        data = resp.json()
        assert data["circuit_state"] in ("closed", "open", "half_open"), (
            f"Unexpected circuit_state: {data['circuit_state']}"
        )

    def test_config_has_resilience_fields(self, client):
        resp = client.get(f"{BASE_URL}/api/rate-limits/{TEST_BROKER}")
        data = resp.json()
        cfg = data.get("config", {})
        for field in ("max_rps", "burst", "cooldown_ms", "failure_threshold",
                      "failure_window_seconds", "recovery_timeout_seconds"):
            assert field in cfg, f"Missing config field '{field}': {cfg}"


# ---------------------------------------------------------------------------
# POST /api/rate-limits/{broker_id}  (config update)
# ---------------------------------------------------------------------------

class TestSetBrokerRateLimit:
    """POST /api/rate-limits/{broker_id} — update resilience config."""

    def test_returns_200(self, client):
        resp = client.post(
            f"{BASE_URL}/api/rate-limits/{TEST_BROKER}",
            params={
                "max_rps": 7.5,
                "burst": 15,
                "cooldown_ms": 200,
                "failure_threshold": 3,
                "failure_window_seconds": 30,
                "recovery_timeout_seconds": 45,
                "half_open_max_calls": 2,
                "skip_during_opening": False,
            },
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_response_ok_flag(self, client):
        resp = client.post(
            f"{BASE_URL}/api/rate-limits/{TEST_BROKER}",
            params={"max_rps": 7.5, "burst": 15},
        )
        data = resp.json()
        assert data.get("ok") is True, f"Expected ok=true: {data}"

    def test_config_values_saved(self, client):
        """POST a specific config, then GET and verify it was persisted."""
        resp_post = client.post(
            f"{BASE_URL}/api/rate-limits/{TEST_BROKER}",
            params={
                "max_rps": 12.0,
                "burst": 25,
                "cooldown_ms": 50,
                "failure_threshold": 4,
                "failure_window_seconds": 45,
                "recovery_timeout_seconds": 90,
                "half_open_max_calls": 3,
                "skip_during_opening": True,
            },
        )
        assert resp_post.status_code == 200

        # Verify inline response
        data = resp_post.json()
        assert "config" in data, f"Missing 'config' in response: {data}"
        cfg = data["config"].get("config", {})
        assert cfg.get("max_rps") == 12.0, f"max_rps not saved: {cfg}"
        assert cfg.get("burst") == 25, f"burst not saved: {cfg}"
        assert cfg.get("failure_threshold") == 4, f"failure_threshold not saved: {cfg}"
        assert cfg.get("skip_during_opening") is True, f"skip_during_opening not saved: {cfg}"

    def test_get_reflects_saved_config(self, client):
        """After POST, a GET should return the same values."""
        client.post(
            f"{BASE_URL}/api/rate-limits/{TEST_BROKER}",
            params={"max_rps": 8.0, "burst": 16, "cooldown_ms": 300},
        )
        resp = client.get(f"{BASE_URL}/api/rate-limits/{TEST_BROKER}")
        data = resp.json()
        cfg = data.get("config", {})
        assert cfg.get("max_rps") == 8.0, f"GET config max_rps mismatch: {cfg}"
        assert cfg.get("burst") == 16, f"GET config burst mismatch: {cfg}"
        assert cfg.get("cooldown_ms") == 300, f"GET config cooldown_ms mismatch: {cfg}"

    def test_invalid_max_rps_rejected(self, client):
        """max_rps=0 is below ge=0.1 constraint — should be 422."""
        resp = client.post(
            f"{BASE_URL}/api/rate-limits/{TEST_BROKER}",
            params={"max_rps": 0},
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


# ---------------------------------------------------------------------------
# POST /api/circuit/{broker_id}/reset
# ---------------------------------------------------------------------------

class TestCircuitReset:
    """POST /api/circuit/{broker_id}/reset — manual circuit breaker reset."""

    def test_returns_200(self, client):
        resp = client.post(f"{BASE_URL}/api/circuit/{TEST_BROKER}/reset")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_response_structure(self, client):
        resp = client.post(f"{BASE_URL}/api/circuit/{TEST_BROKER}/reset")
        data = resp.json()
        assert data.get("ok") is True, f"Expected ok=true: {data}"
        assert data.get("broker_id") == TEST_BROKER, f"broker_id mismatch: {data}"
        assert data.get("circuit_state") == "closed", f"Expected circuit_state='closed': {data}"

    def test_circuit_is_closed_after_reset(self, client):
        """After reset, GET should show circuit_state=closed."""
        client.post(f"{BASE_URL}/api/circuit/{TEST_BROKER}/reset")
        resp = client.get(f"{BASE_URL}/api/rate-limits/{TEST_BROKER}")
        data = resp.json()
        assert data.get("circuit_state") == "closed", (
            f"Circuit should be closed after reset, got: {data.get('circuit_state')}"
        )


# ---------------------------------------------------------------------------
# GET /api/audit-logs
# ---------------------------------------------------------------------------

class TestAuditLogs:
    """GET /api/audit-logs — returns audit log entries."""

    def test_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    def test_response_structure(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs")
        data = resp.json()
        assert "logs" in data, f"Missing 'logs' key: {data}"
        assert "count" in data, f"Missing 'count' key: {data}"
        assert isinstance(data["logs"], list)
        assert isinstance(data["count"], int)
        assert data["count"] == len(data["logs"])

    def test_limit_param_respected(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs", params={"limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["logs"]) <= 5, f"Limit not respected: got {len(data['logs'])} logs"

    def test_filter_by_broker_id(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs", params={"broker_id": TEST_BROKER, "limit": 50})
        assert resp.status_code == 200
        data = resp.json()
        # All returned logs (if any) must match the broker_id filter
        for log in data["logs"]:
            assert log.get("broker_id") == TEST_BROKER, (
                f"Log has wrong broker_id: {log.get('broker_id')}"
            )


# ---------------------------------------------------------------------------
# Static / code-level checks (no HTTP)
# ---------------------------------------------------------------------------

class TestStaticCodeChecks:
    """Verify file structure and import hygiene without running the code."""

    def test_rate_limiter_file_deleted(self):
        """rate_limiter.py must NOT exist in /app/backend/."""
        import os
        assert not os.path.exists("/app/backend/rate_limiter.py"), (
            "rate_limiter.py still exists — it should have been deleted"
        )

    def test_no_rate_limiter_imports_in_codebase(self):
        """Scan production source for live imports of the deleted module."""
        import os
        import re
        root = "/app/backend"
        offenders = []
        # Directories to skip (test files, caches, build artifacts)
        SKIP_DIRS = {"tests", "__pycache__", ".pytest_cache", "static"}
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skip dirs in-place so os.walk doesn't descend into them
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                full_path = os.path.join(dirpath, fn)
                try:
                    with open(full_path) as f:
                        content = f.read()
                    # Match real import statements only (skip comment lines)
                    for line in content.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                            continue
                        module_name = "rate_limiter"
                        if re.search(
                            rf"from\s+{module_name}\b|import\s+{module_name}\b",
                            stripped,
                        ):
                            offenders.append(f"{full_path}: {stripped}")
                except Exception:
                    pass
        assert not offenders, f"Found live imports of deleted module: {offenders}"

    def test_broker_manager_imports_from_resilience(self):
        """broker_manager.py _place_single must import from resilience."""
        with open("/app/backend/broker_manager.py") as f:
            content = f.read()
        assert "from resilience import" in content, (
            "broker_manager.py does not import from resilience"
        )
        assert "rate_limiter" not in content or content.count("rate_limiter") == 0, (
            "broker_manager.py still references rate_limiter"
        )

    def test_trading_engine_imports_circuit_open_error(self):
        """trading_engine.py must import CircuitOpenError from resilience."""
        with open("/app/backend/trading_engine.py") as f:
            content = f.read()
        assert "CircuitOpenError" in content, (
            "trading_engine.py does not reference CircuitOpenError"
        )
        assert "from resilience import" in content or "import resilience" in content, (
            "trading_engine.py does not import from resilience"
        )

    def test_server_imports_circuit_open_error(self):
        """server.py must import CircuitOpenError from resilience."""
        with open("/app/backend/server.py") as f:
            content = f.read()
        assert "from resilience import CircuitOpenError" in content, (
            "server.py does not import CircuitOpenError from resilience"
        )

    def test_system_routes_use_broker_resilience(self):
        """routes/system.py must use broker_resilience from resilience module."""
        with open("/app/backend/routes/system.py") as f:
            content = f.read()
        assert "from resilience import broker_resilience" in content, (
            "routes/system.py does not import broker_resilience from resilience"
        )
        assert "rate_limiter" not in content.replace("rate_limiter)", ""), (
            "routes/system.py still has rate_limiter references (non-comment)"
        )
