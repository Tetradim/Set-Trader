"""
Test suite for new features:
1. Live Price Chart (via priceHistory in frontend store)
2. Preset Strategy Toggle (backup/restore custom config)
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndBasics:
    """Health check and basic API tests"""
    
    def test_health_endpoint(self):
        """Verify backend is running and healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        print(f"Backend status: {data}")
    
    def test_tickers_endpoint(self):
        """Verify tickers endpoint returns data"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        assert isinstance(tickers, list)
        assert len(tickers) > 0
        print(f"Found {len(tickers)} tickers")
        
        # Verify expected ticker fields exist
        for ticker in tickers:
            assert "symbol" in ticker
            assert "buy_offset" in ticker
            assert "sell_offset" in ticker
            assert "strategy" in ticker


class TestPresetStrategyToggle:
    """Test preset strategy toggle feature - backup and restore custom config"""
    
    @pytest.fixture
    def test_ticker(self):
        """Get a test ticker symbol that exists"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        # Prefer AAPL or first available ticker
        for t in tickers:
            if t["symbol"] == "AAPL":
                return "AAPL"
        return tickers[0]["symbol"] if tickers else None
    
    def test_apply_preset_conservative_1y(self, test_ticker):
        """Test applying Conservative 1Y preset changes values correctly"""
        if not test_ticker:
            pytest.skip("No tickers available")
        
        # First, get current state
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = {t["symbol"]: t for t in response.json()}
        original = tickers.get(test_ticker)
        assert original is not None
        
        original_strategy = original.get("strategy")
        original_buy_offset = original.get("buy_offset")
        original_avg_days = original.get("avg_days")
        print(f"Original state: strategy={original_strategy}, buy_offset={original_buy_offset}, avg_days={original_avg_days}")
        
        # If already on conservative_1y, toggle OFF first to reset
        if original_strategy == "conservative_1y":
            response = requests.post(f"{BASE_URL}/api/tickers/{test_ticker}/strategy/conservative_1y")
            assert response.status_code == 200
            time.sleep(0.5)
            # Re-fetch original state
            response = requests.get(f"{BASE_URL}/api/tickers")
            tickers = {t["symbol"]: t for t in response.json()}
            original = tickers.get(test_ticker)
            original_buy_offset = original.get("buy_offset")
            original_avg_days = original.get("avg_days")
        
        # Apply Conservative 1Y preset
        response = requests.post(f"{BASE_URL}/api/tickers/{test_ticker}/strategy/conservative_1y")
        assert response.status_code == 200
        data = response.json()
        
        # Verify preset values were applied
        assert data["strategy"] == "conservative_1y"
        assert data["buy_offset"] == -5.0, f"Expected buy_offset=-5.0, got {data['buy_offset']}"
        assert data["avg_days"] == 365, f"Expected avg_days=365, got {data['avg_days']}"
        assert data["sell_offset"] == 8.0
        assert data["stop_offset"] == -10.0
        assert data["trailing_enabled"] == False
        
        # Verify custom_backup was saved
        assert "custom_backup" in data
        assert data["custom_backup"] is not None
        print(f"Preset applied: strategy={data['strategy']}, custom_backup keys={list(data['custom_backup'].keys())}")
    
    def test_toggle_off_preset_restores_custom(self, test_ticker):
        """Test toggling off preset restores previous custom values"""
        if not test_ticker:
            pytest.skip("No tickers available")
        
        # First ensure we're in a clean state - get current
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = {t["symbol"]: t for t in response.json()}
        original = tickers.get(test_ticker)
        
        # If NOT on conservative_1y, apply it first
        if original.get("strategy") != "conservative_1y":
            # Save original values
            saved_buy_offset = original.get("buy_offset")
            saved_avg_days = original.get("avg_days")
            print(f"Saving original: buy_offset={saved_buy_offset}, avg_days={saved_avg_days}")
            
            # Apply preset
            response = requests.post(f"{BASE_URL}/api/tickers/{test_ticker}/strategy/conservative_1y")
            assert response.status_code == 200
            data = response.json()
            assert data["strategy"] == "conservative_1y"
            print(f"Applied preset, custom_backup={data.get('custom_backup')}")
            time.sleep(0.5)
        else:
            # Already on preset, get backup values
            saved_buy_offset = original.get("custom_backup", {}).get("buy_offset")
            saved_avg_days = original.get("custom_backup", {}).get("avg_days")
            print(f"Already on preset, backup values: buy_offset={saved_buy_offset}, avg_days={saved_avg_days}")
        
        # Now toggle OFF by clicking same preset
        response = requests.post(f"{BASE_URL}/api/tickers/{test_ticker}/strategy/conservative_1y")
        assert response.status_code == 200
        data = response.json()
        
        # Verify strategy is now "custom"
        assert data["strategy"] == "custom", f"Expected strategy=custom, got {data['strategy']}"
        
        # Verify custom_backup is cleared
        assert data.get("custom_backup") is None, "custom_backup should be None after toggle off"
        
        # Verify values were restored (if we had backup values)
        if saved_buy_offset is not None:
            assert data["buy_offset"] == saved_buy_offset, f"Expected buy_offset={saved_buy_offset}, got {data['buy_offset']}"
        if saved_avg_days is not None:
            assert data["avg_days"] == saved_avg_days, f"Expected avg_days={saved_avg_days}, got {data['avg_days']}"
        
        print(f"Toggled off: strategy={data['strategy']}, buy_offset={data['buy_offset']}, avg_days={data['avg_days']}")
    
    def test_full_toggle_cycle(self, test_ticker):
        """Complete cycle: custom -> preset -> custom (with value verification)"""
        if not test_ticker:
            pytest.skip("No tickers available")
        
        # Step 1: Ensure clean custom state by toggling off any preset
        response = requests.get(f"{BASE_URL}/api/tickers")
        tickers = {t["symbol"]: t for t in response.json()}
        ticker = tickers.get(test_ticker)
        
        # If on a preset, toggle it off first
        current_strategy = ticker.get("strategy", "custom")
        if current_strategy != "custom":
            response = requests.post(f"{BASE_URL}/api/tickers/{test_ticker}/strategy/{current_strategy}")
            assert response.status_code == 200
            time.sleep(0.5)
            response = requests.get(f"{BASE_URL}/api/tickers")
            tickers = {t["symbol"]: t for t in response.json()}
            ticker = tickers.get(test_ticker)
        
        # Record custom values BEFORE applying preset
        custom_buy_offset = ticker.get("buy_offset")
        custom_avg_days = ticker.get("avg_days")
        custom_sell_offset = ticker.get("sell_offset")
        custom_stop_offset = ticker.get("stop_offset")
        custom_trailing_enabled = ticker.get("trailing_enabled")
        print(f"Step 1 - Custom state: buy={custom_buy_offset}, avg_days={custom_avg_days}, sell={custom_sell_offset}")
        
        # Step 2: Apply Aggressive Monthly preset
        response = requests.post(f"{BASE_URL}/api/tickers/{test_ticker}/strategy/aggressive_monthly")
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "aggressive_monthly"
        assert data["buy_offset"] == -2.0
        assert data["avg_days"] == 30
        assert data["sell_offset"] == 4.0
        assert data["trailing_enabled"] == True
        print(f"Step 2 - Preset applied: strategy=aggressive_monthly, buy={data['buy_offset']}, sell={data['sell_offset']}")
        
        # Step 3: Toggle OFF aggressive_monthly
        response = requests.post(f"{BASE_URL}/api/tickers/{test_ticker}/strategy/aggressive_monthly")
        assert response.status_code == 200
        data = response.json()
        
        # Verify custom values are restored
        assert data["strategy"] == "custom"
        assert data["buy_offset"] == custom_buy_offset, f"buy_offset not restored: {data['buy_offset']} != {custom_buy_offset}"
        assert data["avg_days"] == custom_avg_days, f"avg_days not restored: {data['avg_days']} != {custom_avg_days}"
        assert data["sell_offset"] == custom_sell_offset, f"sell_offset not restored: {data['sell_offset']} != {custom_sell_offset}"
        assert data.get("custom_backup") is None
        print(f"Step 3 - Restored: strategy=custom, buy={data['buy_offset']}, avg_days={data['avg_days']}, sell={data['sell_offset']}")
        
        print("SUCCESS: Full toggle cycle completed with correct backup/restore")


class TestStrategiesEndpoint:
    """Test strategies metadata endpoint"""
    
    def test_get_all_strategies(self):
        """Verify all preset strategies are available"""
        response = requests.get(f"{BASE_URL}/api/strategies")
        assert response.status_code == 200
        strategies = response.json()
        
        # Verify expected strategies exist
        expected = ["conservative_1y", "aggressive_monthly", "swing_trader"]
        for strategy_id in expected:
            assert strategy_id in strategies, f"Missing strategy: {strategy_id}"
            s = strategies[strategy_id]
            assert "avg_days" in s
            assert "buy_offset" in s
            assert "sell_offset" in s
            print(f"Strategy {strategy_id}: avg_days={s['avg_days']}, buy={s['buy_offset']}, sell={s['sell_offset']}")


class TestPortfolioAndTrades:
    """Test portfolio and trades endpoints"""
    
    def test_portfolio_endpoint(self):
        """Verify portfolio endpoint returns correct structure"""
        response = requests.get(f"{BASE_URL}/api/portfolio")
        assert response.status_code == 200
        data = response.json()
        
        # Verify expected fields
        assert "total_pnl" in data
        assert "total_equity" in data
        assert "buying_power" in data
        assert "positions" in data
        assert "profits_by_symbol" in data
        print(f"Portfolio: P&L=${data['total_pnl']:.2f}, equity=${data['total_equity']:.2f}")
    
    def test_trades_endpoint(self):
        """Verify trades endpoint returns trade history"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=10")
        assert response.status_code == 200
        trades = response.json()
        assert isinstance(trades, list)
        
        if trades:
            trade = trades[0]
            assert "symbol" in trade
            assert "side" in trade
            assert "price" in trade
            assert "quantity" in trade
            print(f"Latest trade: {trade['side']} {trade['symbol']} @ ${trade['price']:.2f}")
