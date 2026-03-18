"""
Test the Manual Sell feature: Market Sell, Limit Sell, Pending Sells, and Cancel Pending.
Tests POST /positions/{symbol}/sell, GET /positions/pending-sells, DELETE /positions/{symbol}/pending-sell
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestManualSellFeature:
    """Test manual sell endpoints for positions tab"""
    
    def test_01_get_positions(self):
        """GET /api/positions - Verify positions endpoint returns data structure"""
        response = requests.get(f"{BASE_URL}/api/positions")
        assert response.status_code == 200
        positions = response.json()
        assert isinstance(positions, list)
        # If positions exist, validate structure
        if len(positions) > 0:
            pos = positions[0]
            assert "symbol" in pos
            assert "quantity" in pos
            assert "avg_entry" in pos
            assert "current_price" in pos
            assert "market_value" in pos
            assert "unrealized_pnl" in pos
            print(f"Found {len(positions)} positions: {[p['symbol'] for p in positions]}")
        else:
            print("No positions found - engine may have sold them all")
    
    def test_02_get_pending_sells(self):
        """GET /api/positions/pending-sells - Verify pending sells endpoint works"""
        response = requests.get(f"{BASE_URL}/api/positions/pending-sells")
        assert response.status_code == 200
        pending = response.json()
        assert isinstance(pending, dict)
        print(f"Pending sells: {pending}")
    
    def test_03_sell_nonexistent_position_returns_400(self):
        """POST /api/positions/NONEXISTENT/sell - Should return 400 for non-existent position"""
        response = requests.post(
            f"{BASE_URL}/api/positions/NONEXISTENT/sell",
            json={"order_type": "market"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        print(f"Non-existent position error: {data['detail']}")
    
    def test_04_limit_sell_requires_price(self):
        """POST /api/positions/{symbol}/sell - Limit order without price returns 400"""
        # Get positions first
        pos_response = requests.get(f"{BASE_URL}/api/positions")
        positions = pos_response.json()
        if len(positions) == 0:
            pytest.skip("No positions available to test limit sell validation")
        
        symbol = positions[0]["symbol"]
        response = requests.post(
            f"{BASE_URL}/api/positions/{symbol}/sell",
            json={"order_type": "limit"}  # Missing limit_price
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "limit_price" in data["detail"].lower()
        print(f"Limit price validation: {data['detail']}")
    
    def test_05_invalid_order_type_returns_400(self):
        """POST /api/positions/{symbol}/sell - Invalid order type returns 400"""
        pos_response = requests.get(f"{BASE_URL}/api/positions")
        positions = pos_response.json()
        if len(positions) == 0:
            pytest.skip("No positions available to test")
        
        symbol = positions[0]["symbol"]
        response = requests.post(
            f"{BASE_URL}/api/positions/{symbol}/sell",
            json={"order_type": "invalid_type"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        print(f"Invalid order type error: {data['detail']}")
    
    def test_06_limit_sell_creates_pending(self):
        """POST /api/positions/{symbol}/sell with limit - Creates pending limit sell"""
        pos_response = requests.get(f"{BASE_URL}/api/positions")
        positions = pos_response.json()
        if len(positions) == 0:
            pytest.skip("No positions available for limit sell test")
        
        # Find a position to place limit sell
        position = positions[0]
        symbol = position["symbol"]
        current_price = position["current_price"]
        # Set limit price higher than current (unlikely to execute)
        limit_price = round(current_price * 1.5, 2)  # 50% above current
        
        response = requests.post(
            f"{BASE_URL}/api/positions/{symbol}/sell",
            json={"order_type": "limit", "limit_price": limit_price}
        )
        
        # Either 200 for success or 400 if position was sold by engine
        if response.status_code == 400:
            print(f"Position {symbol} was sold by engine before test could place limit sell")
            pytest.skip("Position no longer available")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["order_type"] == "limit"
        assert data["symbol"] == symbol
        assert data["limit_price"] == limit_price
        assert "quantity" in data
        print(f"Created pending limit sell: {symbol} @ ${limit_price}")
        
        # Verify it appears in pending sells
        pending_response = requests.get(f"{BASE_URL}/api/positions/pending-sells")
        pending = pending_response.json()
        assert symbol in pending
        assert pending[symbol]["limit_price"] == limit_price
        print(f"Verified in pending sells: {pending[symbol]}")
    
    def test_07_cancel_pending_sell(self):
        """DELETE /api/positions/{symbol}/pending-sell - Cancel pending limit sell"""
        # First check if there are any pending sells
        pending_response = requests.get(f"{BASE_URL}/api/positions/pending-sells")
        pending = pending_response.json()
        
        if len(pending) == 0:
            # Try to create one first
            pos_response = requests.get(f"{BASE_URL}/api/positions")
            positions = pos_response.json()
            if len(positions) == 0:
                pytest.skip("No positions to create pending sell")
            
            symbol = positions[0]["symbol"]
            limit_price = round(positions[0]["current_price"] * 1.5, 2)
            create_response = requests.post(
                f"{BASE_URL}/api/positions/{symbol}/sell",
                json={"order_type": "limit", "limit_price": limit_price}
            )
            if create_response.status_code != 200:
                pytest.skip("Could not create pending sell to cancel")
            print(f"Created pending sell for {symbol}")
        else:
            symbol = list(pending.keys())[0]
        
        # Now cancel it
        cancel_response = requests.delete(f"{BASE_URL}/api/positions/{symbol}/pending-sell")
        assert cancel_response.status_code == 200
        data = cancel_response.json()
        assert data["status"] == "cancelled"
        assert data["symbol"] == symbol
        print(f"Cancelled pending sell for {symbol}")
        
        # Verify it's removed from pending
        verify_response = requests.get(f"{BASE_URL}/api/positions/pending-sells")
        verify_pending = verify_response.json()
        assert symbol not in verify_pending
        print("Verified pending sell removed")
    
    def test_08_cancel_nonexistent_pending_sell(self):
        """DELETE /api/positions/{symbol}/pending-sell - Cancel non-existent returns 400"""
        response = requests.delete(f"{BASE_URL}/api/positions/NOTPENDING/pending-sell")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        print(f"Non-existent pending sell error: {data['detail']}")
    
    def test_09_market_sell_executes_immediately(self):
        """POST /api/positions/{symbol}/sell with market - Executes immediately"""
        # Wait a bit for engine to potentially create new positions
        time.sleep(2)
        
        pos_response = requests.get(f"{BASE_URL}/api/positions")
        positions = pos_response.json()
        if len(positions) == 0:
            pytest.skip("No positions available for market sell test - engine is actively trading")
        
        position = positions[0]
        symbol = position["symbol"]
        quantity = position["quantity"]
        
        print(f"Attempting market sell of {symbol} ({quantity} shares)")
        
        response = requests.post(
            f"{BASE_URL}/api/positions/{symbol}/sell",
            json={"order_type": "market"}
        )
        
        # Position might be sold by engine before we can
        if response.status_code == 400:
            data = response.json()
            print(f"Position sold by engine: {data['detail']}")
            pytest.skip("Position was sold by engine")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure for executed market sell
        assert data["status"] == "executed"
        assert data["order_type"] == "market"
        assert data["symbol"] == symbol
        assert "price" in data
        assert "quantity" in data
        assert "pnl" in data
        assert "total_value" in data
        assert "trading_mode" in data
        
        print(f"Market sell executed: {symbol} @ ${data['price']:.2f}")
        print(f"  Quantity: {data['quantity']:.4f}")
        print(f"  P&L: ${data['pnl']:.2f}")
        print(f"  Total Value: ${data['total_value']:.2f}")
        print(f"  Trading Mode: {data['trading_mode']}")
        
        # Verify position is removed
        verify_response = requests.get(f"{BASE_URL}/api/positions")
        remaining = verify_response.json()
        remaining_symbols = [p["symbol"] for p in remaining]
        assert symbol not in remaining_symbols, "Position should be removed after market sell"
        print(f"Verified position {symbol} removed")


class TestMarketSellResponseStructure:
    """Verify the response structure of market sell matches expected format"""
    
    def test_market_sell_response_fields(self):
        """Verify all required fields in market sell response"""
        pos_response = requests.get(f"{BASE_URL}/api/positions")
        positions = pos_response.json()
        if len(positions) == 0:
            pytest.skip("No positions for response validation")
        
        position = positions[0]
        response = requests.post(
            f"{BASE_URL}/api/positions/{position['symbol']}/sell",
            json={"order_type": "market"}
        )
        
        if response.status_code == 400:
            pytest.skip("Position sold by engine")
        
        data = response.json()
        
        # Required fields as per spec
        required_fields = ["status", "symbol", "order_type", "price", "quantity", "pnl", "total_value", "trading_mode"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        assert data["status"] == "executed"
        assert isinstance(data["price"], (int, float))
        assert isinstance(data["quantity"], (int, float))
        assert isinstance(data["pnl"], (int, float))
        print(f"Market sell response structure validated")


class TestLimitSellResponseStructure:
    """Verify the response structure of limit sell matches expected format"""
    
    def test_limit_sell_response_fields(self):
        """Verify all required fields in limit sell response"""
        # Wait for engine to create positions
        time.sleep(3)
        
        pos_response = requests.get(f"{BASE_URL}/api/positions")
        positions = pos_response.json()
        if len(positions) == 0:
            pytest.skip("No positions for response validation")
        
        position = positions[0]
        limit_price = round(position["current_price"] * 1.5, 2)
        
        response = requests.post(
            f"{BASE_URL}/api/positions/{position['symbol']}/sell",
            json={"order_type": "limit", "limit_price": limit_price}
        )
        
        if response.status_code == 400:
            pytest.skip("Position sold by engine")
        
        data = response.json()
        
        # Required fields for pending limit sell
        required_fields = ["status", "symbol", "order_type", "limit_price", "quantity"]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        assert data["status"] == "pending"
        assert data["order_type"] == "limit"
        assert data["limit_price"] == limit_price
        print(f"Limit sell response structure validated")
        
        # Clean up - cancel the pending sell
        requests.delete(f"{BASE_URL}/api/positions/{position['symbol']}/pending-sell")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
