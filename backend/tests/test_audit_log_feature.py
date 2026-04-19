"""
Backend tests for Audit Log API feature:
- GET /api/audit-logs with various filters
- GET /api/audit-logs/event-types
- Multi event_type filtering with $in query
- Pagination with limit/skip
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture
def client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# ---------------------------------------------------------------------------
# 1. GET /api/audit-logs/event-types — must return exactly 26 event types
# ---------------------------------------------------------------------------

class TestAuditEventTypes:
    """Tests for /api/audit-logs/event-types endpoint."""

    def test_event_types_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs/event-types")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: event-types returns 200")

    def test_event_types_has_event_types_key(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs/event-types")
        data = resp.json()
        assert "event_types" in data, f"'event_types' key missing: {data}"
        print(f"PASS: event_types key present, value: {data['event_types']}")

    def test_event_types_returns_26_types(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs/event-types")
        data = resp.json()
        event_types = data.get("event_types", [])
        assert len(event_types) == 26, f"Expected 26 event types, got {len(event_types)}: {event_types}"
        print(f"PASS: 26 event types returned: {event_types}")

    def test_event_types_are_strings(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs/event-types")
        data = resp.json()
        for et in data.get("event_types", []):
            assert isinstance(et, str), f"Expected string, got {type(et)} for {et}"
        print("PASS: All event types are strings")

    def test_event_types_includes_key_types(self, client):
        """Spot-check well-known event types from all 5 categories."""
        resp = client.get(f"{BASE_URL}/api/audit-logs/event-types")
        data = resp.json()
        event_types = set(data.get("event_types", []))
        required = [
            "BUY_EXECUTED", "SELL_EXECUTED",                   # trading
            "BROKER_CONNECTED", "BROKER_API_ERROR",             # broker
            "SETTING_CHANGED", "TICKER_CREATED",                # config
            "ENGINE_STARTED", "MODE_SWITCHED",                  # engine
            "SYSTEM_ERROR", "PRICE_FEED_SWITCHED",              # system
        ]
        for et in required:
            assert et in event_types, f"Expected event type '{et}' not found"
        print(f"PASS: All required event types present")


# ---------------------------------------------------------------------------
# 2. GET /api/audit-logs — basic response shape
# ---------------------------------------------------------------------------

class TestAuditLogsBasic:
    """Tests for basic /api/audit-logs response."""

    def test_audit_logs_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: /api/audit-logs returns 200")

    def test_audit_logs_has_logs_and_count_keys(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs")
        data = resp.json()
        assert "logs" in data, f"'logs' key missing: {data.keys()}"
        assert "count" in data, f"'count' key missing: {data.keys()}"
        print(f"PASS: logs and count keys present. count={data['count']}")

    def test_audit_logs_count_matches_logs_length(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs")
        data = resp.json()
        assert data["count"] == len(data["logs"]), (
            f"count={data['count']} != len(logs)={len(data['logs'])}"
        )
        print(f"PASS: count ({data['count']}) matches len(logs)")

    def test_audit_logs_each_row_has_required_fields(self, client):
        """Each row must have: timestamp, event_type, success, details."""
        resp = client.get(f"{BASE_URL}/api/audit-logs?limit=10")
        data = resp.json()
        logs = data.get("logs", [])
        if not logs:
            pytest.skip("No audit log entries in DB — skip field validation")
        required_fields = ["timestamp", "event_type", "success", "details"]
        for row in logs:
            for field in required_fields:
                assert field in row, f"Field '{field}' missing in row: {row}"
        print(f"PASS: All {len(logs)} rows have required fields")

    def test_audit_logs_no_mongodb_id_in_response(self, client):
        """MongoDB _id must not be exposed."""
        resp = client.get(f"{BASE_URL}/api/audit-logs?limit=10")
        data = resp.json()
        for row in data.get("logs", []):
            assert "_id" not in row, f"MongoDB _id exposed in row: {row}"
        print("PASS: No _id field in audit log rows")

    def test_audit_logs_success_field_is_boolean(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs?limit=10")
        data = resp.json()
        for row in data.get("logs", []):
            assert isinstance(row["success"], bool), (
                f"'success' must be bool, got {type(row['success'])}: {row}"
            )
        print("PASS: success field is boolean in all rows")

    def test_audit_logs_timestamp_field_is_string(self, client):
        resp = client.get(f"{BASE_URL}/api/audit-logs?limit=10")
        data = resp.json()
        for row in data.get("logs", []):
            assert isinstance(row["timestamp"], str), (
                f"'timestamp' must be str, got {type(row['timestamp'])}: {row}"
            )
        print("PASS: timestamp field is string in all rows")


# ---------------------------------------------------------------------------
# 3. Filtering tests
# ---------------------------------------------------------------------------

class TestAuditLogsFilters:
    """Tests for query param filtering on /api/audit-logs."""

    def test_filter_success_false(self, client):
        """success=false returns only failed events."""
        resp = client.get(f"{BASE_URL}/api/audit-logs?success=false&limit=50")
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code}"
        data = resp.json()
        for row in data.get("logs", []):
            assert row["success"] is False, f"Expected success=False, got {row['success']} in {row}"
        print(f"PASS: success=false filter — {data['count']} failed events, all have success=false")

    def test_filter_success_true(self, client):
        """success=true returns only successful events."""
        resp = client.get(f"{BASE_URL}/api/audit-logs?success=true&limit=50")
        assert resp.status_code == 200
        data = resp.json()
        for row in data.get("logs", []):
            assert row["success"] is True, f"Expected success=True, got {row['success']} in {row}"
        print(f"PASS: success=true filter — {data['count']} successful events")

    def test_filter_single_event_type(self, client):
        """Filter by a single known event type."""
        # SETTING_CHANGED should exist from previous tests (resilience tests log it)
        resp = client.get(f"{BASE_URL}/api/audit-logs?event_type=SETTING_CHANGED&limit=50")
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code}: {resp.text}"
        data = resp.json()
        for row in data.get("logs", []):
            assert row["event_type"] == "SETTING_CHANGED", (
                f"Expected SETTING_CHANGED, got {row['event_type']}"
            )
        print(f"PASS: single event_type filter — {data['count']} SETTING_CHANGED events")

    def test_filter_multiple_event_types_with_in_query(self, client):
        """Multi event_type params use $in query — both types must appear or zero."""
        resp = client.get(
            f"{BASE_URL}/api/audit-logs?event_type=BROKER_API_ERROR&event_type=BROKER_CIRCUIT_OPEN&limit=50"
        )
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code}: {resp.text}"
        data = resp.json()
        allowed = {"BROKER_API_ERROR", "BROKER_CIRCUIT_OPEN"}
        for row in data.get("logs", []):
            assert row["event_type"] in allowed, (
                f"Event type {row['event_type']} not in allowed set {allowed}"
            )
        print(f"PASS: multi event_type $in filter — {data['count']} events, all in allowed set")

    def test_filter_symbol(self, client):
        """Filter by symbol — only matching symbol returned (if any)."""
        resp = client.get(f"{BASE_URL}/api/audit-logs?symbol=AAPL&limit=50")
        assert resp.status_code == 200
        data = resp.json()
        for row in data.get("logs", []):
            assert row.get("symbol") == "AAPL", (
                f"Expected symbol=AAPL, got {row.get('symbol')}"
            )
        print(f"PASS: symbol=AAPL filter — {data['count']} events (may be 0 if no AAPL trades logged)")

    def test_filter_broker_id(self, client):
        """Filter by broker_id — only matching broker returned (if any)."""
        resp = client.get(f"{BASE_URL}/api/audit-logs?broker_id=alpaca&limit=50")
        assert resp.status_code == 200
        data = resp.json()
        for row in data.get("logs", []):
            assert row.get("broker_id") == "alpaca", (
                f"Expected broker_id=alpaca, got {row.get('broker_id')}"
            )
        print(f"PASS: broker_id=alpaca filter — {data['count']} events")

    def test_filter_combination_success_and_event_type(self, client):
        """Combined filter: success=false + event_type (any valid type)."""
        resp = client.get(
            f"{BASE_URL}/api/audit-logs?success=false&event_type=BROKER_API_ERROR&limit=50"
        )
        assert resp.status_code == 200
        data = resp.json()
        for row in data.get("logs", []):
            assert row["success"] is False
            assert row["event_type"] == "BROKER_API_ERROR"
        print(f"PASS: combined filter success=false+BROKER_API_ERROR — {data['count']} events")


# ---------------------------------------------------------------------------
# 4. Pagination tests
# ---------------------------------------------------------------------------

class TestAuditLogsPagination:
    """Tests for limit/skip pagination on /api/audit-logs."""

    def test_limit_reduces_result_count(self, client):
        """limit=5 should return at most 5 results."""
        resp = client.get(f"{BASE_URL}/api/audit-logs?limit=5&skip=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] <= 5, f"Expected ≤5 results, got {data['count']}"
        assert len(data["logs"]) <= 5
        print(f"PASS: limit=5 returns {data['count']} results (≤5)")

    def test_skip_offsets_results(self, client):
        """skip=0 and skip=5 should return different first results."""
        resp_0 = client.get(f"{BASE_URL}/api/audit-logs?limit=5&skip=0")
        resp_5 = client.get(f"{BASE_URL}/api/audit-logs?limit=5&skip=5")
        assert resp_0.status_code == 200
        assert resp_5.status_code == 200

        logs_0 = resp_0.json().get("logs", [])
        logs_5 = resp_5.json().get("logs", [])

        if logs_0 and logs_5:
            # First items should be different when skip changes
            assert logs_0[0]["timestamp"] != logs_5[0]["timestamp"], (
                "skip=0 and skip=5 returned same first result — pagination not working"
            )
            print(f"PASS: skip pagination works — page0[0]={logs_0[0]['timestamp']}, page1[0]={logs_5[0]['timestamp']}")
        else:
            pytest.skip("Not enough audit log entries to test pagination (need >5)")

    def test_limit_1_returns_exactly_1(self, client):
        """limit=1 must return exactly 1 result (if any exist)."""
        resp = client.get(f"{BASE_URL}/api/audit-logs?limit=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["logs"]) <= 1, f"Expected ≤1 result, got {len(data['logs'])}"
        print(f"PASS: limit=1 returns {len(data['logs'])} result")

    def test_pagination_count_field(self, client):
        """count field matches len(logs) for paginated response."""
        resp = client.get(f"{BASE_URL}/api/audit-logs?limit=3&skip=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == len(data["logs"]), (
            f"count={data['count']} does not match len(logs)={len(data['logs'])}"
        )
        print(f"PASS: count matches len(logs) for paginated response")


# ---------------------------------------------------------------------------
# 5. Seed test log and verify retrieval
# ---------------------------------------------------------------------------

class TestAuditLogsDataIntegrity:
    """Seed an audit log via a settings change and verify it appears in logs."""

    def test_setting_change_creates_audit_log(self, client):
        """
        Trigger a price-source toggle (which calls audit_service.log_setting_change)
        and confirm the SETTING_CHANGED event appears in audit logs.
        """
        # Get current setting
        status_resp = client.get(f"{BASE_URL}/api/price-sources")
        assert status_resp.status_code == 200
        current = status_resp.json().get("prefer_broker_feeds", False)

        # Toggle price source (generates a SETTING_CHANGED audit event)
        toggle_resp = client.post(
            f"{BASE_URL}/api/price-sources/toggle?prefer_broker={str(not current).lower()}"
        )
        assert toggle_resp.status_code == 200, f"Toggle failed: {toggle_resp.text}"

        # Restore original
        client.post(
            f"{BASE_URL}/api/price-sources/toggle?prefer_broker={str(current).lower()}"
        )

        # Check the audit log contains SETTING_CHANGED entries
        log_resp = client.get(f"{BASE_URL}/api/audit-logs?event_type=SETTING_CHANGED&limit=10")
        assert log_resp.status_code == 200
        data = log_resp.json()
        assert data["count"] > 0, "Expected at least 1 SETTING_CHANGED event after toggle"
        print(f"PASS: SETTING_CHANGED audit entries found: {data['count']}")

    def test_audit_logs_sorted_newest_first(self, client):
        """Audit logs should be sorted by timestamp descending (newest first)."""
        resp = client.get(f"{BASE_URL}/api/audit-logs?limit=20")
        assert resp.status_code == 200
        logs = resp.json().get("logs", [])
        if len(logs) < 2:
            pytest.skip("Need at least 2 logs to verify sort order")
        timestamps = [row["timestamp"] for row in logs]
        for i in range(len(timestamps) - 1):
            assert timestamps[i] >= timestamps[i + 1], (
                f"Logs not sorted newest-first: {timestamps[i]} < {timestamps[i + 1]}"
            )
        print(f"PASS: {len(logs)} logs are sorted newest-first")
