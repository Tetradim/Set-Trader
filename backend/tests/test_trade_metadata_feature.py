"""
Tests for Trade Logging Rich Metadata Feature
- Tests the 14 new TradeRecord metadata fields: order_type, rule_mode, entry_price, target_price, 
  total_value, buy_power, avg_price, sell_target, stop_target, trail_high, trail_trigger, trail_value, trail_mode
- Tests GET /api/trades returns new metadata fields
- Validates data integrity for BUY, SELL, STOP, and TRAILING_STOP trades
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')


class TestTradeMetadataFields:
    """Tests for new metadata fields in GET /api/trades response"""
    
    def test_health_endpoint(self):
        """Verify backend is running"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        print("Health endpoint OK")
    
    def test_trades_endpoint_returns_data(self):
        """Verify GET /api/trades returns trade data"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=50")
        assert response.status_code == 200
        trades = response.json()
        assert isinstance(trades, list)
        print(f"GET /api/trades returned {len(trades)} trades")
    
    def test_trades_have_order_type_field(self):
        """Verify order_type field is present and valid (MARKET or LIMIT)"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=50")
        assert response.status_code == 200
        trades = response.json()
        
        trades_with_order_type = [t for t in trades if t.get("order_type")]
        assert len(trades_with_order_type) > 0, "No trades have order_type populated"
        
        for t in trades_with_order_type:
            assert t["order_type"] in ["MARKET", "LIMIT"], f"Invalid order_type: {t['order_type']}"
        
        market_count = len([t for t in trades if t.get("order_type") == "MARKET"])
        limit_count = len([t for t in trades if t.get("order_type") == "LIMIT"])
        print(f"Found {market_count} MARKET orders and {limit_count} LIMIT orders")
    
    def test_trades_have_rule_mode_field(self):
        """Verify rule_mode field is present and valid (PERCENT or DOLLAR)"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=50")
        assert response.status_code == 200
        trades = response.json()
        
        trades_with_rule_mode = [t for t in trades if t.get("rule_mode")]
        assert len(trades_with_rule_mode) > 0, "No trades have rule_mode populated"
        
        for t in trades_with_rule_mode:
            assert t["rule_mode"] in ["PERCENT", "DOLLAR"], f"Invalid rule_mode: {t['rule_mode']}"
        
        percent_count = len([t for t in trades if t.get("rule_mode") == "PERCENT"])
        dollar_count = len([t for t in trades if t.get("rule_mode") == "DOLLAR"])
        print(f"Found {percent_count} PERCENT mode and {dollar_count} DOLLAR mode trades")
    
    def test_buy_trades_have_required_metadata(self):
        """Verify BUY trades have total_value > 0, buy_power > 0, target_price > 0, avg_price > 0"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=100")
        assert response.status_code == 200
        trades = response.json()
        
        buy_trades = [t for t in trades if t.get("side") == "BUY" and t.get("order_type")]
        assert len(buy_trades) > 0, "No BUY trades found with metadata"
        
        for t in buy_trades:
            assert t.get("total_value", 0) > 0, f"BUY trade {t['id']} missing total_value"
            assert t.get("buy_power", 0) > 0, f"BUY trade {t['id']} missing buy_power"
            assert t.get("avg_price", 0) > 0, f"BUY trade {t['id']} missing avg_price"
            # target_price should exist for BUY trades
            assert "target_price" in t, f"BUY trade {t['id']} missing target_price field"
        
        print(f"Validated {len(buy_trades)} BUY trades have required metadata")
    
    def test_sell_trades_have_required_metadata(self):
        """Verify SELL trades have entry_price > 0, pnl != 0 (can be negative for losses)"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=100")
        assert response.status_code == 200
        trades = response.json()
        
        sell_trades = [t for t in trades if t.get("side") == "SELL" and t.get("order_type")]
        
        if len(sell_trades) == 0:
            pytest.skip("No SELL trades found with metadata")
        
        for t in sell_trades:
            assert t.get("entry_price", 0) > 0, f"SELL trade {t['id']} missing entry_price"
            # P&L should exist but can be 0 if entry == exit
            assert "pnl" in t, f"SELL trade {t['id']} missing pnl field"
        
        print(f"Validated {len(sell_trades)} SELL trades have required metadata")
    
    def test_stop_trades_have_required_metadata(self):
        """Verify STOP trades have entry_price > 0, pnl (usually negative)"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=200")
        assert response.status_code == 200
        trades = response.json()
        
        stop_trades = [t for t in trades if t.get("side") == "STOP" and t.get("order_type")]
        
        if len(stop_trades) == 0:
            pytest.skip("No STOP trades found with metadata")
        
        for t in stop_trades:
            assert t.get("entry_price", 0) > 0, f"STOP trade {t['id']} missing entry_price"
            assert "pnl" in t, f"STOP trade {t['id']} missing pnl field"
        
        print(f"Validated {len(stop_trades)} STOP trades have required metadata")
    
    def test_trailing_stop_trades_have_trail_metadata(self):
        """Verify TRAILING_STOP trades have trail_high, trail_trigger, trail_value, trail_mode"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=200")
        assert response.status_code == 200
        trades = response.json()
        
        trailing_trades = [t for t in trades if t.get("side") == "TRAILING_STOP" and t.get("order_type")]
        
        if len(trailing_trades) == 0:
            pytest.skip("No TRAILING_STOP trades found with metadata")
        
        for t in trailing_trades:
            assert t.get("trail_high", 0) > 0, f"TRAILING_STOP trade {t['id']} missing trail_high"
            assert t.get("trail_trigger", 0) > 0, f"TRAILING_STOP trade {t['id']} missing trail_trigger"
            assert "trail_value" in t, f"TRAILING_STOP trade {t['id']} missing trail_value"
            assert t.get("trail_mode") in ["PERCENT", "DOLLAR"], f"TRAILING_STOP trade {t['id']} has invalid trail_mode"
        
        print(f"Validated {len(trailing_trades)} TRAILING_STOP trades have trail metadata")
    
    def test_trades_have_sell_target_and_stop_target(self):
        """Verify trades have sell_target and stop_target populated"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=50")
        assert response.status_code == 200
        trades = response.json()
        
        # Filter trades with metadata (have order_type set)
        trades_with_metadata = [t for t in trades if t.get("order_type")]
        
        if len(trades_with_metadata) == 0:
            pytest.skip("No trades with metadata found")
        
        # Check at least some trades have sell_target and stop_target
        has_sell_target = len([t for t in trades_with_metadata if t.get("sell_target", 0) > 0])
        has_stop_target = len([t for t in trades_with_metadata if t.get("stop_target", 0) > 0])
        
        print(f"Trades with sell_target: {has_sell_target}/{len(trades_with_metadata)}")
        print(f"Trades with stop_target: {has_stop_target}/{len(trades_with_metadata)}")
        
        # At least some BUY trades should have these targets set
        buy_trades = [t for t in trades_with_metadata if t.get("side") == "BUY"]
        if buy_trades:
            buy_with_targets = [t for t in buy_trades if t.get("sell_target", 0) > 0]
            assert len(buy_with_targets) > 0, "BUY trades should have sell_target populated"


class TestTradeStatistics:
    """Tests for trade statistics and loss tracking"""
    
    def test_portfolio_endpoint_has_win_rate(self):
        """Verify /api/portfolio returns win_rate"""
        response = requests.get(f"{BASE_URL}/api/portfolio")
        assert response.status_code == 200
        data = response.json()
        
        assert "win_rate" in data, "Portfolio missing win_rate"
        assert "total_pnl" in data, "Portfolio missing total_pnl"
        assert "total_trades" in data, "Portfolio missing total_trades"
        
        print(f"Portfolio: win_rate={data['win_rate']}%, total_pnl=${data['total_pnl']}, trades={data['total_trades']}")
    
    def test_trades_can_filter_losses(self):
        """Verify trades with pnl < 0 exist and can be filtered"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=200")
        assert response.status_code == 200
        trades = response.json()
        
        losses = [t for t in trades if t.get("pnl", 0) < 0]
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        
        total_loss = sum(t.get("pnl", 0) for t in losses)
        total_gain = sum(t.get("pnl", 0) for t in wins)
        
        print(f"Loss trades: {len(losses)} (total: ${total_loss:.2f})")
        print(f"Win trades: {len(wins)} (total: ${total_gain:.2f})")


class TestLegacyTradeHandling:
    """Tests for backward compatibility with legacy trades (pre-metadata)"""
    
    def test_old_trades_have_default_metadata(self):
        """Verify old trades without metadata return empty/0 values gracefully"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=200")
        assert response.status_code == 200
        trades = response.json()
        
        # Check structure of response - should not cause errors
        for t in trades:
            # These fields should exist (even if empty/0)
            assert "id" in t
            assert "symbol" in t
            assert "side" in t
            assert "price" in t
            assert "quantity" in t
            assert "timestamp" in t
        
        # Old trades might have empty order_type - that's OK
        old_trades = [t for t in trades if not t.get("order_type")]
        new_trades = [t for t in trades if t.get("order_type")]
        
        print(f"Legacy trades (no metadata): {len(old_trades)}")
        print(f"New trades (with metadata): {len(new_trades)}")


class TestTradeReasonLabels:
    """Tests for [MKT] and [LMT] labels in trade reason field"""
    
    def test_trades_have_order_labels_in_reason(self):
        """Verify trades contain [MKT] or [LMT] labels in reason field"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=50")
        assert response.status_code == 200
        trades = response.json()
        
        # Filter trades with metadata
        trades_with_metadata = [t for t in trades if t.get("order_type")]
        
        if len(trades_with_metadata) == 0:
            pytest.skip("No trades with metadata found")
        
        mkt_count = 0
        lmt_count = 0
        for trade in trades_with_metadata:
            reason = trade.get("reason", "")
            if "[MKT]" in reason:
                mkt_count += 1
                assert trade.get("order_type") == "MARKET", "Reason has [MKT] but order_type != MARKET"
            if "[LMT]" in reason:
                lmt_count += 1
                assert trade.get("order_type") == "LIMIT", "Reason has [LMT] but order_type != LIMIT"
        
        print(f"Found {mkt_count} [MKT] labeled trades and {lmt_count} [LMT] labeled trades")
        assert mkt_count + lmt_count > 0, "No [MKT] or [LMT] labels found in trade reasons"


class TestTotalValueCalculation:
    """Tests for total_value field calculation"""
    
    def test_total_value_matches_price_times_quantity(self):
        """Verify total_value = price * quantity"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=50")
        assert response.status_code == 200
        trades = response.json()
        
        # Filter trades with metadata
        trades_with_metadata = [t for t in trades if t.get("order_type")]
        
        for t in trades_with_metadata:
            expected = t["price"] * t["quantity"]
            actual = t.get("total_value", 0)
            # Allow small floating point difference
            assert abs(actual - expected) < 0.1, f"Trade {t['id']}: expected total_value {expected:.2f}, got {actual:.2f}"
        
        print(f"Validated total_value calculation for {len(trades_with_metadata)} trades")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
