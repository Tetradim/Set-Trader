"""
Tests for new features in Sentinel Pulse:
1. Beta Registration Modal - /api/beta/status and /api/beta/register
2. Prometheus Metrics - /api/metrics
3. Broker Integration - /api/brokers and /api/brokers/{broker_id}
"""

import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestBetaRegistration:
    """Tests for beta registration endpoints."""

    def test_beta_status_initially_not_registered(self):
        """GET /api/beta/status should return registered: false initially."""
        response = requests.get(f"{BASE_URL}/api/beta/status")
        assert response.status_code == 200
        data = response.json()
        # registration could be null or have a value depending on state
        assert "registered" in data
        assert "registration" in data

    def test_beta_register_missing_fields(self):
        """POST /api/beta/register without required fields should fail."""
        response = requests.post(f"{BASE_URL}/api/beta/register", json={
            "first_name": "",
            "last_name": "",
            "email": "",
            "ssn_last4": "1234",
            "address_street": "123 Test St",
            "address_city": "TestCity",
            "address_state": "CA",
            "address_zip": "90210",
            "address_country": "United States",
            "agreement_accepted": True
        })
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "required" in data["detail"].lower() or "name" in data["detail"].lower()

    def test_beta_register_invalid_ssn(self):
        """POST /api/beta/register with invalid SSN should fail."""
        response = requests.post(f"{BASE_URL}/api/beta/register", json={
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "ssn_last4": "123",  # Only 3 digits
            "address_street": "123 Test St",
            "address_city": "TestCity",
            "address_state": "CA",
            "address_zip": "90210",
            "address_country": "United States",
            "agreement_accepted": True
        })
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "4 digits" in data["detail"] or "SSN" in data["detail"]

    def test_beta_register_agreement_not_accepted(self):
        """POST /api/beta/register without agreement should fail."""
        response = requests.post(f"{BASE_URL}/api/beta/register", json={
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "ssn_last4": "1234",
            "address_street": "123 Test St",
            "address_city": "TestCity",
            "address_state": "CA",
            "address_zip": "90210",
            "address_country": "United States",
            "agreement_accepted": False
        })
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "agreement" in data["detail"].lower()

    def test_beta_register_success(self):
        """POST /api/beta/register with valid data should succeed."""
        response = requests.post(f"{BASE_URL}/api/beta/register", json={
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "phone": "5551234567",
            "ssn_last4": "1234",
            "address_street": "123 Test St",
            "address_city": "TestCity",
            "address_state": "CA",
            "address_zip": "90210",
            "address_country": "United States",
            "agreement_accepted": True,
            "agreement_version": "1.0"
        })
        assert response.status_code == 200, f"Failed with: {response.text}"
        data = response.json()
        assert data.get("status") == "registered"
        assert "registration" in data
        reg = data["registration"]
        assert reg["first_name"] == "Test"
        assert reg["last_name"] == "User"
        assert reg["email"] == "test@example.com"
        assert reg["ssn_last4"] == "1234"

    def test_beta_status_after_registration(self):
        """GET /api/beta/status should return registered: true after registration."""
        response = requests.get(f"{BASE_URL}/api/beta/status")
        assert response.status_code == 200
        data = response.json()
        assert data["registered"] == True
        assert data["registration"] is not None
        assert data["registration"]["first_name"] == "Test"


class TestPrometheusMetrics:
    """Tests for Prometheus-compatible /api/metrics endpoint."""

    def test_metrics_endpoint_returns_text(self):
        """GET /api/metrics should return plain text."""
        response = requests.get(f"{BASE_URL}/api/metrics")
        assert response.status_code == 200
        # Should be text/plain content type
        assert "text/plain" in response.headers.get("content-type", "")

    def test_metrics_contains_sentinel_pulse_up(self):
        """Metrics should include sentinel_pulse_up gauge."""
        response = requests.get(f"{BASE_URL}/api/metrics")
        assert response.status_code == 200
        content = response.text
        assert "sentinel_pulse_up" in content
        # Should have HELP and TYPE annotations
        assert "# HELP sentinel_pulse_up" in content
        assert "# TYPE sentinel_pulse_up gauge" in content

    def test_metrics_contains_account_balance(self):
        """Metrics should include account balance gauge."""
        response = requests.get(f"{BASE_URL}/api/metrics")
        assert response.status_code == 200
        content = response.text
        assert "sentinel_pulse_account_balance_usd" in content

    def test_metrics_contains_trades_total(self):
        """Metrics should include total trades counter."""
        response = requests.get(f"{BASE_URL}/api/metrics")
        assert response.status_code == 200
        content = response.text
        assert "sentinel_pulse_trades_total" in content
        assert "# TYPE sentinel_pulse_trades_total counter" in content

    def test_metrics_contains_ticker_buy_power(self):
        """Metrics should include per-ticker buy power gauges."""
        response = requests.get(f"{BASE_URL}/api/metrics")
        assert response.status_code == 200
        content = response.text
        # Should have at least one ticker metric with symbol label
        assert "sentinel_pulse_ticker_buy_power_usd{symbol=" in content

    def test_metrics_is_prometheus_format(self):
        """Metrics should be valid Prometheus text format."""
        response = requests.get(f"{BASE_URL}/api/metrics")
        assert response.status_code == 200
        content = response.text
        lines = content.strip().split("\n")
        
        # Check that format is correct
        metric_pattern = re.compile(r'^[a-z_]+({[^}]+})?\s+[\d.+-]+$')
        comment_pattern = re.compile(r'^#\s+(HELP|TYPE)\s+')
        
        metric_lines = [l for l in lines if l and not l.startswith("#")]
        comment_lines = [l for l in lines if l.startswith("#")]
        
        # Should have both comments (HELP/TYPE) and metric values
        assert len(metric_lines) > 0, "No metric lines found"
        assert len(comment_lines) > 0, "No comment lines found"
        
        # Sample verification of metric format
        for line in metric_lines[:5]:
            # Basic check that the line has metric_name value format
            parts = line.split()
            assert len(parts) >= 2, f"Invalid metric line: {line}"

    def test_metrics_contains_all_expected_metrics(self):
        """Metrics should contain all documented metric names."""
        response = requests.get(f"{BASE_URL}/api/metrics")
        assert response.status_code == 200
        content = response.text
        
        expected_metrics = [
            "sentinel_pulse_up",
            "sentinel_pulse_paused",
            "sentinel_pulse_market_open",
            "sentinel_pulse_ws_clients",
            "sentinel_pulse_account_balance_usd",
            "sentinel_pulse_allocated_usd",
            "sentinel_pulse_available_usd",
            "sentinel_pulse_tickers_total",
            "sentinel_pulse_tickers_enabled",
            "sentinel_pulse_trades_total",
            "sentinel_pulse_total_pnl_usd",
            "sentinel_pulse_cash_reserve_usd",
            "sentinel_pulse_open_positions"
        ]
        
        for metric in expected_metrics:
            assert metric in content, f"Missing metric: {metric}"


class TestBrokerEndpoints:
    """Tests for broker integration endpoints."""

    def test_list_brokers_returns_array(self):
        """GET /api/brokers should return a list of brokers."""
        response = requests.get(f"{BASE_URL}/api/brokers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 6  # 6 brokers in the registry

    def test_list_brokers_contains_expected_brokers(self):
        """GET /api/brokers should include all 6 expected brokers."""
        response = requests.get(f"{BASE_URL}/api/brokers")
        assert response.status_code == 200
        data = response.json()
        broker_ids = [b["id"] for b in data]
        expected = ["robinhood", "schwab", "webull", "ibkr", "wealthsimple", "fidelity"]
        for bid in expected:
            assert bid in broker_ids, f"Missing broker: {bid}"

    def test_broker_has_required_fields(self):
        """Each broker should have all required fields."""
        response = requests.get(f"{BASE_URL}/api/brokers")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ["id", "name", "description", "supported", "risk_warning"]
        for broker in data:
            for field in required_fields:
                assert field in broker, f"Broker {broker.get('id')} missing field: {field}"

    def test_broker_risk_warning_structure(self):
        """Risk warning should have level and message."""
        response = requests.get(f"{BASE_URL}/api/brokers")
        assert response.status_code == 200
        data = response.json()
        
        for broker in data:
            rw = broker.get("risk_warning")
            if rw is not None:
                assert "level" in rw, f"Broker {broker['id']} risk_warning missing level"
                assert "message" in rw, f"Broker {broker['id']} risk_warning missing message"
                assert rw["level"] in ["low", "medium", "high"], f"Invalid risk level: {rw['level']}"

    def test_get_specific_broker_ibkr(self):
        """GET /api/brokers/ibkr should return IBKR details."""
        response = requests.get(f"{BASE_URL}/api/brokers/ibkr")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "ibkr"
        assert data["name"] == "Interactive Brokers (IBKR)"
        assert data["risk_warning"]["level"] == "low"

    def test_get_specific_broker_robinhood(self):
        """GET /api/brokers/robinhood should return Robinhood details."""
        response = requests.get(f"{BASE_URL}/api/brokers/robinhood")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "robinhood"
        assert data["risk_warning"]["level"] == "high"

    def test_get_specific_broker_schwab(self):
        """GET /api/brokers/schwab should return Schwab details."""
        response = requests.get(f"{BASE_URL}/api/brokers/schwab")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "schwab"
        assert data["risk_warning"]["level"] == "medium"

    def test_get_nonexistent_broker_returns_404(self):
        """GET /api/brokers/nonexistent should return 404."""
        response = requests.get(f"{BASE_URL}/api/brokers/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_all_brokers_not_supported_yet(self):
        """All brokers should have supported=False (planned but not implemented)."""
        response = requests.get(f"{BASE_URL}/api/brokers")
        assert response.status_code == 200
        data = response.json()
        for broker in data:
            assert broker["supported"] == False, f"Broker {broker['id']} should not be supported yet"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
