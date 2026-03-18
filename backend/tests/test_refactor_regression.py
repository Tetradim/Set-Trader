"""
Regression Tests for Sentinel Pulse Refactoring
Tests all API endpoints after the monolithic server.py was split into 12+ modules.
Verifies API contracts are preserved after the refactoring.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthEndpoint:
    """Test /api/health endpoint"""
    
    def test_health_returns_expected_fields(self):
        """GET /api/health - returns status, trading_mode, brokers_connected fields"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        
        data = response.json()
        # Required fields
        assert "status" in data
        assert data["status"] == "online"
        assert "trading_mode" in data
        assert data["trading_mode"] in ["paper", "live"]
        assert "brokers_connected" in data
        assert isinstance(data["brokers_connected"], int)
        assert "running" in data
        assert "paused" in data
        assert "market_open" in data
        print(f"Health endpoint working: trading_mode={data['trading_mode']}, brokers_connected={data['brokers_connected']}")


class TestSettingsEndpoint:
    """Test /api/settings endpoint"""
    
    def test_get_settings_returns_expected_fields(self):
        """GET /api/settings - returns simulate_24_7, trading_mode, telegram, account_balance"""
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200
        
        data = response.json()
        # Required fields
        assert "simulate_24_7" in data
        assert isinstance(data["simulate_24_7"], bool)
        assert "trading_mode" in data
        assert data["trading_mode"] in ["paper", "live"]
        assert "telegram" in data
        assert "account_balance" in data
        assert isinstance(data["account_balance"], (int, float))
        print(f"Settings endpoint working: simulate_24_7={data['simulate_24_7']}, account_balance={data['account_balance']}")
    
    def test_post_settings_toggle_simulate_24_7(self):
        """POST /api/settings with {simulate_24_7: false} - toggles mode"""
        # Get current state
        get_resp = requests.get(f"{BASE_URL}/api/settings")
        current_state = get_resp.json()["simulate_24_7"]
        
        # Toggle to opposite
        new_state = not current_state
        response = requests.post(f"{BASE_URL}/api/settings", json={"simulate_24_7": new_state})
        assert response.status_code == 200
        
        # Verify change
        verify_resp = requests.get(f"{BASE_URL}/api/settings")
        assert verify_resp.json()["simulate_24_7"] == new_state
        expected_mode = "paper" if new_state else "live"
        assert verify_resp.json()["trading_mode"] == expected_mode
        
        # Toggle back to original
        restore_resp = requests.post(f"{BASE_URL}/api/settings", json={"simulate_24_7": current_state})
        assert restore_resp.status_code == 200
        print(f"Settings toggle working: toggled to {new_state}, restored to {current_state}")


class TestTickersEndpoint:
    """Test /api/tickers CRUD endpoints"""
    
    def test_get_tickers_returns_list(self):
        """GET /api/tickers - returns list of tickers with broker_ids"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            ticker = data[0]
            assert "symbol" in ticker
            assert "base_power" in ticker
            # broker_ids should be present (broker_allocations is optional)
            assert "broker_ids" in ticker
            assert isinstance(ticker["broker_ids"], list)
        print(f"Tickers endpoint working: {len(data)} tickers found")
    
    def test_ticker_crud_operations(self):
        """Test POST, PUT, DELETE /api/tickers"""
        test_symbol = "TESTGOOG"
        
        # Cleanup first if exists
        requests.delete(f"{BASE_URL}/api/tickers/{test_symbol}")
        
        # CREATE
        create_resp = requests.post(f"{BASE_URL}/api/tickers", json={"symbol": test_symbol, "base_power": 150.0})
        assert create_resp.status_code == 200
        created = create_resp.json()
        assert created["symbol"] == test_symbol
        assert created["base_power"] == 150.0
        print(f"Created ticker: {test_symbol}")
        
        # GET to verify
        get_resp = requests.get(f"{BASE_URL}/api/tickers")
        tickers = get_resp.json()
        found = any(t["symbol"] == test_symbol for t in tickers)
        assert found, f"Ticker {test_symbol} not found after creation"
        
        # UPDATE
        update_resp = requests.put(f"{BASE_URL}/api/tickers/{test_symbol}", json={"base_power": 200.0})
        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["base_power"] == 200.0
        print(f"Updated ticker: {test_symbol} base_power to 200")
        
        # DELETE
        delete_resp = requests.delete(f"{BASE_URL}/api/tickers/{test_symbol}")
        assert delete_resp.status_code == 200
        deleted = delete_resp.json()
        assert deleted["deleted"] == test_symbol
        print(f"Deleted ticker: {test_symbol}")
        
        # Verify deletion
        get_after_delete = requests.get(f"{BASE_URL}/api/tickers")
        tickers_after = get_after_delete.json()
        still_exists = any(t["symbol"] == test_symbol for t in tickers_after)
        assert not still_exists, f"Ticker {test_symbol} still exists after deletion"


class TestBrokersEndpoint:
    """Test /api/brokers endpoints"""
    
    def test_get_brokers_returns_10_brokers(self):
        """GET /api/brokers - returns 10 brokers"""
        response = requests.get(f"{BASE_URL}/api/brokers")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 10, f"Expected 10 brokers, got {len(data)}"
        
        # Verify each broker has required fields
        for broker in data:
            assert "id" in broker
            assert "name" in broker
            assert "description" in broker
            assert "supported" in broker
            assert "auth_fields" in broker
        print(f"Brokers endpoint working: {len(data)} brokers found")
    
    def test_get_brokers_status(self):
        """GET /api/brokers/status - returns connection status for all 10 brokers"""
        response = requests.get(f"{BASE_URL}/api/brokers/status")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict)
        # Should have status for brokers
        print(f"Broker status endpoint working: {len(data)} broker statuses")
    
    def test_post_brokers_reconnect(self):
        """POST /api/brokers/reconnect - returns results dict"""
        response = requests.post(f"{BASE_URL}/api/brokers/reconnect")
        assert response.status_code == 200
        
        data = response.json()
        assert "results" in data
        print(f"Broker reconnect endpoint working: {data}")
    
    def test_get_single_broker(self):
        """GET /api/brokers/alpaca - returns single broker info"""
        response = requests.get(f"{BASE_URL}/api/brokers/alpaca")
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == "alpaca"
        assert data["name"] == "Alpaca"
        assert "auth_fields" in data
        print(f"Single broker endpoint working: alpaca")


class TestTradesEndpoint:
    """Test /api/trades endpoints"""
    
    def test_get_trades_with_limit(self):
        """GET /api/trades?limit=5 - returns recent trades with trading_mode field"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5
        
        # If there are trades, verify they have required fields
        if len(data) > 0:
            trade = data[0]
            assert "symbol" in trade
            assert "side" in trade
            assert "price" in trade
            assert "quantity" in trade
            assert "trading_mode" in trade, "Trade record should have trading_mode field"
        print(f"Trades endpoint working: {len(data)} trades returned")


class TestPortfolioEndpoint:
    """Test /api/portfolio endpoint"""
    
    def test_get_portfolio(self):
        """GET /api/portfolio - returns P&L, positions, win_rate"""
        response = requests.get(f"{BASE_URL}/api/portfolio")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_pnl" in data
        assert "positions" in data
        assert "win_rate" in data
        assert isinstance(data["positions"], list)
        print(f"Portfolio endpoint working: total_pnl={data['total_pnl']}, win_rate={data['win_rate']}")


class TestPositionsEndpoint:
    """Test /api/positions endpoint"""
    
    def test_get_positions(self):
        """GET /api/positions - returns open positions"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        # If positions exist, verify structure
        if len(data) > 0:
            pos = data[0]
            assert "symbol" in pos
            assert "quantity" in pos
            assert "avg_entry" in pos
        print(f"Positions endpoint working: {len(data)} positions")


class TestStrategiesEndpoint:
    """Test /api/strategies endpoint"""
    
    def test_get_strategies_returns_3_presets(self):
        """GET /api/strategies - returns 3 preset strategies"""
        response = requests.get(f"{BASE_URL}/api/strategies")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, dict)
        assert len(data) == 3, f"Expected 3 preset strategies, got {len(data)}"
        
        # Verify strategy structure
        for name, strategy in data.items():
            assert "name" in strategy
            assert "avg_days" in strategy
            assert "buy_offset" in strategy
            assert "sell_offset" in strategy
        print(f"Strategies endpoint working: {list(data.keys())}")


class TestMetricsEndpoint:
    """Test /api/metrics endpoint"""
    
    def test_get_metrics_returns_prometheus_format(self):
        """GET /api/metrics - returns Prometheus text format"""
        response = requests.get(f"{BASE_URL}/api/metrics")
        assert response.status_code == 200
        
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type
        
        text = response.text
        assert "sentinel_pulse_up" in text
        assert "sentinel_pulse_paused" in text
        assert "sentinel_pulse_market_open" in text
        print(f"Metrics endpoint working: {len(text)} bytes of Prometheus metrics")


class TestTracesEndpoint:
    """Test /api/traces endpoint"""
    
    def test_get_traces_returns_spans(self):
        """GET /api/traces - returns OpenTelemetry spans"""
        response = requests.get(f"{BASE_URL}/api/traces")
        assert response.status_code == 200
        
        data = response.json()
        assert "count" in data
        assert "spans" in data
        assert isinstance(data["spans"], list)
        print(f"Traces endpoint working: {data['count']} spans")


class TestBotEndpoint:
    """Test /api/bot endpoints"""
    
    def test_bot_start(self):
        """POST /api/bot/start - starts the bot"""
        response = requests.post(f"{BASE_URL}/api/bot/start")
        assert response.status_code == 200
        
        data = response.json()
        assert "running" in data
        assert data["running"] == True
        print("Bot start endpoint working")
    
    def test_bot_stop(self):
        """POST /api/bot/stop - stops the bot"""
        response = requests.post(f"{BASE_URL}/api/bot/stop")
        assert response.status_code == 200
        
        data = response.json()
        assert "running" in data
        assert data["running"] == False
        print("Bot stop endpoint working")
        
        # Restart bot for other tests
        requests.post(f"{BASE_URL}/api/bot/start")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
