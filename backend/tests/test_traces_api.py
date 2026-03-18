"""
Test OpenTelemetry Traces API endpoints
Tests: GET /api/traces, filtering, limit functionality
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestTracesAPI:
    """Tests for the /api/traces endpoint"""
    
    def test_get_traces_returns_valid_response(self):
        """GET /api/traces returns {count: int, spans: [...]}"""
        response = requests.get(f"{BASE_URL}/api/traces")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "count" in data, "Response missing 'count' field"
        assert "spans" in data, "Response missing 'spans' field"
        assert isinstance(data["count"], int), "'count' should be an integer"
        assert isinstance(data["spans"], list), "'spans' should be a list"
        assert data["count"] == len(data["spans"]), "count should match spans length"
        print(f"PASS: GET /api/traces returns {data['count']} spans")
    
    def test_span_object_structure(self):
        """Span objects contain required fields: trace_id, span_id, name, kind, status, duration_ms, attributes"""
        response = requests.get(f"{BASE_URL}/api/traces?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        if data["count"] == 0:
            pytest.skip("No spans available to test structure")
        
        span = data["spans"][0]
        required_fields = ["trace_id", "span_id", "name", "kind", "status", "duration_ms", "attributes"]
        for field in required_fields:
            assert field in span, f"Span missing required field: {field}"
        
        # Validate field types
        assert isinstance(span["trace_id"], str), "trace_id should be string"
        assert isinstance(span["span_id"], str), "span_id should be string"
        assert isinstance(span["name"], str), "name should be string"
        assert isinstance(span["kind"], str), "kind should be string"
        assert isinstance(span["status"], str), "status should be string"
        assert isinstance(span["duration_ms"], (int, float)), "duration_ms should be numeric"
        assert isinstance(span["attributes"], dict), "attributes should be dict"
        print(f"PASS: Span object has all required fields with correct types")
    
    def test_traces_filter_by_name_trade(self):
        """GET /api/traces?name=trade filters spans by name containing 'trade'"""
        response = requests.get(f"{BASE_URL}/api/traces?name=trade")
        assert response.status_code == 200
        
        data = response.json()
        for span in data["spans"]:
            assert "trade" in span["name"].lower(), f"Span name '{span['name']}' should contain 'trade'"
        print(f"PASS: Filter by name='trade' returned {data['count']} matching spans")
    
    def test_traces_filter_by_name_ticker(self):
        """GET /api/traces?name=ticker filters spans by name containing 'ticker'"""
        response = requests.get(f"{BASE_URL}/api/traces?name=ticker")
        assert response.status_code == 200
        
        data = response.json()
        for span in data["spans"]:
            assert "ticker" in span["name"].lower(), f"Span name '{span['name']}' should contain 'ticker'"
        print(f"PASS: Filter by name='ticker' returned {data['count']} matching spans")
    
    def test_traces_limit_parameter(self):
        """GET /api/traces?limit=5 limits results to 5 spans"""
        response = requests.get(f"{BASE_URL}/api/traces?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert data["count"] <= 5, f"Expected at most 5 spans, got {data['count']}"
        print(f"PASS: Limit=5 returned {data['count']} spans (max 5)")
    
    def test_traces_limit_and_filter_combined(self):
        """GET /api/traces?name=ticker&limit=3 filters and limits results"""
        response = requests.get(f"{BASE_URL}/api/traces?name=ticker&limit=3")
        assert response.status_code == 200
        
        data = response.json()
        assert data["count"] <= 3, f"Expected at most 3 spans, got {data['count']}"
        for span in data["spans"]:
            assert "ticker" in span["name"].lower(), f"Span '{span['name']}' should contain 'ticker'"
        print(f"PASS: Combined filter name='ticker' & limit=3 returned {data['count']} spans")
    
    def test_span_kinds_present(self):
        """Verify spans have valid kind values (SERVER, INTERNAL, CLIENT)"""
        response = requests.get(f"{BASE_URL}/api/traces?limit=100")
        assert response.status_code == 200
        
        data = response.json()
        valid_kinds = {"SERVER", "INTERNAL", "CLIENT", "PRODUCER", "CONSUMER", "UNSPECIFIED"}
        kinds_found = set()
        
        for span in data["spans"]:
            kinds_found.add(span["kind"])
            assert span["kind"] in valid_kinds, f"Invalid span kind: {span['kind']}"
        
        print(f"PASS: Found valid span kinds: {kinds_found}")
    
    def test_span_status_values(self):
        """Verify spans have valid status values (OK, UNSET, ERROR)"""
        response = requests.get(f"{BASE_URL}/api/traces?limit=100")
        assert response.status_code == 200
        
        data = response.json()
        valid_statuses = {"OK", "UNSET", "ERROR"}
        statuses_found = set()
        
        for span in data["spans"]:
            statuses_found.add(span["status"])
            assert span["status"] in valid_statuses, f"Invalid span status: {span['status']}"
        
        print(f"PASS: Found valid span statuses: {statuses_found}")
    
    def test_trade_execute_span_attributes(self):
        """Verify trade.execute spans have trade-specific attributes"""
        response = requests.get(f"{BASE_URL}/api/traces?name=trade.execute&limit=10")
        assert response.status_code == 200
        
        data = response.json()
        if data["count"] == 0:
            pytest.skip("No trade.execute spans available")
        
        span = data["spans"][0]
        trade_attrs = ["trade.id", "trade.symbol", "trade.side", "trade.price"]
        found_attrs = [attr for attr in trade_attrs if attr in span["attributes"]]
        
        assert len(found_attrs) > 0, "trade.execute span should have trade attributes"
        print(f"PASS: trade.execute span has attributes: {found_attrs}")
    
    def test_ticker_evaluate_span_attributes(self):
        """Verify ticker.evaluate spans have ticker-specific attributes"""
        response = requests.get(f"{BASE_URL}/api/traces?name=ticker.evaluate&limit=10")
        assert response.status_code == 200
        
        data = response.json()
        if data["count"] == 0:
            pytest.skip("No ticker.evaluate spans available")
        
        span = data["spans"][0]
        ticker_attrs = ["ticker.symbol", "ticker.buy_power", "ticker.enabled"]
        found_attrs = [attr for attr in ticker_attrs if attr in span["attributes"]]
        
        assert len(found_attrs) > 0, "ticker.evaluate span should have ticker attributes"
        print(f"PASS: ticker.evaluate span has attributes: {found_attrs}")
    
    def test_http_request_spans_auto_instrumented(self):
        """Verify auto-instrumented HTTP request spans exist"""
        response = requests.get(f"{BASE_URL}/api/traces?limit=200")
        assert response.status_code == 200
        
        data = response.json()
        # Look for SERVER kind spans which are the main HTTP request spans
        http_spans = [s for s in data["spans"] if s["kind"] == "SERVER" and (s["name"].startswith("GET") or s["name"].startswith("POST"))]
        
        assert len(http_spans) > 0, "Should have auto-instrumented HTTP SERVER spans"
        
        # Verify HTTP span has expected attributes
        for span in http_spans[:3]:
            attrs = span["attributes"]
            assert "http.method" in attrs or "http.status_code" in attrs, f"HTTP span should have http attributes, got: {attrs}"
        
        print(f"PASS: Found {len(http_spans)} auto-instrumented HTTP SERVER spans")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
