"""
Tests for Limit/Market Order Type Feature
- Tests the 4 new order type fields: buy_order_type, sell_order_type, stop_order_type, trailing_order_type
- Tests API persistence and preset strategy backup/restore
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')


class TestOrderTypeAPI:
    """Tests for order type field persistence via REST API"""
    
    def test_health_endpoint(self):
        """Verify backend is running"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        print("Health endpoint OK")
    
    def test_get_tickers_includes_order_types(self):
        """Verify order type fields can be present in ticker response"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        assert len(tickers) > 0
        print(f"Found {len(tickers)} tickers")
        # Order types may not be present if not set yet (default is 'limit')
    
    def test_update_buy_order_type(self):
        """Test setting buy_order_type to market and back to limit"""
        # Set to market
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={"buy_order_type": "market"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["buy_order_type"] == "market"
        print("buy_order_type set to market")
        
        # Reset to limit
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={"buy_order_type": "limit"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["buy_order_type"] == "limit"
        print("buy_order_type reset to limit")
    
    def test_update_sell_order_type(self):
        """Test setting sell_order_type to market and back to limit"""
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={"sell_order_type": "market"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sell_order_type"] == "market"
        print("sell_order_type set to market")
        
        # Reset to limit
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={"sell_order_type": "limit"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sell_order_type"] == "limit"
        print("sell_order_type reset to limit")
    
    def test_update_stop_order_type(self):
        """Test setting stop_order_type to market and back to limit"""
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={"stop_order_type": "market"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stop_order_type"] == "market"
        print("stop_order_type set to market")
        
        # Reset to limit
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={"stop_order_type": "limit"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["stop_order_type"] == "limit"
        print("stop_order_type reset to limit")
    
    def test_update_trailing_order_type(self):
        """Test setting trailing_order_type to market and back to limit"""
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={"trailing_order_type": "market"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trailing_order_type"] == "market"
        print("trailing_order_type set to market")
        
        # Reset to limit
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={"trailing_order_type": "limit"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trailing_order_type"] == "limit"
        print("trailing_order_type reset to limit")
    
    def test_update_all_four_order_types(self):
        """Test setting all 4 order types in a single request"""
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={
                "buy_order_type": "market",
                "sell_order_type": "market",
                "stop_order_type": "market",
                "trailing_order_type": "market"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["buy_order_type"] == "market"
        assert data["sell_order_type"] == "market"
        assert data["stop_order_type"] == "market"
        assert data["trailing_order_type"] == "market"
        print("All 4 order types set to market")
        
        # Reset all to limit
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={
                "buy_order_type": "limit",
                "sell_order_type": "limit",
                "stop_order_type": "limit",
                "trailing_order_type": "limit"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["buy_order_type"] == "limit"
        assert data["sell_order_type"] == "limit"
        assert data["stop_order_type"] == "limit"
        assert data["trailing_order_type"] == "limit"
        print("All 4 order types reset to limit")


class TestOrderTypeTradeLabels:
    """Tests for [MKT] and [LMT] labels in trade history"""
    
    def test_trades_have_order_labels(self):
        """Verify trades contain [MKT] or [LMT] labels in reason field"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=50")
        assert response.status_code == 200
        trades = response.json()
        assert len(trades) > 0
        
        # Check for labels in trade reasons
        mkt_count = 0
        lmt_count = 0
        for trade in trades:
            reason = trade.get("reason", "")
            if "[MKT]" in reason:
                mkt_count += 1
            if "[LMT]" in reason:
                lmt_count += 1
        
        # At least one type of label should be present
        total_labeled = mkt_count + lmt_count
        print(f"Found {mkt_count} [MKT] trades and {lmt_count} [LMT] trades out of {len(trades)} total")
        assert total_labeled > 0, "No [MKT] or [LMT] labels found in trades"


class TestPresetStrategyOrderTypeBackup:
    """Tests for order type fields in preset strategy backup/restore"""
    
    def test_preset_strategy_saves_and_restores_order_types(self):
        """
        Test that order type fields are backed up when applying preset
        and restored when toggling off
        """
        # First, set a custom order type
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={"buy_order_type": "market"}
        )
        assert response.status_code == 200
        assert response.json()["buy_order_type"] == "market"
        print("Set buy_order_type to market for backup test")
        
        # Apply a preset strategy (should backup current settings)
        response = requests.post(
            f"{BASE_URL}/api/tickers/AAPL/strategy/conservative_1y"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "conservative_1y"
        # Check that custom_backup contains the order type
        backup = data.get("custom_backup", {})
        assert backup.get("buy_order_type") == "market", "buy_order_type not backed up"
        print(f"Preset applied, backup contains buy_order_type: {backup.get('buy_order_type')}")
        
        # Toggle off the preset (should restore custom settings)
        response = requests.post(
            f"{BASE_URL}/api/tickers/AAPL/strategy/conservative_1y"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "custom"
        assert data["buy_order_type"] == "market", "buy_order_type not restored from backup"
        print("Preset toggled off, buy_order_type restored to market")
        
        # Cleanup: reset to limit
        response = requests.put(
            f"{BASE_URL}/api/tickers/AAPL",
            json={"buy_order_type": "limit"}
        )
        assert response.status_code == 200
        print("Cleanup: reset buy_order_type to limit")


class TestGetStrategies:
    """Verify strategies endpoint returns preset configurations"""
    
    def test_strategies_endpoint(self):
        """Verify /api/strategies returns available presets"""
        response = requests.get(f"{BASE_URL}/api/strategies")
        assert response.status_code == 200
        data = response.json()
        assert "conservative_1y" in data
        assert "aggressive_monthly" in data
        assert "swing_trader" in data
        print(f"Found {len(data)} preset strategies")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
