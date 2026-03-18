"""
Test file for Broker API endpoints.
Tests: GET /api/brokers, GET /api/brokers/{id}, POST /api/brokers/{id}/test
10 brokers total: alpaca, ibkr, td_ameritrade, tradier, robinhood, tradestation, thinkorswim, webull, wealthsimple, fidelity
9 supported=True, 1 (fidelity) supported=False
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestBrokersListEndpoint:
    """Test GET /api/brokers — list all brokers"""

    def test_list_brokers_returns_200(self):
        """GET /api/brokers should return 200 with list of brokers"""
        response = requests.get(f"{BASE_URL}/api/brokers")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"PASS: GET /api/brokers returned {len(data)} brokers")

    def test_list_brokers_returns_10_brokers(self):
        """GET /api/brokers should return exactly 10 brokers"""
        response = requests.get(f"{BASE_URL}/api/brokers")
        data = response.json()
        assert len(data) == 10, f"Expected 10 brokers, got {len(data)}"
        print("PASS: Got all 10 brokers")

    def test_brokers_have_required_fields(self):
        """Each broker should have id, name, description, supported, color, auth_fields, risk_warning"""
        response = requests.get(f"{BASE_URL}/api/brokers")
        data = response.json()
        required_fields = ["id", "name", "description", "supported", "color", "auth_fields", "risk_warning"]
        for broker in data:
            for field in required_fields:
                assert field in broker, f"Broker {broker.get('id', 'unknown')} missing field '{field}'"
        print("PASS: All brokers have required fields")

    def test_nine_brokers_are_supported(self):
        """9 out of 10 brokers should have supported=True"""
        response = requests.get(f"{BASE_URL}/api/brokers")
        data = response.json()
        supported_count = sum(1 for b in data if b["supported"])
        assert supported_count == 9, f"Expected 9 supported brokers, got {supported_count}"
        print("PASS: 9 brokers are supported")

    def test_fidelity_is_not_supported(self):
        """Fidelity should be the only unsupported broker"""
        response = requests.get(f"{BASE_URL}/api/brokers")
        data = response.json()
        unsupported = [b for b in data if not b["supported"]]
        assert len(unsupported) == 1, f"Expected 1 unsupported broker, got {len(unsupported)}"
        assert unsupported[0]["id"] == "fidelity", f"Expected fidelity to be unsupported, got {unsupported[0]['id']}"
        print("PASS: Fidelity is the only unsupported broker")


class TestBrokerDetailEndpoint:
    """Test GET /api/brokers/{broker_id} — single broker details"""

    def test_get_alpaca_details(self):
        """GET /api/brokers/alpaca should return Alpaca with color=#22c55e"""
        response = requests.get(f"{BASE_URL}/api/brokers/alpaca")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "alpaca"
        assert data["name"] == "Alpaca"
        assert data["color"] == "#22c55e"
        assert data["supported"] == True
        assert "api_key" in data["auth_fields"]
        assert "api_secret" in data["auth_fields"]
        print("PASS: Alpaca details correct with color #22c55e")

    def test_get_tradier_details(self):
        """GET /api/brokers/tradier should return Tradier with color=#8b5cf6"""
        response = requests.get(f"{BASE_URL}/api/brokers/tradier")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "tradier"
        assert data["name"] == "Tradier"
        assert data["color"] == "#8b5cf6"
        assert data["supported"] == True
        print("PASS: Tradier details correct with color #8b5cf6")

    def test_get_ibkr_details(self):
        """GET /api/brokers/ibkr should return IBKR with supported=True"""
        response = requests.get(f"{BASE_URL}/api/brokers/ibkr")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "ibkr"
        assert data["supported"] == True
        assert "gateway_url" in data["auth_fields"]
        assert "account_id" in data["auth_fields"]
        print("PASS: IBKR details correct")

    def test_get_fidelity_details(self):
        """GET /api/brokers/fidelity should return Fidelity with supported=False"""
        response = requests.get(f"{BASE_URL}/api/brokers/fidelity")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "fidelity"
        assert data["supported"] == False
        print("PASS: Fidelity has supported=False")

    def test_nonexistent_broker_returns_404(self):
        """GET /api/brokers/nonexistent should return 404"""
        response = requests.get(f"{BASE_URL}/api/brokers/nonexistent")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Nonexistent broker returns 404")

    def test_all_broker_colors(self):
        """Verify each broker has a valid color"""
        broker_colors = {
            "alpaca": "#22c55e",
            "ibkr": "#e11d48",
            "td_ameritrade": "#3b82f6",
            "tradier": "#8b5cf6",
            "robinhood": "#00c805",
            "tradestation": "#0066cc",
            "thinkorswim": "#ff6600",
            "webull": "#f59e0b",
            "wealthsimple": "#f97316",
            "fidelity": "#4ade80",
        }
        for broker_id, expected_color in broker_colors.items():
            response = requests.get(f"{BASE_URL}/api/brokers/{broker_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["color"] == expected_color, f"Broker {broker_id} color mismatch: expected {expected_color}, got {data['color']}"
        print("PASS: All broker colors verified")


class TestBrokerTestEndpoint:
    """Test POST /api/brokers/{broker_id}/test — credential validation"""

    def test_alpaca_valid_format_passes_format_validation(self):
        """Alpaca with valid-format credentials should pass required_fields and format_validation"""
        response = requests.post(
            f"{BASE_URL}/api/brokers/alpaca/test",
            json={"credentials": {
                "api_key": "PKABCDEFGHIJ1234567890",
                "api_secret": "abcdefghijklmnopqrstuvwxyz123456789",
                "paper": "true"
            }}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["broker_id"] == "alpaca"
        
        # Find checks by name
        checks_by_name = {c["name"]: c for c in data["checks"]}
        
        # Required fields should pass
        assert "required_fields" in checks_by_name
        assert checks_by_name["required_fields"]["status"] == "pass"
        
        # Format validation should pass
        assert "format_validation" in checks_by_name
        assert checks_by_name["format_validation"]["status"] == "pass"
        
        print("PASS: Alpaca with valid format passes required_fields and format_validation")

    def test_alpaca_short_api_key_fails_format_validation(self):
        """Alpaca with short api_key should fail format_validation"""
        response = requests.post(
            f"{BASE_URL}/api/brokers/alpaca/test",
            json={"credentials": {
                "api_key": "short",
                "api_secret": "abcdefghijklmnopqrstuvwxyz123456789",
                "paper": "true"
            }}
        )
        assert response.status_code == 200
        data = response.json()
        
        checks_by_name = {c["name"]: c for c in data["checks"]}
        
        # Required fields should pass
        assert checks_by_name["required_fields"]["status"] == "pass"
        
        # Format validation should fail
        assert "format_validation" in checks_by_name
        assert checks_by_name["format_validation"]["status"] == "fail"
        assert "too short" in checks_by_name["format_validation"]["message"].lower()
        
        print("PASS: Alpaca with short api_key fails format_validation")

    def test_robinhood_missing_username_fails_required_fields(self):
        """Robinhood with missing username should fail required_fields"""
        response = requests.post(
            f"{BASE_URL}/api/brokers/robinhood/test",
            json={"credentials": {
                "password": "testpassword123",
                "mfa_code": "123456"
            }}
        )
        assert response.status_code == 200
        data = response.json()
        
        checks_by_name = {c["name"]: c for c in data["checks"]}
        
        # Required fields should fail
        assert "required_fields" in checks_by_name
        assert checks_by_name["required_fields"]["status"] == "fail"
        assert "username" in checks_by_name["required_fields"]["message"].lower()
        
        print("PASS: Robinhood with missing username fails required_fields")

    def test_ibkr_valid_format_passes_checks(self):
        """IBKR with valid gateway_url and account_id should pass format checks"""
        response = requests.post(
            f"{BASE_URL}/api/brokers/ibkr/test",
            json={"credentials": {
                "gateway_url": "https://localhost:5000",
                "account_id": "U1234567"
            }}
        )
        assert response.status_code == 200
        data = response.json()
        
        checks_by_name = {c["name"]: c for c in data["checks"]}
        
        # Required fields should pass
        assert checks_by_name["required_fields"]["status"] == "pass"
        
        # Format validation should pass
        assert checks_by_name["format_validation"]["status"] == "pass"
        
        print("PASS: IBKR with valid format passes format checks")

    def test_tradier_short_access_token_fails_format(self):
        """Tradier with short access_token should fail format_validation"""
        response = requests.post(
            f"{BASE_URL}/api/brokers/tradier/test",
            json={"credentials": {
                "access_token": "short",
                "account_id": "12345678"
            }}
        )
        assert response.status_code == 200
        data = response.json()
        
        checks_by_name = {c["name"]: c for c in data["checks"]}
        
        # Required fields should pass
        assert checks_by_name["required_fields"]["status"] == "pass"
        
        # Format validation should fail
        assert checks_by_name["format_validation"]["status"] == "fail"
        assert "too short" in checks_by_name["format_validation"]["message"].lower()
        
        print("PASS: Tradier with short access_token fails format_validation")

    def test_fidelity_with_valid_creds_fails_at_live_connection(self):
        """Fidelity should pass format but fail at live_connection (has adapter but returns False)"""
        response = requests.post(
            f"{BASE_URL}/api/brokers/fidelity/test",
            json={"credentials": {
                "username": "testuser",
                "password": "testpassword123"
            }}
        )
        assert response.status_code == 200
        data = response.json()
        
        checks_by_name = {c["name"]: c for c in data["checks"]}
        
        # Required fields should pass
        assert checks_by_name["required_fields"]["status"] == "pass"
        
        # Format validation should pass
        assert checks_by_name["format_validation"]["status"] == "pass"
        
        # Should fail at live_connection since Fidelity adapter returns False
        assert "live_connection" in checks_by_name
        assert checks_by_name["live_connection"]["status"] == "fail"
        
        print("PASS: Fidelity passes format checks but fails at live_connection")

    def test_alpaca_fake_creds_fail_at_live_connection(self):
        """Alpaca with fake but valid-format creds should fail at live_connection"""
        response = requests.post(
            f"{BASE_URL}/api/brokers/alpaca/test",
            json={"credentials": {
                "api_key": "FAKE_KEY_LONG_ENOUGH_12345",
                "api_secret": "fake_secret_long_enough_for_validation_123456789",
                "paper": "true"
            }}
        )
        assert response.status_code == 200
        data = response.json()
        
        checks_by_name = {c["name"]: c for c in data["checks"]}
        
        # Format should pass
        assert checks_by_name["required_fields"]["status"] == "pass"
        assert checks_by_name["format_validation"]["status"] == "pass"
        
        # Live connection should fail with fake credentials
        assert "live_connection" in checks_by_name
        assert checks_by_name["live_connection"]["status"] == "fail"
        
        print("PASS: Alpaca with fake creds fails at live_connection (expected)")


class TestBrokerRiskWarnings:
    """Test broker risk warnings are properly included"""

    def test_robinhood_has_high_risk(self):
        """Robinhood should have high risk warning"""
        response = requests.get(f"{BASE_URL}/api/brokers/robinhood")
        data = response.json()
        assert data["risk_warning"] is not None
        assert data["risk_warning"]["level"] == "high"
        print("PASS: Robinhood has high risk warning")

    def test_alpaca_has_low_risk(self):
        """Alpaca should have low risk warning"""
        response = requests.get(f"{BASE_URL}/api/brokers/alpaca")
        data = response.json()
        assert data["risk_warning"] is not None
        assert data["risk_warning"]["level"] == "low"
        print("PASS: Alpaca has low risk warning")

    def test_webull_has_high_risk(self):
        """Webull should have high risk warning (unofficial API)"""
        response = requests.get(f"{BASE_URL}/api/brokers/webull")
        data = response.json()
        assert data["risk_warning"] is not None
        assert data["risk_warning"]["level"] == "high"
        print("PASS: Webull has high risk warning")

    def test_td_ameritrade_has_medium_risk(self):
        """TD Ameritrade should have medium risk warning"""
        response = requests.get(f"{BASE_URL}/api/brokers/td_ameritrade")
        data = response.json()
        assert data["risk_warning"] is not None
        assert data["risk_warning"]["level"] == "medium"
        print("PASS: TD Ameritrade has medium risk warning")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
