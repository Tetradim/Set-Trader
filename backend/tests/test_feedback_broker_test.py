"""
Tests for new features:
1. Feedback/Bug Report system (POST /api/feedback)
2. Broker Test Connection (POST /api/brokers/{id}/test)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestFeedbackEndpoint:
    """Test /api/feedback endpoint - Bug report, error log, suggestion, complaint submission"""

    def test_feedback_requires_subject(self):
        """POST /api/feedback with empty subject returns 400"""
        response = requests.post(f"{BASE_URL}/api/feedback", json={
            "type": "bug",
            "subject": "",
            "description": "Test description"
        })
        assert response.status_code == 400
        assert "Subject and description are required" in response.json().get("detail", "")

    def test_feedback_requires_description(self):
        """POST /api/feedback with empty description returns 400"""
        response = requests.post(f"{BASE_URL}/api/feedback", json={
            "type": "bug",
            "subject": "Test subject",
            "description": ""
        })
        assert response.status_code == 400
        assert "Subject and description are required" in response.json().get("detail", "")

    def test_feedback_invalid_type(self):
        """POST /api/feedback with invalid type returns 400"""
        response = requests.post(f"{BASE_URL}/api/feedback", json={
            "type": "invalid_type",
            "subject": "Test subject",
            "description": "Test description"
        })
        assert response.status_code == 400
        assert "Type must be one of" in response.json().get("detail", "")

    def test_feedback_bug_report_valid(self):
        """POST /api/feedback with valid bug report returns success"""
        response = requests.post(f"{BASE_URL}/api/feedback", json={
            "type": "bug",
            "subject": "Test Bug Report",
            "description": "This is a test bug description"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert data["email_sent"] == False  # SMTP not configured
        assert "feedback" in data
        assert data["feedback"]["type"] == "bug"
        assert data["feedback"]["subject"] == "Test Bug Report"
        assert data["feedback"]["description"] == "This is a test bug description"
        assert "user_name" in data["feedback"]
        assert "user_email" in data["feedback"]
        assert "app_version" in data["feedback"]
        assert "timestamp" in data["feedback"]

    def test_feedback_error_report_valid(self):
        """POST /api/feedback with valid error report returns success"""
        response = requests.post(f"{BASE_URL}/api/feedback", json={
            "type": "error",
            "subject": "Test Error Report",
            "description": "Error occurred during testing",
            "error_log": "Error: Something went wrong\nat line 123"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert data["feedback"]["type"] == "error"
        assert data["feedback"]["error_log"] == "Error: Something went wrong\nat line 123"

    def test_feedback_suggestion_valid(self):
        """POST /api/feedback with valid suggestion returns success"""
        response = requests.post(f"{BASE_URL}/api/feedback", json={
            "type": "suggestion",
            "subject": "Feature Request",
            "description": "Please add dark mode support"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert data["feedback"]["type"] == "suggestion"

    def test_feedback_complaint_valid(self):
        """POST /api/feedback with valid complaint returns success"""
        response = requests.post(f"{BASE_URL}/api/feedback", json={
            "type": "complaint",
            "subject": "Performance Issue",
            "description": "The app is slow when loading tickers"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert data["feedback"]["type"] == "complaint"


class TestBrokerTestConnection:
    """Test /api/brokers/{id}/test endpoint - Credential validation dry-run"""

    def test_broker_test_ibkr_missing_credentials(self):
        """POST /api/brokers/ibkr/test with missing credentials returns fail"""
        response = requests.post(f"{BASE_URL}/api/brokers/ibkr/test", json={
            "credentials": {"host": "127.0.0.1"}  # Missing port and client_id
        })
        assert response.status_code == 200
        data = response.json()
        assert data["broker_id"] == "ibkr"
        assert data["overall"] == "fail"
        assert any(check["name"] == "required_fields" and check["status"] == "fail" for check in data["checks"])
        # Check that the missing fields are mentioned
        missing_msg = [c for c in data["checks"] if c["name"] == "required_fields"][0]["message"]
        assert "port" in missing_msg or "client_id" in missing_msg

    def test_broker_test_ibkr_invalid_port_format(self):
        """POST /api/brokers/ibkr/test with invalid port format returns fail"""
        response = requests.post(f"{BASE_URL}/api/brokers/ibkr/test", json={
            "credentials": {
                "host": "127.0.0.1",
                "port": "invalid_port",  # Should be numeric
                "client_id": "1"
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["overall"] == "fail"
        assert any(check["name"] == "format_validation" and check["status"] == "fail" for check in data["checks"])
        format_msg = [c for c in data["checks"] if c["name"] == "format_validation"][0]["message"]
        assert "port" in format_msg.lower()

    def test_broker_test_ibkr_valid_credentials_partial_pass(self):
        """POST /api/brokers/ibkr/test with valid credentials returns partial (adapter not implemented)"""
        response = requests.post(f"{BASE_URL}/api/brokers/ibkr/test", json={
            "credentials": {
                "host": "127.0.0.1",
                "port": "7497",
                "client_id": "1"
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["broker_id"] == "ibkr"
        # Since adapter is not implemented, should get partial pass
        assert data["overall"] == "partial"
        assert any(check["name"] == "required_fields" and check["status"] == "pass" for check in data["checks"])
        assert any(check["name"] == "format_validation" and check["status"] == "pass" for check in data["checks"])
        assert any(check["name"] == "adapter_available" and check["status"] == "warn" for check in data["checks"])

    def test_broker_test_robinhood_missing_credentials(self):
        """POST /api/brokers/robinhood/test with missing credentials returns fail"""
        response = requests.post(f"{BASE_URL}/api/brokers/robinhood/test", json={
            "credentials": {"username": "testuser"}  # Missing password and mfa_code
        })
        assert response.status_code == 200
        data = response.json()
        assert data["broker_id"] == "robinhood"
        assert data["overall"] == "fail"
        required_check = [c for c in data["checks"] if c["name"] == "required_fields"][0]
        assert required_check["status"] == "fail"
        assert "password" in required_check["message"] or "mfa_code" in required_check["message"]

    def test_broker_test_robinhood_invalid_mfa(self):
        """POST /api/brokers/robinhood/test with invalid mfa_code format returns fail"""
        response = requests.post(f"{BASE_URL}/api/brokers/robinhood/test", json={
            "credentials": {
                "username": "testuser",
                "password": "testpass",
                "mfa_code": "1234"  # Should be 6 digits
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["overall"] == "fail"
        format_check = [c for c in data["checks"] if c["name"] == "format_validation"][0]
        assert format_check["status"] == "fail"
        assert "mfa_code" in format_check["message"]

    def test_broker_test_robinhood_valid_partial(self):
        """POST /api/brokers/robinhood/test with valid credentials returns partial"""
        response = requests.post(f"{BASE_URL}/api/brokers/robinhood/test", json={
            "credentials": {
                "username": "testuser",
                "password": "testpass",
                "mfa_code": "123456"
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["overall"] == "partial"

    def test_broker_test_schwab_short_app_key(self):
        """POST /api/brokers/schwab/test with short app_key returns fail"""
        response = requests.post(f"{BASE_URL}/api/brokers/schwab/test", json={
            "credentials": {
                "app_key": "short",  # Too short (less than 8 chars)
                "app_secret": "longenoughsecret",
                "refresh_token": "some_token_value"
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["overall"] == "fail"
        format_check = [c for c in data["checks"] if c["name"] == "format_validation"][0]
        assert format_check["status"] == "fail"
        assert "app_key" in format_check["message"]

    def test_broker_test_schwab_valid_partial(self):
        """POST /api/brokers/schwab/test with valid credentials returns partial"""
        response = requests.post(f"{BASE_URL}/api/brokers/schwab/test", json={
            "credentials": {
                "app_key": "valid_app_key_12345",
                "app_secret": "valid_secret_123",
                "refresh_token": "some_refresh_token"
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["overall"] == "partial"

    def test_broker_test_webull_invalid_pin(self):
        """POST /api/brokers/webull/test with invalid trading_pin returns fail"""
        response = requests.post(f"{BASE_URL}/api/brokers/webull/test", json={
            "credentials": {
                "email": "test@example.com",
                "password": "testpass",
                "trading_pin": "12"  # Too short (less than 4 digits)
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert data["overall"] == "fail"
        format_check = [c for c in data["checks"] if c["name"] == "format_validation"][0]
        assert format_check["status"] == "fail"
        assert "trading_pin" in format_check["message"]

    def test_broker_test_nonexistent_broker(self):
        """POST /api/brokers/nonexistent/test returns 404"""
        response = requests.post(f"{BASE_URL}/api/brokers/nonexistent/test", json={
            "credentials": {}
        })
        assert response.status_code == 404


class TestBrokerEndpointList:
    """Verify broker list endpoints are working (supplementary check)"""

    def test_brokers_list_has_6_brokers(self):
        """GET /api/brokers returns 6 brokers"""
        response = requests.get(f"{BASE_URL}/api/brokers")
        assert response.status_code == 200
        brokers = response.json()
        assert len(brokers) == 6
        broker_ids = [b["id"] for b in brokers]
        assert set(broker_ids) == {"robinhood", "schwab", "webull", "ibkr", "wealthsimple", "fidelity"}

    def test_each_broker_has_auth_fields(self):
        """Each broker has auth_fields defined"""
        response = requests.get(f"{BASE_URL}/api/brokers")
        brokers = response.json()
        for broker in brokers:
            assert "auth_fields" in broker
            assert isinstance(broker["auth_fields"], list)
            assert len(broker["auth_fields"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
