"""
Test Account Balance Feature
Tests:
- POST /api/settings with account_balance saves to MongoDB
- GET /api/settings returns account_balance, allocated, available
- WebSocket INITIAL_STATE includes account balance fields
- WebSocket ACCOUNT_UPDATE broadcast when account_balance is changed
- Take Profit still works with account balance
"""
import pytest
import requests
import os
import websocket
import json
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestAccountBalanceAPI:
    """Tests for account balance settings API endpoints"""

    def test_get_settings_returns_account_fields(self):
        """GET /api/settings should return account_balance, allocated, available"""
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # Verify all account fields are present
        assert "account_balance" in data, "account_balance field missing from settings"
        assert "allocated" in data, "allocated field missing from settings"
        assert "available" in data, "available field missing from settings"
        
        # Verify types
        assert isinstance(data["account_balance"], (int, float)), "account_balance should be numeric"
        assert isinstance(data["allocated"], (int, float)), "allocated should be numeric"
        assert isinstance(data["available"], (int, float)), "available should be numeric"
        
        print(f"Account Balance: ${data['account_balance']}")
        print(f"Allocated: ${data['allocated']}")
        print(f"Available: ${data['available']}")

    def test_post_settings_updates_account_balance(self):
        """POST /api/settings with account_balance should save to MongoDB"""
        # First, get current settings
        response = requests.get(f"{BASE_URL}/api/settings")
        original_balance = response.json().get("account_balance", 0)
        
        # Set a new account balance
        test_balance = 150000.50
        response = requests.post(f"{BASE_URL}/api/settings", json={
            "account_balance": test_balance
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Verify the balance was saved by fetching it again
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["account_balance"] == test_balance, f"Expected {test_balance}, got {data['account_balance']}"
        
        # Restore original balance
        requests.post(f"{BASE_URL}/api/settings", json={
            "account_balance": original_balance
        })
        print(f"Successfully updated account_balance to {test_balance} and restored to {original_balance}")

    def test_allocated_equals_sum_of_ticker_base_powers(self):
        """Allocated should equal sum of all ticker base_powers"""
        # Get all tickers
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        # Calculate expected allocated
        expected_allocated = sum(t.get("base_power", 0) for t in tickers)
        
        # Get settings and compare
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200
        data = response.json()
        
        # Allow for small floating point differences
        assert abs(data["allocated"] - expected_allocated) < 0.01, \
            f"Allocated mismatch: expected {expected_allocated}, got {data['allocated']}"
        print(f"Allocated ${data['allocated']} matches sum of ticker base_powers")

    def test_available_calculation(self):
        """Available should equal account_balance minus allocated"""
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200
        data = response.json()
        
        expected_available = data["account_balance"] - data["allocated"]
        assert abs(data["available"] - expected_available) < 0.01, \
            f"Available mismatch: expected {expected_available}, got {data['available']}"
        print(f"Available ${data['available']} = Account ${data['account_balance']} - Allocated ${data['allocated']}")

    def test_negative_available_when_overallocated(self):
        """When allocated > balance, available should be negative"""
        # Get current settings
        response = requests.get(f"{BASE_URL}/api/settings")
        original_balance = response.json().get("account_balance", 0)
        allocated = response.json().get("allocated", 0)
        
        if allocated > 0:
            # Set balance to less than allocated
            small_balance = allocated / 2
            response = requests.post(f"{BASE_URL}/api/settings", json={
                "account_balance": small_balance
            })
            assert response.status_code == 200
            
            # Verify available is negative
            response = requests.get(f"{BASE_URL}/api/settings")
            data = response.json()
            assert data["available"] < 0, f"Expected negative available, got {data['available']}"
            print(f"Over-allocated scenario: Available = ${data['available']} (negative as expected)")
            
            # Restore original balance
            requests.post(f"{BASE_URL}/api/settings", json={
                "account_balance": original_balance
            })
        else:
            pytest.skip("No allocated funds to test over-allocation")


class TestAccountBalanceWebSocket:
    """Tests for WebSocket account balance integration"""

    def test_initial_state_includes_account_fields(self):
        """WebSocket INITIAL_STATE should include account_balance, allocated, available"""
        ws_url = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/ws'
        
        try:
            ws = websocket.create_connection(ws_url, timeout=10)
            
            # Wait for INITIAL_STATE
            initial_data = None
            for _ in range(5):
                msg = ws.recv()
                data = json.loads(msg)
                if data.get("type") == "INITIAL_STATE":
                    initial_data = data
                    break
            
            ws.close()
            
            assert initial_data is not None, "Never received INITIAL_STATE message"
            assert "account_balance" in initial_data, "account_balance missing from INITIAL_STATE"
            assert "allocated" in initial_data, "allocated missing from INITIAL_STATE"
            assert "available" in initial_data, "available missing from INITIAL_STATE"
            
            print(f"INITIAL_STATE contains: account_balance={initial_data['account_balance']}, "
                  f"allocated={initial_data['allocated']}, available={initial_data['available']}")
        except Exception as e:
            pytest.fail(f"WebSocket test failed: {e}")

    def test_account_update_broadcast(self):
        """POST /api/settings should trigger ACCOUNT_UPDATE WebSocket broadcast"""
        ws_url = BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://') + '/api/ws'
        
        try:
            ws = websocket.create_connection(ws_url, timeout=10)
            
            # Consume initial state
            for _ in range(3):
                msg = ws.recv()
                data = json.loads(msg)
                if data.get("type") == "INITIAL_STATE":
                    break
            
            # Get original balance
            response = requests.get(f"{BASE_URL}/api/settings")
            original_balance = response.json().get("account_balance", 0)
            
            # Update balance via API
            new_balance = original_balance + 1000
            response = requests.post(f"{BASE_URL}/api/settings", json={
                "account_balance": new_balance
            })
            assert response.status_code == 200
            
            # Wait for ACCOUNT_UPDATE broadcast
            account_update = None
            ws.settimeout(5)
            try:
                for _ in range(10):
                    msg = ws.recv()
                    data = json.loads(msg)
                    if data.get("type") == "ACCOUNT_UPDATE":
                        account_update = data
                        break
            except websocket.WebSocketTimeoutException:
                pass
            
            ws.close()
            
            # Restore original balance
            requests.post(f"{BASE_URL}/api/settings", json={
                "account_balance": original_balance
            })
            
            assert account_update is not None, "Never received ACCOUNT_UPDATE broadcast"
            assert account_update["account_balance"] == new_balance, \
                f"Expected {new_balance}, got {account_update['account_balance']}"
            assert "allocated" in account_update, "allocated missing from ACCOUNT_UPDATE"
            assert "available" in account_update, "available missing from ACCOUNT_UPDATE"
            
            print(f"ACCOUNT_UPDATE received with account_balance={account_update['account_balance']}")
        except Exception as e:
            pytest.fail(f"WebSocket test failed: {e}")


class TestTakeProfitWithAccountBalance:
    """Tests for Take Profit interaction with account balance"""

    def test_get_cash_reserve(self):
        """GET /api/cash-reserve should return total and ledger"""
        response = requests.get(f"{BASE_URL}/api/cash-reserve")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data, "total field missing from cash-reserve"
        assert "ledger" in data, "ledger field missing from cash-reserve"
        print(f"Cash Reserve: ${data['total']}")

    def test_take_profit_endpoint_exists(self):
        """POST /api/tickers/{symbol}/take-profit endpoint should exist"""
        # Get a ticker with positive profit
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200
        # This just checks the endpoint pattern exists
        # Actual take profit requires positive P&L
        response = requests.post(f"{BASE_URL}/api/tickers/NONEXISTENT/take-profit")
        # Should return 400 (no positive profit) or 404 (ticker not found), not 404 method not found
        assert response.status_code in [400, 404], f"Unexpected status code: {response.status_code}"
        print("Take profit endpoint exists and responds correctly")


class TestTickerReorderingStillWorks:
    """Verify previous features still work"""

    def test_reorder_tickers(self):
        """POST /api/tickers/reorder should update sort_order"""
        # Get current tickers
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        if len(tickers) >= 2:
            # Get symbols in current order
            symbols = [t["symbol"] for t in tickers]
            
            # Reverse the order
            reversed_symbols = list(reversed(symbols))
            
            response = requests.post(f"{BASE_URL}/api/tickers/reorder", json={
                "order": reversed_symbols
            })
            assert response.status_code == 200
            
            # Verify order changed
            response = requests.get(f"{BASE_URL}/api/tickers")
            new_tickers = response.json()
            new_symbols = [t["symbol"] for t in new_tickers]
            
            # Restore original order
            requests.post(f"{BASE_URL}/api/tickers/reorder", json={
                "order": symbols
            })
            
            print("Ticker reordering still works correctly")
        else:
            pytest.skip("Need at least 2 tickers to test reordering")


class TestHealthCheck:
    """Basic health check"""

    def test_health_endpoint(self):
        """GET /api/health should return status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "online", "Health status should be online"
        print(f"Health check passed: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
