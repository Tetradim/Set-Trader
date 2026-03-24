"""
Test suite for Partial Fills (Scale In / Scale Out) feature.
Tests:
- GET /api/tickers - SPY should have partial_fills_enabled, buy_legs, sell_legs
- PUT /api/tickers/SPY - toggle partial_fills_enabled
- PUT /api/tickers/SPY - save custom buy_legs and sell_legs
- PUT /api/tickers/TSLA - save single-leg config
- GET /api/tickers/TSLA - verify partial fill fields persisted
- Backend schema validation for TradeRecord trading_mode and broker_results
- TradingEngine._evaluate_partial_fills method existence
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestPartialFillsAPI:
    """Test partial fills API endpoints"""
    
    def test_health_check(self):
        """Verify API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health check passed")
    
    def test_get_tickers_returns_partial_fills_fields(self):
        """GET /api/tickers should return partial_fills_enabled, buy_legs, sell_legs for each ticker"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        assert isinstance(tickers, list)
        assert len(tickers) > 0
        
        # Check that all tickers have partial fills fields
        for ticker in tickers:
            assert 'partial_fills_enabled' in ticker, f"Missing partial_fills_enabled for {ticker.get('symbol')}"
            assert 'buy_legs' in ticker, f"Missing buy_legs for {ticker.get('symbol')}"
            assert 'sell_legs' in ticker, f"Missing sell_legs for {ticker.get('symbol')}"
            print(f"✓ {ticker['symbol']}: partial_fills_enabled={ticker['partial_fills_enabled']}, buy_legs={len(ticker['buy_legs'])}, sell_legs={len(ticker['sell_legs'])}")
        
        print(f"✓ All {len(tickers)} tickers have partial fills fields")
    
    def test_spy_has_partial_fills_configured(self):
        """SPY should have partial_fills_enabled=true with 3 buy legs and 2 sell legs"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        spy = next((t for t in tickers if t['symbol'] == 'SPY'), None)
        if spy is None:
            pytest.skip("SPY ticker not found - may need to be created first")
        
        # Check SPY has partial fills enabled
        assert spy.get('partial_fills_enabled') == True, f"SPY partial_fills_enabled should be True, got {spy.get('partial_fills_enabled')}"
        
        # Check buy legs
        buy_legs = spy.get('buy_legs', [])
        assert len(buy_legs) == 3, f"SPY should have 3 buy legs, got {len(buy_legs)}"
        
        # Check sell legs
        sell_legs = spy.get('sell_legs', [])
        assert len(sell_legs) == 2, f"SPY should have 2 sell legs, got {len(sell_legs)}"
        
        # Validate leg structure
        for i, leg in enumerate(buy_legs):
            assert 'alloc_pct' in leg, f"Buy leg {i} missing alloc_pct"
            assert 'offset' in leg, f"Buy leg {i} missing offset"
            assert 'is_percent' in leg, f"Buy leg {i} missing is_percent"
            print(f"✓ Buy leg {i+1}: alloc_pct={leg['alloc_pct']}, offset={leg['offset']}, is_percent={leg['is_percent']}")
        
        for i, leg in enumerate(sell_legs):
            assert 'alloc_pct' in leg, f"Sell leg {i} missing alloc_pct"
            assert 'offset' in leg, f"Sell leg {i} missing offset"
            assert 'is_percent' in leg, f"Sell leg {i} missing is_percent"
            print(f"✓ Sell leg {i+1}: alloc_pct={leg['alloc_pct']}, offset={leg['offset']}, is_percent={leg['is_percent']}")
        
        print("✓ SPY has correct partial fills configuration")
    
    def test_disable_partial_fills_for_spy(self):
        """PUT /api/tickers/SPY with partial_fills_enabled=false should disable partial fills"""
        # First get current state
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        spy = next((t for t in tickers if t['symbol'] == 'SPY'), None)
        if spy is None:
            pytest.skip("SPY ticker not found")
        
        original_state = spy.get('partial_fills_enabled', False)
        
        # Disable partial fills
        response = requests.put(f"{BASE_URL}/api/tickers/SPY", json={
            "partial_fills_enabled": False
        })
        assert response.status_code == 200
        updated = response.json()
        assert updated['partial_fills_enabled'] == False, f"Expected partial_fills_enabled=False, got {updated['partial_fills_enabled']}"
        print("✓ Disabled partial fills for SPY")
        
        # Verify via GET
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        spy = next((t for t in tickers if t['symbol'] == 'SPY'), None)
        assert spy['partial_fills_enabled'] == False
        print("✓ Verified partial_fills_enabled=False persisted")
        
        # Restore original state
        response = requests.put(f"{BASE_URL}/api/tickers/SPY", json={
            "partial_fills_enabled": original_state
        })
        assert response.status_code == 200
        print(f"✓ Restored SPY partial_fills_enabled to {original_state}")
    
    def test_enable_partial_fills_with_custom_legs(self):
        """PUT /api/tickers/SPY with partial_fills_enabled=true and custom legs should save config"""
        # First get current state to restore later
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        spy = next((t for t in tickers if t['symbol'] == 'SPY'), None)
        if spy is None:
            pytest.skip("SPY ticker not found")
        
        original_buy_legs = spy.get('buy_legs', [])
        original_sell_legs = spy.get('sell_legs', [])
        original_enabled = spy.get('partial_fills_enabled', False)
        
        # Update with custom legs
        custom_buy_legs = [
            {"alloc_pct": 40, "offset": -2.0, "is_percent": True},
            {"alloc_pct": 35, "offset": -4.0, "is_percent": True},
            {"alloc_pct": 25, "offset": -6.0, "is_percent": True}
        ]
        custom_sell_legs = [
            {"alloc_pct": 60, "offset": 2.5, "is_percent": True},
            {"alloc_pct": 40, "offset": 5.0, "is_percent": True}
        ]
        
        response = requests.put(f"{BASE_URL}/api/tickers/SPY", json={
            "partial_fills_enabled": True,
            "buy_legs": custom_buy_legs,
            "sell_legs": custom_sell_legs
        })
        assert response.status_code == 200
        updated = response.json()
        
        # Verify response
        assert updated['partial_fills_enabled'] == True
        assert len(updated['buy_legs']) == 3
        assert len(updated['sell_legs']) == 2
        assert updated['buy_legs'][0]['alloc_pct'] == 40
        assert updated['sell_legs'][0]['alloc_pct'] == 60
        print("✓ Updated SPY with custom partial fills config")
        
        # Verify via GET
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        spy = next((t for t in tickers if t['symbol'] == 'SPY'), None)
        assert spy['partial_fills_enabled'] == True
        assert spy['buy_legs'][0]['alloc_pct'] == 40
        print("✓ Verified custom legs persisted")
        
        # Restore original state
        response = requests.put(f"{BASE_URL}/api/tickers/SPY", json={
            "partial_fills_enabled": original_enabled,
            "buy_legs": original_buy_legs,
            "sell_legs": original_sell_legs
        })
        assert response.status_code == 200
        print("✓ Restored SPY to original state")
    
    def test_tsla_single_leg_config(self):
        """PUT /api/tickers/TSLA with single-leg partial fills config"""
        # First check if TSLA exists
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        tsla = next((t for t in tickers if t['symbol'] == 'TSLA'), None)
        
        if tsla is None:
            # Create TSLA if it doesn't exist
            response = requests.post(f"{BASE_URL}/api/tickers", json={
                "symbol": "TSLA",
                "base_power": 100.0
            })
            if response.status_code == 400:
                # Already exists, just continue
                pass
            else:
                assert response.status_code == 200
        
        # Get current state
        response = requests.get(f"{BASE_URL}/api/tickers")
        tickers = response.json()
        tsla = next((t for t in tickers if t['symbol'] == 'TSLA'), None)
        original_enabled = tsla.get('partial_fills_enabled', False)
        original_buy_legs = tsla.get('buy_legs', [])
        original_sell_legs = tsla.get('sell_legs', [])
        
        # Update with single-leg config
        single_buy_leg = [{"alloc_pct": 100, "offset": -2, "is_percent": True}]
        single_sell_leg = [{"alloc_pct": 100, "offset": 5, "is_percent": True}]
        
        response = requests.put(f"{BASE_URL}/api/tickers/TSLA", json={
            "partial_fills_enabled": True,
            "buy_legs": single_buy_leg,
            "sell_legs": single_sell_leg
        })
        assert response.status_code == 200
        updated = response.json()
        
        # Verify response
        assert updated['partial_fills_enabled'] == True
        assert len(updated['buy_legs']) == 1
        assert len(updated['sell_legs']) == 1
        assert updated['buy_legs'][0]['alloc_pct'] == 100
        assert updated['buy_legs'][0]['offset'] == -2
        assert updated['buy_legs'][0]['is_percent'] == True
        assert updated['sell_legs'][0]['alloc_pct'] == 100
        assert updated['sell_legs'][0]['offset'] == 5
        assert updated['sell_legs'][0]['is_percent'] == True
        print("✓ Updated TSLA with single-leg partial fills config")
        
        # Verify via GET
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        tsla = next((t for t in tickers if t['symbol'] == 'TSLA'), None)
        assert tsla['partial_fills_enabled'] == True
        assert len(tsla['buy_legs']) == 1
        assert len(tsla['sell_legs']) == 1
        print("✓ Verified TSLA single-leg config persisted")
        
        # Restore original state
        response = requests.put(f"{BASE_URL}/api/tickers/TSLA", json={
            "partial_fills_enabled": original_enabled,
            "buy_legs": original_buy_legs,
            "sell_legs": original_sell_legs
        })
        assert response.status_code == 200
        print("✓ Restored TSLA to original state")
    
    def test_partial_fills_with_dollar_offset(self):
        """Test partial fills with is_percent=false (dollar offset)"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        # Use first available ticker
        if not tickers:
            pytest.skip("No tickers available")
        
        ticker = tickers[0]
        symbol = ticker['symbol']
        original_enabled = ticker.get('partial_fills_enabled', False)
        original_buy_legs = ticker.get('buy_legs', [])
        original_sell_legs = ticker.get('sell_legs', [])
        
        # Update with dollar offset legs
        dollar_buy_legs = [{"alloc_pct": 50, "offset": 450.0, "is_percent": False}]
        dollar_sell_legs = [{"alloc_pct": 50, "offset": 500.0, "is_percent": False}]
        
        response = requests.put(f"{BASE_URL}/api/tickers/{symbol}", json={
            "partial_fills_enabled": True,
            "buy_legs": dollar_buy_legs,
            "sell_legs": dollar_sell_legs
        })
        assert response.status_code == 200
        updated = response.json()
        
        # Verify dollar offset saved correctly
        assert updated['buy_legs'][0]['is_percent'] == False
        assert updated['buy_legs'][0]['offset'] == 450.0
        assert updated['sell_legs'][0]['is_percent'] == False
        assert updated['sell_legs'][0]['offset'] == 500.0
        print(f"✓ {symbol} saved with dollar offset legs")
        
        # Restore original state
        response = requests.put(f"{BASE_URL}/api/tickers/{symbol}", json={
            "partial_fills_enabled": original_enabled,
            "buy_legs": original_buy_legs,
            "sell_legs": original_sell_legs
        })
        assert response.status_code == 200
        print(f"✓ Restored {symbol} to original state")
    
    def test_empty_legs_array(self):
        """Test that empty legs arrays are handled correctly"""
        response = requests.get(f"{BASE_URL}/api/tickers")
        assert response.status_code == 200
        tickers = response.json()
        
        if not tickers:
            pytest.skip("No tickers available")
        
        ticker = tickers[0]
        symbol = ticker['symbol']
        original_enabled = ticker.get('partial_fills_enabled', False)
        original_buy_legs = ticker.get('buy_legs', [])
        original_sell_legs = ticker.get('sell_legs', [])
        
        # Update with empty legs
        response = requests.put(f"{BASE_URL}/api/tickers/{symbol}", json={
            "partial_fills_enabled": True,
            "buy_legs": [],
            "sell_legs": []
        })
        assert response.status_code == 200
        updated = response.json()
        
        # Verify empty arrays saved
        assert updated['buy_legs'] == []
        assert updated['sell_legs'] == []
        print(f"✓ {symbol} saved with empty legs arrays")
        
        # Restore original state
        response = requests.put(f"{BASE_URL}/api/tickers/{symbol}", json={
            "partial_fills_enabled": original_enabled,
            "buy_legs": original_buy_legs,
            "sell_legs": original_sell_legs
        })
        assert response.status_code == 200
        print(f"✓ Restored {symbol} to original state")


class TestTradeRecordSchema:
    """Test TradeRecord schema has trading_mode and broker_results fields"""
    
    def test_trades_have_trading_mode_field(self):
        """GET /api/trades should return trades with trading_mode field"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        trades = response.json()
        
        if not trades:
            pytest.skip("No trades available to verify schema")
        
        # Check first few trades have trading_mode
        for trade in trades[:5]:
            assert 'trading_mode' in trade, f"Trade {trade.get('id')} missing trading_mode field"
            assert trade['trading_mode'] in ['paper', 'live'], f"Invalid trading_mode: {trade['trading_mode']}"
            print(f"✓ Trade {trade['id'][:8]}... has trading_mode={trade['trading_mode']}")
        
        print(f"✓ Verified trading_mode field in {min(5, len(trades))} trades")
    
    def test_trades_have_broker_results_field(self):
        """GET /api/trades should return trades with broker_results field"""
        response = requests.get(f"{BASE_URL}/api/trades")
        assert response.status_code == 200
        trades = response.json()
        
        if not trades:
            pytest.skip("No trades available to verify schema")
        
        # Check first few trades have broker_results
        for trade in trades[:5]:
            assert 'broker_results' in trade, f"Trade {trade.get('id')} missing broker_results field"
            assert isinstance(trade['broker_results'], list), f"broker_results should be a list"
            print(f"✓ Trade {trade['id'][:8]}... has broker_results (count: {len(trade['broker_results'])})")
        
        print(f"✓ Verified broker_results field in {min(5, len(trades))} trades")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
