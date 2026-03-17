"""
Tests for Loss Log Feature:
1. _write_loss_log method creates proper .txt files
2. /api/loss-logs endpoint returns date folders with files
3. /api/loss-logs/{date}/{filename} returns plain text content
4. Log files contain all required metadata fields
5. Trailing stop losses include trail_high, trail_trigger, trail_value, trail_mode
"""
import pytest
import requests
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import time

# Add backend to path for direct imports
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
BACKEND_DIR = Path('/app/backend')
LOSS_LOGS_DIR = BACKEND_DIR / "trade_logs" / "losses"


class TestLossLogAPI:
    """Test the /api/loss-logs REST endpoints"""
    
    def test_loss_logs_list_endpoint_returns_200(self):
        """GET /api/loss-logs should return 200 with dates array"""
        response = requests.get(f"{BASE_URL}/api/loss-logs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "dates" in data, "Response should contain 'dates' key"
        assert isinstance(data["dates"], list), "dates should be a list"
        print(f"✓ Loss logs list endpoint returns 200 with {len(data['dates'])} date folders")
    
    def test_loss_log_file_endpoint_404_on_missing(self):
        """GET /api/loss-logs/{date}/{filename} should return 404 for missing files"""
        response = requests.get(f"{BASE_URL}/api/loss-logs/2099-01-01/nonexistent.txt")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Loss log file endpoint returns 404 for missing files")


class TestLossLogCreation:
    """Test loss log file creation by directly invoking _write_loss_log"""
    
    @pytest.fixture
    def cleanup_test_logs(self):
        """Clean up test-created log files after test"""
        test_files = []
        yield test_files
        # Cleanup
        for filepath in test_files:
            try:
                Path(filepath).unlink(missing_ok=True)
                print(f"  Cleaned up: {filepath}")
            except Exception as e:
                print(f"  Warning: Could not clean up {filepath}: {e}")
    
    def test_write_loss_log_creates_file(self, cleanup_test_logs):
        """_write_loss_log should create a .txt file with proper structure"""
        from server import TradeRecord, TradingEngine
        
        engine = TradingEngine()
        
        # Create a test loss trade
        test_trade = TradeRecord(
            id="TEST-LOSS-001",
            symbol="TESTLOSS",
            side="STOP",
            price=95.00,
            quantity=10.0,
            reason="[LMT] Stop-loss hit $95.00 <= $96.00",
            pnl=-50.00,
            timestamp=datetime.now(timezone.utc).isoformat(),
            order_type="LIMIT",
            rule_mode="PERCENT",
            entry_price=100.00,
            target_price=96.00,
            total_value=950.00,
            buy_power=1000.00,
            avg_price=98.50,
            sell_target=105.00,
            stop_target=96.00,
        )
        
        # Call the method
        engine._write_loss_log(test_trade)
        
        # Verify file was created
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_dir = LOSS_LOGS_DIR / today
        
        assert log_dir.exists(), f"Log directory {log_dir} should exist"
        
        # Find the test log file
        test_files = list(log_dir.glob("TESTLOSS_STOP_*_TEST-LOS*.txt"))
        assert len(test_files) >= 1, f"Should find at least 1 test log file, found {len(test_files)}"
        
        test_file = test_files[0]
        cleanup_test_logs.append(str(test_file))
        
        # Read and verify content
        content = test_file.read_text()
        
        # Verify required fields are present
        required_fields = [
            "Trade ID:",
            "Timestamp:",
            "Symbol:",
            "Side:",
            "Order Type:",
            "Rule Mode:",
            "Fill Price:",
            "Entry Price:",
            "Target Price:",
            "Avg Price",
            "Quantity:",
            "Total Value:",
            "Buy Power:",
            "Sell Target:",
            "Stop Target:",
            "P&L:",
            "% Change:",
            "REASON",
        ]
        
        for field in required_fields:
            assert field in content, f"Log file should contain '{field}'"
        
        # Verify specific values
        assert "TESTLOSS" in content
        assert "STOP" in content
        assert "$95.00" in content
        assert "$-50.00" in content or "-$50.00" in content
        assert "PERCENT" in content
        
        print(f"✓ Loss log file created at {test_file}")
        print(f"✓ All {len(required_fields)} required fields present in log")
    
    def test_write_loss_log_trailing_stop_includes_trail_fields(self, cleanup_test_logs):
        """Trailing stop loss logs should include trail_high, trail_trigger, trail_value, trail_mode"""
        from server import TradeRecord, TradingEngine
        
        engine = TradingEngine()
        
        # Create a trailing stop loss trade
        test_trade = TradeRecord(
            id="TEST-TRAIL-001",
            symbol="TESTTRAIL",
            side="TRAILING_STOP",
            price=92.00,
            quantity=10.0,
            reason="[LMT] Trailing stop hit $92.00 (high $100.00)",
            pnl=-30.00,
            timestamp=datetime.now(timezone.utc).isoformat(),
            order_type="LIMIT",
            rule_mode="PERCENT",
            entry_price=95.00,
            target_price=92.00,
            total_value=920.00,
            buy_power=1000.00,
            avg_price=97.00,
            sell_target=105.00,
            stop_target=90.00,
            trail_high=100.00,
            trail_trigger=92.00,
            trail_value=8.0,
            trail_mode="PERCENT",
        )
        
        # Call the method
        engine._write_loss_log(test_trade)
        
        # Find the test log file
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_dir = LOSS_LOGS_DIR / today
        test_files = list(log_dir.glob("TESTTRAIL_TRAILING_STOP_*_TEST-TRA*.txt"))
        assert len(test_files) >= 1, f"Should find trailing stop test log file"
        
        test_file = test_files[0]
        cleanup_test_logs.append(str(test_file))
        
        content = test_file.read_text()
        
        # Verify trailing stop specific fields
        trail_fields = [
            "TRAILING STOP DETAILS",
            "Trail High:",
            "Trail Trigger:",
            "Trail Value:",
            "Trail Mode:",
        ]
        
        for field in trail_fields:
            assert field in content, f"Trailing stop log should contain '{field}'"
        
        assert "$100.00" in content  # trail_high
        assert "$92.00" in content   # trail_trigger
        assert "PERCENT" in content  # trail_mode
        
        print(f"✓ Trailing stop loss log created at {test_file}")
        print("✓ All trailing stop specific fields present")


class TestLossLogAPIIntegration:
    """Test that created log files appear in API responses"""
    
    @pytest.fixture
    def create_test_log(self):
        """Create a test log file and clean up after"""
        from server import TradeRecord, TradingEngine
        
        engine = TradingEngine()
        test_id = f"APITEST-{int(time.time())}"
        
        test_trade = TradeRecord(
            id=test_id,
            symbol="APITEST",
            side="STOP",
            price=50.00,
            quantity=5.0,
            reason="API Integration Test",
            pnl=-25.00,
            timestamp=datetime.now(timezone.utc).isoformat(),
            order_type="MARKET",
            rule_mode="DOLLAR",
            entry_price=55.00,
            target_price=50.00,
            total_value=250.00,
            buy_power=500.00,
            avg_price=52.00,
            sell_target=60.00,
            stop_target=50.00,
        )
        
        engine._write_loss_log(test_trade)
        
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_dir = LOSS_LOGS_DIR / today
        test_files = list(log_dir.glob(f"APITEST_STOP_*_{test_id[:8]}*.txt"))
        
        filepath = test_files[0] if test_files else None
        yield {"date": today, "filepath": filepath, "filename": filepath.name if filepath else None}
        
        # Cleanup
        if filepath and filepath.exists():
            filepath.unlink()
            print(f"  Cleaned up: {filepath}")
    
    def test_api_list_includes_created_log(self, create_test_log):
        """GET /api/loss-logs should include newly created log date"""
        today = create_test_log["date"]
        
        response = requests.get(f"{BASE_URL}/api/loss-logs")
        assert response.status_code == 200
        
        data = response.json()
        date_entries = [d for d in data["dates"] if d["date"] == today]
        
        assert len(date_entries) >= 1, f"Should find entry for today ({today})"
        assert date_entries[0]["count"] >= 1, "Should have at least 1 file"
        
        print(f"✓ API includes today's date ({today}) with {date_entries[0]['count']} files")
    
    def test_api_get_file_content(self, create_test_log):
        """GET /api/loss-logs/{date}/{filename} should return file content"""
        date = create_test_log["date"]
        filename = create_test_log["filename"]
        
        assert filename, "Test log file should have been created"
        
        response = requests.get(f"{BASE_URL}/api/loss-logs/{date}/{filename}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers.get("content-type", "").startswith("text/plain")
        
        content = response.text
        assert "APITEST" in content
        assert "Trade ID:" in content
        assert "P&L:" in content
        
        print(f"✓ API returns plain text content for {date}/{filename}")
        print(f"  Content length: {len(content)} chars")


class TestTradesEndpointMetadata:
    """Verify /api/trades returns all metadata fields"""
    
    def test_trades_endpoint_returns_metadata_fields(self):
        """GET /api/trades should return trades with full metadata"""
        response = requests.get(f"{BASE_URL}/api/trades?limit=10")
        assert response.status_code == 200
        
        trades = response.json()
        assert len(trades) > 0, "Should have at least 1 trade"
        
        trade = trades[0]
        
        # Required fields as per the feature request
        required_fields = [
            "id", "symbol", "side", "price", "quantity", "timestamp",
            "order_type", "rule_mode", "entry_price", "target_price",
            "total_value", "buy_power", "avg_price", "sell_target", 
            "stop_target", "pnl",
        ]
        
        for field in required_fields:
            assert field in trade, f"Trade should have '{field}' field"
        
        print(f"✓ /api/trades returns all {len(required_fields)} required metadata fields")
        print(f"  Sample trade: {trade['side']} {trade['symbol']} @ ${trade['price']:.2f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
