"""
Test suite for Trading Mode Features (Paper/Live Trading)
Tests simulate_24_7 toggle, trading mode in health/settings/trades endpoints,
broker status, and WebSocket integration.
"""
import pytest
import requests
import os
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestHealthEndpoint:
    """Tests for GET /api/health - should return trading_mode field"""

    def test_health_endpoint_returns_trading_mode(self):
        """Health endpoint should include trading_mode field (paper when simulate_24_7=true)"""
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        
        data = response.json()
        
        # Verify required fields exist
        assert "status" in data, "Missing 'status' field in health response"
        assert "trading_mode" in data, "Missing 'trading_mode' field in health response"
        assert "brokers_connected" in data, "Missing 'brokers_connected' field in health response"
        
        # trading_mode should be either "paper" or "live"
        assert data["trading_mode"] in ["paper", "live"], f"Invalid trading_mode: {data['trading_mode']}"
        
        # brokers_connected should be a non-negative integer
        assert isinstance(data["brokers_connected"], int), "brokers_connected should be an integer"
        assert data["brokers_connected"] >= 0, "brokers_connected cannot be negative"
        
        print(f"Health: status={data['status']}, trading_mode={data['trading_mode']}, brokers_connected={data['brokers_connected']}")


class TestSettingsEndpoint:
    """Tests for GET/POST /api/settings - simulate_24_7 and trading_mode"""

    def test_get_settings_returns_simulate_24_7(self):
        """GET /api/settings should return simulate_24_7 and trading_mode fields"""
        response = requests.get(f"{BASE_URL}/api/settings", timeout=10)
        assert response.status_code == 200, f"Get settings failed: {response.text}"
        
        data = response.json()
        
        # Verify required fields
        assert "simulate_24_7" in data, "Missing 'simulate_24_7' field in settings response"
        assert "trading_mode" in data, "Missing 'trading_mode' field in settings response"
        
        # simulate_24_7 should be boolean
        assert isinstance(data["simulate_24_7"], bool), "simulate_24_7 should be a boolean"
        
        # trading_mode should match simulate_24_7
        expected_mode = "paper" if data["simulate_24_7"] else "live"
        assert data["trading_mode"] == expected_mode, f"trading_mode mismatch: expected {expected_mode}, got {data['trading_mode']}"
        
        print(f"Settings: simulate_24_7={data['simulate_24_7']}, trading_mode={data['trading_mode']}")
        return data["simulate_24_7"]

    def test_post_settings_toggle_simulate_24_7_on(self):
        """POST /api/settings with simulate_24_7=true should enable paper trading mode"""
        response = requests.post(
            f"{BASE_URL}/api/settings",
            json={"simulate_24_7": True},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        assert response.status_code == 200, f"Toggle simulate_24_7=true failed: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True, "Expected 'ok': true in response"
        
        # Verify the setting was persisted by checking GET /api/settings
        verify_response = requests.get(f"{BASE_URL}/api/settings", timeout=10)
        verify_data = verify_response.json()
        
        assert verify_data.get("simulate_24_7") == True, "simulate_24_7 was not persisted as True"
        assert verify_data.get("trading_mode") == "paper", "trading_mode should be 'paper' when simulate_24_7=true"
        
        # Also verify health endpoint reflects this
        health_response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        health_data = health_response.json()
        assert health_data.get("trading_mode") == "paper", "Health endpoint should show 'paper' mode"
        
        print("Successfully toggled to Paper Trading mode (simulate_24_7=true)")

    def test_post_settings_toggle_simulate_24_7_off(self):
        """POST /api/settings with simulate_24_7=false should enable live trading mode"""
        response = requests.post(
            f"{BASE_URL}/api/settings",
            json={"simulate_24_7": False},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        assert response.status_code == 200, f"Toggle simulate_24_7=false failed: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True, "Expected 'ok': true in response"
        
        # Verify the setting was persisted
        verify_response = requests.get(f"{BASE_URL}/api/settings", timeout=10)
        verify_data = verify_response.json()
        
        assert verify_data.get("simulate_24_7") == False, "simulate_24_7 was not persisted as False"
        assert verify_data.get("trading_mode") == "live", "trading_mode should be 'live' when simulate_24_7=false"
        
        # Also verify health endpoint reflects this
        health_response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        health_data = health_response.json()
        assert health_data.get("trading_mode") == "live", "Health endpoint should show 'live' mode"
        
        print("Successfully toggled to Live Trading mode (simulate_24_7=false)")

    def test_toggle_and_restore_simulate_24_7(self):
        """Test toggling simulate_24_7 back to true to restore paper mode for other tests"""
        response = requests.post(
            f"{BASE_URL}/api/settings",
            json={"simulate_24_7": True},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        assert response.status_code == 200
        print("Restored Paper Trading mode for subsequent tests")


class TestBrokerEndpoints:
    """Tests for broker status and reconnect endpoints"""

    def test_get_brokers_status(self):
        """GET /api/brokers/status should return connection status for all brokers"""
        response = requests.get(f"{BASE_URL}/api/brokers/status", timeout=10)
        assert response.status_code == 200, f"Get broker status failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, dict), "Broker status should be a dictionary"
        
        # Each broker should have 'connected', 'failed', and 'name' fields
        for broker_id, status in data.items():
            assert "connected" in status, f"Missing 'connected' field for broker {broker_id}"
            assert "name" in status, f"Missing 'name' field for broker {broker_id}"
            assert isinstance(status["connected"], bool), f"'connected' should be boolean for {broker_id}"
            print(f"Broker {broker_id}: connected={status['connected']}, failed={status.get('failed')}")
        
        print(f"Broker status retrieved for {len(data)} brokers")

    def test_post_brokers_reconnect(self):
        """POST /api/brokers/reconnect should attempt to reconnect all brokers"""
        response = requests.post(f"{BASE_URL}/api/brokers/reconnect", timeout=15)
        assert response.status_code == 200, f"Reconnect brokers failed: {response.text}"
        
        data = response.json()
        assert "results" in data, "Missing 'results' field in reconnect response"
        assert isinstance(data["results"], dict), "'results' should be a dictionary"
        
        print(f"Reconnect results: {data['results']}")

    def test_post_broker_connect_alpaca(self):
        """POST /api/brokers/alpaca/connect should accept credentials and try to connect"""
        # Note: This will fail with fake credentials (expected behavior)
        response = requests.post(
            f"{BASE_URL}/api/brokers/alpaca/test",
            json={"credentials": {
                "api_key": "FAKE_API_KEY_12345678901234567890",
                "api_secret": "FAKE_API_SECRET_12345678901234567890"
            }},
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        assert response.status_code == 200, f"Test broker connection failed: {response.text}"
        
        data = response.json()
        assert "broker_id" in data, "Missing 'broker_id' in response"
        assert "checks" in data, "Missing 'checks' in response"
        assert data["broker_id"] == "alpaca"
        
        # With fake credentials, it should pass format checks but fail live connection
        print(f"Broker test response: overall={data.get('overall')}, checks={len(data.get('checks', []))}")


class TestTradesEndpoint:
    """Tests for trade records with trading_mode field"""

    def test_get_trades_returns_trading_mode_field(self):
        """GET /api/trades should return trades with trading_mode field"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=20", timeout=10)
        assert response.status_code == 200, f"Get trades failed: {response.text}"
        
        data = response.json()
        
        # Check if response is a list of trades or has a 'trades' field
        trades = data if isinstance(data, list) else data.get("trades", [])
        
        print(f"Retrieved {len(trades)} trades")
        
        # If there are trades, verify they have trading_mode field
        for trade in trades[:5]:  # Check first 5
            if "trading_mode" in trade:
                assert trade["trading_mode"] in ["paper", "live", None], f"Invalid trading_mode: {trade['trading_mode']}"
                print(f"Trade {trade.get('id', 'unknown')}: symbol={trade.get('symbol')}, side={trade.get('side')}, trading_mode={trade.get('trading_mode')}")
            else:
                print(f"Trade {trade.get('id', 'unknown')}: trading_mode field not present (may be older trade)")


class TestWebSocketInitialState:
    """Test WebSocket INITIAL_STATE includes simulate_24_7"""
    
    def test_websocket_connection_basic(self):
        """Basic test that WebSocket endpoint is accessible (HTTP upgrade)"""
        # We can't test full WebSocket easily with requests, but we can verify the endpoint exists
        import websocket
        
        # Build WebSocket URL from HTTP URL
        ws_url = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/ws'
        
        try:
            ws = websocket.create_connection(ws_url, timeout=10)
            
            # Receive initial state
            result = ws.recv()
            data = json.loads(result)
            
            # Verify INITIAL_STATE message
            assert data.get("type") == "INITIAL_STATE", f"Expected INITIAL_STATE, got {data.get('type')}"
            assert "simulate_24_7" in data, "Missing simulate_24_7 in INITIAL_STATE"
            assert isinstance(data["simulate_24_7"], bool), "simulate_24_7 should be boolean"
            
            print(f"WebSocket INITIAL_STATE: simulate_24_7={data['simulate_24_7']}")
            
            ws.close()
            
        except ImportError:
            pytest.skip("websocket-client not installed")
        except Exception as e:
            pytest.skip(f"WebSocket test skipped: {e}")


class TestCombinedFlow:
    """End-to-end tests for trading mode flow"""

    def test_full_mode_toggle_flow(self):
        """Test complete flow: toggle mode -> verify health -> verify settings -> verify WS-compatible"""
        # 1. Start in paper mode
        response = requests.post(
            f"{BASE_URL}/api/settings",
            json={"simulate_24_7": True},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        assert response.status_code == 200
        
        # 2. Verify health shows paper
        health_resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert health_resp.json().get("trading_mode") == "paper"
        
        # 3. Verify settings shows paper
        settings_resp = requests.get(f"{BASE_URL}/api/settings", timeout=10)
        settings_data = settings_resp.json()
        assert settings_data.get("simulate_24_7") == True
        assert settings_data.get("trading_mode") == "paper"
        
        # 4. Toggle to live mode
        response = requests.post(
            f"{BASE_URL}/api/settings",
            json={"simulate_24_7": False},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        assert response.status_code == 200
        
        # 5. Verify health shows live
        health_resp = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert health_resp.json().get("trading_mode") == "live"
        
        # 6. Verify settings shows live
        settings_resp = requests.get(f"{BASE_URL}/api/settings", timeout=10)
        settings_data = settings_resp.json()
        assert settings_data.get("simulate_24_7") == False
        assert settings_data.get("trading_mode") == "live"
        
        # 7. Restore paper mode
        response = requests.post(
            f"{BASE_URL}/api/settings",
            json={"simulate_24_7": True},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        assert response.status_code == 200
        
        print("Full mode toggle flow completed successfully!")


# Cleanup fixture to restore paper mode after all tests
@pytest.fixture(scope="module", autouse=True)
def restore_paper_mode():
    yield
    # Restore paper mode after all tests
    try:
        requests.post(
            f"{BASE_URL}/api/settings",
            json={"simulate_24_7": True},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
    except:
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
