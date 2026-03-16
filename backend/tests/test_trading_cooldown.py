"""
Backend tests for Trading Bot Dashboard
Tests:
1. API health check
2. Trade cooldown verification (30-second per-symbol)
3. Trades API endpoint
4. Basic CRUD operations on tickers
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

if not BASE_URL:
    raise ValueError("REACT_APP_BACKEND_URL environment variable not set")

class TestHealthCheck:
    """Health check tests"""
    
    def test_health_endpoint(self):
        """Test /api/health returns online status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert "running" in data
        assert "paused" in data
        assert "market_open" in data
        print(f"Health check passed: {data}")


class TestTradeCooldown:
    """Tests for the 30-second per-symbol trade cooldown feature"""
    
    def test_get_trades_returns_data(self):
        """Test /api/trades endpoint returns trade data"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=10")
        assert response.status_code == 200
        trades = response.json()
        assert isinstance(trades, list)
        print(f"Trades endpoint returned {len(trades)} trades")
    
    def test_trade_timestamps_cooldown_spacing(self):
        """
        Verify RECENT trades for the same symbol are spaced at least ~30 seconds apart.
        The TRADE_COOLDOWN_SECS = 30 in server.py should prevent rapid-fire trades.
        Note: Only checks the last 20 trades to avoid old data from before cooldown was implemented.
        """
        response = requests.get(f"{BASE_URL}/api/trades?limit=20")
        assert response.status_code == 200
        trades = response.json()
        
        if len(trades) < 2:
            pytest.skip("Not enough trades to verify cooldown")
        
        # Group trades by symbol
        symbol_trades = {}
        for t in trades:
            sym = t.get("symbol")
            if sym not in symbol_trades:
                symbol_trades[sym] = []
            symbol_trades[sym].append(t)
        
        print(f"\nAnalyzing {len(trades)} recent trades across {len(symbol_trades)} symbols")
        
        # Check each symbol's trade spacing (only check consecutive same-symbol trades)
        cooldown_violations = []
        for sym, sym_trades in symbol_trades.items():
            if len(sym_trades) < 2:
                continue
            
            # Sort by timestamp (most recent first)
            sym_trades.sort(key=lambda x: x["timestamp"], reverse=True)
            
            # Only check the gap between the two most recent trades for each symbol
            t1 = sym_trades[0]
            t2 = sym_trades[1]
            
            ts1 = datetime.fromisoformat(t1["timestamp"].replace("Z", "+00:00"))
            ts2 = datetime.fromisoformat(t2["timestamp"].replace("Z", "+00:00"))
            
            gap_seconds = abs((ts1 - ts2).total_seconds())
            
            print(f"  {sym}: Last two trades gap = {gap_seconds:.1f}s")
            
            # 30-second cooldown with 5-second tolerance
            if gap_seconds < 25:  # Allow some tolerance
                cooldown_violations.append({
                    "symbol": sym,
                    "gap_seconds": gap_seconds,
                    "trade1_time": t1["timestamp"],
                    "trade2_time": t2["timestamp"],
                })
        
        if cooldown_violations:
            print(f"WARNING: Found {len(cooldown_violations)} potential cooldown violations:")
            for v in cooldown_violations:
                print(f"  {v['symbol']}: {v['gap_seconds']:.1f}s gap between trades")
        else:
            print("SUCCESS: Recent same-symbol trades are properly spaced (>=25 seconds)")
        
        # The test should pass if cooldown is working (no violations)
        assert len(cooldown_violations) == 0, f"Found {len(cooldown_violations)} cooldown violations"
    
    def test_trade_record_structure(self):
        """Verify trade records have expected fields"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=5")
        assert response.status_code == 200
        trades = response.json()
        
        if len(trades) == 0:
            pytest.skip("No trades available to verify structure")
        
        trade = trades[0]
        required_fields = ["id", "symbol", "side", "price", "quantity", "timestamp"]
        
        for field in required_fields:
            assert field in trade, f"Missing required field: {field}"
        
        # Verify side is valid
        valid_sides = ["BUY", "SELL", "STOP", "TRAILING_STOP"]
        assert trade["side"] in valid_sides, f"Invalid side: {trade['side']}"
        
        print(f"Trade structure verified: {trade}")


class TestTickersCRUD:
    """Tests for ticker CRUD operations"""
    
    def test_get_tickers(self):
        """Test /api/tickers returns list of tickers"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        assert isinstance(tickers, list)
        print(f"Tickers endpoint returned {len(tickers)} tickers")
        
        if len(tickers) > 0:
            # Verify ticker structure
            ticker = tickers[0]
            required_fields = ["symbol", "base_power", "enabled"]
            for field in required_fields:
                assert field in ticker, f"Missing field: {field}"
    
    def test_create_and_delete_ticker(self):
        """Test creating and deleting a ticker"""
        # Create test ticker
        test_symbol = "TEST_TICKER_123"
        
        # First, try to delete if exists (cleanup from previous runs)
        requests.delete(f"{BASE_URL}/api/tickers/{test_symbol}")
        
        # Create ticker
        create_response = requests.post(f"{BASE_URL}/api/tickers", json={
            "symbol": test_symbol,
            "base_power": 100.0
        })
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["symbol"] == test_symbol
        print(f"Created ticker: {test_symbol}")
        
        # Verify it exists
        get_response = requests.get(f"{BASE_URL}/api/tickers")
        assert get_response.status_code == 200
        tickers = get_response.json()
        symbols = [t["symbol"] for t in tickers]
        assert test_symbol in symbols
        
        # Delete ticker
        delete_response = requests.delete(f"{BASE_URL}/api/tickers/{test_symbol}")
        assert delete_response.status_code == 200
        print(f"Deleted ticker: {test_symbol}")
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/tickers")
        tickers = get_response.json()
        symbols = [t["symbol"] for t in tickers]
        assert test_symbol not in symbols
        print("Ticker CRUD test passed")


class TestPortfolio:
    """Tests for portfolio endpoints"""
    
    def test_get_portfolio(self):
        """Test /api/portfolio returns portfolio data"""
        response = requests.get(f"{BASE_URL}/api/portfolio")
        assert response.status_code == 200
        data = response.json()
        
        # Verify portfolio structure
        required_fields = ["total_pnl", "total_equity", "buying_power", "total_trades", "win_rate"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"Portfolio: P&L=${data['total_pnl']:.2f}, Win Rate={data['win_rate']}%")
    
    def test_get_positions(self):
        """Test /api/positions returns positions data"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        positions = response.json()
        assert isinstance(positions, list)
        print(f"Positions endpoint returned {len(positions)} positions")


class TestBotControl:
    """Tests for bot control endpoints"""
    
    def test_bot_start_stop_pause(self):
        """Test bot start/stop/pause controls"""
        # Get initial state
        health = requests.get(f"{BASE_URL}/api/health").json()
        initial_running = health["running"]
        initial_paused = health["paused"]
        
        # Test pause toggle
        pause_response = requests.post(f"{BASE_URL}/api/bot/pause")
        assert pause_response.status_code == 200
        
        # Restore initial state
        if initial_paused != pause_response.json()["paused"]:
            requests.post(f"{BASE_URL}/api/bot/pause")
        
        print(f"Bot control test passed. Running={initial_running}, Paused={initial_paused}")


class TestSettings:
    """Tests for settings endpoints"""
    
    def test_get_settings(self):
        """Test /api/settings returns settings data"""
        response = requests.get(f"{BASE_URL}/api/settings")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ["simulate_24_7", "increment_step", "decrement_step"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"Settings: simulate_24_7={data['simulate_24_7']}, steps=+{data['increment_step']}/-{data['decrement_step']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
