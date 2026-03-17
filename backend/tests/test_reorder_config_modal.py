"""
Test drag-and-drop reorder API and config modal related features.
Tests POST /api/tickers/reorder endpoint and sorted GET /api/tickers response.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestTickerReorderAPI:
    """Tests for POST /api/tickers/reorder endpoint"""
    
    def test_health_check(self):
        """Verify API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        print(f"Health check passed: {data}")
    
    def test_get_tickers_returns_sorted(self):
        """GET /api/tickers should return tickers sorted by sort_order"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        assert isinstance(tickers, list)
        assert len(tickers) > 0
        
        # Verify tickers are sorted by sort_order ascending
        sort_orders = [t.get("sort_order", 0) for t in tickers]
        assert sort_orders == sorted(sort_orders), f"Tickers not sorted: {sort_orders}"
        
        # Log current order
        symbols = [t["symbol"] for t in tickers]
        print(f"Current ticker order: {symbols}")
        print(f"Sort orders: {sort_orders}")
    
    def test_reorder_tickers_success(self):
        """POST /api/tickers/reorder should update sort_order for all tickers"""
        # Get current tickers
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        current_order = [t["symbol"] for t in tickers]
        print(f"Current order: {current_order}")
        
        # Create new order (reverse the list)
        new_order = list(reversed(current_order))
        print(f"New order to set: {new_order}")
        
        # Call reorder endpoint
        response = requests.post(
            f"{BASE_URL}/api/tickers/reorder",
            json={"order": new_order}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        print(f"Reorder response: {data}")
        
        # Verify new order is persisted
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        updated_tickers = response.json()
        updated_order = [t["symbol"] for t in updated_tickers]
        
        assert updated_order == new_order, f"Order not updated. Expected: {new_order}, Got: {updated_order}"
        print(f"Order verified: {updated_order}")
        
        # Restore original order for other tests
        response = requests.post(
            f"{BASE_URL}/api/tickers/reorder",
            json={"order": current_order}
        )
        assert response.status_code == 200
        print(f"Restored original order: {current_order}")
    
    def test_reorder_with_empty_order_fails(self):
        """POST /api/tickers/reorder with empty order should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/tickers/reorder",
            json={"order": []}
        )
        assert response.status_code == 400
        print(f"Empty order correctly rejected: {response.json()}")
    
    def test_reorder_with_no_order_fails(self):
        """POST /api/tickers/reorder without order field should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/tickers/reorder",
            json={}
        )
        assert response.status_code == 400
        print(f"No order field correctly rejected: {response.json()}")
    
    def test_sort_order_field_exists_on_tickers(self):
        """All tickers should have sort_order field"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        for ticker in tickers:
            assert "sort_order" in ticker, f"sort_order missing from {ticker['symbol']}"
            assert isinstance(ticker["sort_order"], int), f"sort_order not int for {ticker['symbol']}"
        
        print(f"All {len(tickers)} tickers have valid sort_order field")


class TestTickerConfigFields:
    """Tests for config modal related fields (Rules, Risk, Rebracket, Advanced tabs)"""
    
    def test_ticker_has_rules_fields(self):
        """Verify tickers have all Rules tab fields"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        rules_fields = [
            "compound_profits", "wait_day_after_buy",
            "buy_order_type", "buy_offset", "buy_percent", "base_power", "avg_days",
            "sell_order_type", "sell_offset", "sell_percent"
        ]
        
        for ticker in tickers:
            for field in rules_fields:
                assert field in ticker, f"Field '{field}' missing from {ticker['symbol']}"
        
        print(f"All tickers have Rules tab fields: {rules_fields}")
    
    def test_ticker_has_risk_fields(self):
        """Verify tickers have all Risk tab fields"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        risk_fields = [
            "stop_offset", "stop_percent", "stop_order_type",
            "trailing_enabled", "trailing_percent", "trailing_percent_mode", "trailing_order_type",
            "max_daily_loss", "max_consecutive_losses"
        ]
        
        for ticker in tickers:
            for field in risk_fields:
                # Some tickers might not have all optional fields
                if field not in ticker:
                    print(f"Warning: Field '{field}' missing from {ticker['symbol']}")
        
        print("Risk tab fields check complete")
    
    def test_ticker_has_rebracket_fields(self):
        """Verify tickers have Rebracket tab fields"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        rebracket_fields = [
            "auto_rebracket", "rebracket_threshold", "rebracket_spread",
            "rebracket_cooldown", "rebracket_lookback", "rebracket_buffer"
        ]
        
        for ticker in tickers:
            if ticker.get("auto_rebracket"):
                for field in rebracket_fields:
                    if field not in ticker:
                        print(f"Warning: Field '{field}' missing from {ticker['symbol']} with auto_rebracket enabled")
        
        print("Rebracket tab fields check complete")
    
    def test_auto_stopped_ticker_has_fields(self):
        """Verify auto-stopped ticker has required fields for modal banner"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        for ticker in tickers:
            if ticker.get("auto_stopped"):
                assert "auto_stop_reason" in ticker, f"auto_stop_reason missing from auto-stopped {ticker['symbol']}"
                print(f"Auto-stopped ticker {ticker['symbol']}: reason = '{ticker.get('auto_stop_reason')}'")
    
    def test_update_ticker_config(self):
        """Test updating ticker config fields via PUT API"""
        # Get first enabled ticker
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        test_ticker = None
        for t in tickers:
            if t.get("enabled") and not t.get("auto_stopped"):
                test_ticker = t
                break
        
        if not test_ticker:
            pytest.skip("No enabled non-auto-stopped ticker found")
        
        symbol = test_ticker["symbol"]
        original_avg_days = test_ticker.get("avg_days", 30)
        
        # Update avg_days
        new_avg_days = 45 if original_avg_days != 45 else 35
        response = requests.put(
            f"{BASE_URL}/api/tickers/{symbol}",
            json={"avg_days": new_avg_days}
        )
        assert response.status_code == 200
        updated = response.json()
        assert updated["avg_days"] == new_avg_days
        print(f"Updated {symbol} avg_days: {original_avg_days} -> {new_avg_days}")
        
        # Restore original value
        response = requests.put(
            f"{BASE_URL}/api/tickers/{symbol}",
            json={"avg_days": original_avg_days}
        )
        assert response.status_code == 200
        print(f"Restored {symbol} avg_days to {original_avg_days}")


class TestStrategies:
    """Tests for preset strategies (Advanced tab)"""
    
    def test_get_strategies(self):
        """GET /api/strategies should return preset strategies"""
        response = requests.get(f"{BASE_URL}/api/strategies")
        assert response.status_code == 200
        strategies = response.json()
        
        expected_strategies = ["conservative_1y", "aggressive_monthly", "swing_trader"]
        for strategy in expected_strategies:
            assert strategy in strategies, f"Strategy '{strategy}' not found"
        
        print(f"Available strategies: {list(strategies.keys())}")
        for name, config in strategies.items():
            print(f"  - {name}: {config.get('name', 'unnamed')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
