#!/usr/bin/env python3
import requests
import json
import sys
from datetime import datetime

class BracketBotAPITester:
    def __init__(self, base_url="https://pulse-engine-1.preview.emergentagent.com"):
        self.base_url = base_url
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_result(self, test_name, success, details="", expected_status=None, actual_status=None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name}")
            if expected_status and actual_status:
                print(f"   Expected: {expected_status}, Got: {actual_status}")
            if details:
                print(f"   Details: {details}")
        
        self.test_results.append({
            "test": test_name,
            "status": "PASS" if success else "FAIL", 
            "details": details
        })
        return success

    def run_test(self, name, method, endpoint, expected_status=200, data=None):
        """Run a single API test"""
        url = f"{self.base_url}/api{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)

            success = response.status_code == expected_status
            
            if success:
                try:
                    response_data = response.json()
                    return self.log_result(name, True), response_data
                except:
                    return self.log_result(name, True), {}
            else:
                error_details = f"Expected {expected_status}, got {response.status_code}"
                try:
                    error_data = response.json()
                    error_details += f" - {error_data}"
                except:
                    error_details += f" - {response.text[:200]}"
                return self.log_result(name, False, error_details, expected_status, response.status_code), {}

        except Exception as e:
            return self.log_result(name, False, f"Exception: {str(e)}"), {}

    def test_health_endpoint(self):
        """Test /api/health endpoint"""
        print("\n🔍 Testing Health Endpoint...")
        success, data = self.run_test("Health Check", "GET", "/health")
        if success and data:
            self.log_result("Health - Status Field", "status" in data, f"Status: {data.get('status', 'missing')}")
            self.log_result("Health - Running Field", "running" in data, f"Running: {data.get('running', 'missing')}")
            self.log_result("Health - Market Open Field", "market_open" in data, f"Market Open: {data.get('market_open', 'missing')}")
            
            # SPECIFIC TESTS for review request items
            running_value = data.get('running')
            paused_value = data.get('paused') 
            market_open_value = data.get('market_open')
            
            self.log_result("Health - Bot Running True", running_value == True, f"Running: {running_value}")
            self.log_result("Health - Bot Not Paused", paused_value == False, f"Paused: {paused_value}")
            self.log_result("Health - Market Open (simulate_24_7)", market_open_value == True, f"Market Open: {market_open_value}")
            
            # Test telegram field in health endpoint
            self.log_result("Health - Telegram Field", "telegram" in data, f"Telegram: {data.get('telegram', 'missing')}")
            telegram_value = data.get('telegram')
            self.log_result("Health - Telegram Boolean", isinstance(telegram_value, bool), f"Telegram type: {type(telegram_value)}")
        return success

    def test_tickers_crud(self):
        """Test tickers CRUD operations"""
        print("\n🔍 Testing Tickers CRUD...")
        
        # Get initial tickers
        success, initial_tickers = self.run_test("Get Tickers", "GET", "/tickers")
        if success:
            seeded_symbols = [t.get("symbol") for t in initial_tickers if isinstance(initial_tickers, list)]
            expected_symbols = ["TSLA", "AAPL", "NVDA"]
            has_seeded = all(sym in seeded_symbols for sym in expected_symbols)
            self.log_result("Seeded Tickers Present", has_seeded, f"Found: {seeded_symbols}")

        # Test adding new ticker
        test_ticker = {"symbol": "GOOGL", "base_power": 150.0}
        success, ticker_data = self.run_test("Add New Ticker", "POST", "/tickers", 200, test_ticker)
        
        ticker_id = None
        if success and ticker_data:
            self.log_result("New Ticker - Symbol Field", ticker_data.get("symbol") == "GOOGL")
            self.log_result("New Ticker - Base Power Field", ticker_data.get("base_power") == 150.0)
            ticker_id = ticker_data.get("id")

        # Test updating ticker (using TSLA which should exist)
        update_data = {"base_power": 200.0, "enabled": False}
        success, updated_ticker = self.run_test("Update Ticker TSLA", "PUT", "/tickers/TSLA", 200, update_data)
        if success and updated_ticker:
            self.log_result("Updated Ticker - Base Power", updated_ticker.get("base_power") == 200.0)
            self.log_result("Updated Ticker - Enabled", updated_ticker.get("enabled") == False)

        # Test deleting the test ticker we added
        if ticker_id:
            success, _ = self.run_test("Delete Test Ticker", "DELETE", "/tickers/GOOGL", 200)

        return True

    def test_strategies_endpoint(self):
        """Test /api/strategies endpoint"""
        print("\n🔍 Testing Strategies Endpoint...")
        success, data = self.run_test("Get Strategies", "GET", "/strategies")
        if success and data:
            expected_strategies = ["conservative_1y", "aggressive_monthly", "swing_trader"]
            found_strategies = list(data.keys()) if isinstance(data, dict) else []
            has_preset_strategies = all(strat in found_strategies for strat in expected_strategies)
            self.log_result("Preset Strategies Present", has_preset_strategies, f"Found: {found_strategies}")
        return success

    def test_portfolio_endpoint(self):
        """Test /api/portfolio endpoint"""
        print("\n🔍 Testing Portfolio Endpoint...")
        success, data = self.run_test("Get Portfolio", "GET", "/portfolio")
        if success and data:
            required_fields = ["total_pnl", "total_equity", "buying_power", "total_trades", "win_rate", "positions"]
            missing_fields = [field for field in required_fields if field not in data]
            self.log_result("Portfolio - Required Fields", len(missing_fields) == 0, f"Missing: {missing_fields}")
        return success

    def test_trades_endpoint(self):
        """Test /api/trades endpoint"""
        print("\n🔍 Testing Trades Endpoint...")
        success, data = self.run_test("Get Trades", "GET", "/trades")
        if success:
            self.log_result("Trades - Response Format", isinstance(data, list), f"Type: {type(data)}")
            
            # SPECIFIC TEST for review request: Check for actual executed trades
            if isinstance(data, list):
                trade_symbols = [trade.get('symbol') for trade in data if isinstance(trade, dict)]
                expected_symbols = ['AAPL', 'TSLA', 'QBTS']
                
                print(f"  📋 Found trades for symbols: {list(set(trade_symbols))}")
                print(f"  📋 Total trades returned: {len(data)}")
                
                # Check if we have trades for the expected symbols
                for symbol in expected_symbols:
                    has_trades = symbol in trade_symbols
                    self.log_result(f"Trades - {symbol} trades present", has_trades, 
                                  f"Found {trade_symbols.count(symbol)} trades for {symbol}")
                
                # Check if trades have required fields
                if data:
                    sample_trade = data[0]
                    required_fields = ['symbol', 'side', 'price', 'quantity', 'timestamp']
                    missing_fields = [field for field in required_fields if field not in sample_trade]
                    self.log_result("Trades - Required Fields", len(missing_fields) == 0, f"Missing: {missing_fields}")
                else:
                    self.log_result("Trades - Has Trade Records", False, "No trades found - bot may not have executed any trades yet")
        return success

    def test_bot_control(self):
        """Test bot control endpoints"""
        print("\n🔍 Testing Bot Control Endpoints...")
        
        # First get initial state
        initial_success, initial_health = self.run_test("Get Initial Health State", "GET", "/health")
        initial_running = initial_health.get('running', False) if initial_success else False
        
        # Test start bot
        success, data = self.run_test("Start Bot", "POST", "/bot/start")
        if success and data:
            self.log_result("Start Bot - Running Field", data.get("running") == True)
            
            # SPECIFIC TEST: Verify state persists by checking health endpoint
            health_success, health_data = self.run_test("Health After Start", "GET", "/health")
            if health_success and health_data:
                self.log_result("State Persistence - Running After Start", health_data.get('running') == True,
                              f"Health shows running: {health_data.get('running')}")

        # Test pause bot 
        success, data = self.run_test("Pause Bot", "POST", "/bot/pause")
        if success and data:
            self.log_result("Pause Bot - Paused Field", "paused" in data)
            
            # Check health shows paused state
            health_success, health_data = self.run_test("Health After Pause", "GET", "/health")
            if health_success and health_data:
                self.log_result("State Persistence - Paused State", health_data.get('paused') != False,
                              f"Health shows paused: {health_data.get('paused')}")

        # Test stop bot
        success, data = self.run_test("Stop Bot", "POST", "/bot/stop")
        if success and data:
            self.log_result("Stop Bot - Running Field", data.get("running") == False)
            
            # SPECIFIC TEST: Verify stop state persists by checking health endpoint
            health_success, health_data = self.run_test("Health After Stop", "GET", "/health")
            if health_success and health_data:
                self.log_result("State Persistence - Stopped After Stop", health_data.get('running') == False,
                              f"Health shows running: {health_data.get('running')}")

        return True

    def test_settings_endpoints(self):
        """Test settings endpoints"""
        print("\n🔍 Testing Settings Endpoints...")
        
        # Test get settings
        success, data = self.run_test("Get Settings", "GET", "/settings")
        if success and data:
            expected_fields = ["simulate_24_7", "telegram", "increment_step", "decrement_step", "cash_reserve"]
            missing_fields = [field for field in expected_fields if field not in data]
            self.log_result("Settings - Required Fields", len(missing_fields) == 0, f"Missing: {missing_fields}")
            
            # NEW: Test increment/decrement step fields
            self.log_result("Settings - Increment Step Field", "increment_step" in data, f"Increment Step: {data.get('increment_step', 'missing')}")
            self.log_result("Settings - Decrement Step Field", "decrement_step" in data, f"Decrement Step: {data.get('decrement_step', 'missing')}")
            self.log_result("Settings - Cash Reserve Field", "cash_reserve" in data, f"Cash Reserve: {data.get('cash_reserve', 'missing')}")
            
            # Test that step values are numbers
            inc_step = data.get('increment_step')
            dec_step = data.get('decrement_step')
            cash_reserve = data.get('cash_reserve')
            self.log_result("Settings - Increment Step Number", isinstance(inc_step, (int, float)), f"Type: {type(inc_step)}")
            self.log_result("Settings - Decrement Step Number", isinstance(dec_step, (int, float)), f"Type: {type(dec_step)}")
            self.log_result("Settings - Cash Reserve Number", isinstance(cash_reserve, (int, float)), f"Type: {type(cash_reserve)}")
            
            # NEW: Test telegram_connected field
            self.log_result("Settings - Telegram Connected Field", "telegram_connected" in data, f"Telegram Connected: {data.get('telegram_connected', 'missing')}")
            telegram_connected = data.get('telegram_connected')
            self.log_result("Settings - Telegram Connected Boolean", isinstance(telegram_connected, bool), f"Type: {type(telegram_connected)}")

        # Test update settings with telegram config and step sizes
        settings_update = {
            "telegram": {"bot_token": "test_token_fake", "chat_ids": ["123456789"]},
            "simulate_24_7": True,
            "increment_step": 0.25,
            "decrement_step": 0.75
        }
        success, response_data = self.run_test("Update Settings", "POST", "/settings", 200, settings_update)
        if success and response_data:
            # NEW: Test telegram_running status in response
            self.log_result("Settings Update - Telegram Running Field", "telegram_running" in response_data, f"Telegram Running: {response_data.get('telegram_running', 'missing')}")
        
        # Test get settings again to verify step updates were saved
        success, updated_data = self.run_test("Get Updated Settings", "GET", "/settings")
        if success and updated_data:
            self.log_result("Updated Settings - Increment Step Saved", updated_data.get('increment_step') == 0.25, f"Expected: 0.25, Got: {updated_data.get('increment_step')}")
            self.log_result("Updated Settings - Decrement Step Saved", updated_data.get('decrement_step') == 0.75, f"Expected: 0.75, Got: {updated_data.get('decrement_step')}")
        
        return True

    def test_cash_reserve_endpoints(self):
        """Test cash reserve endpoints"""
        print("\n🔍 Testing Cash Reserve Endpoints...")
        
        # Test get cash reserve
        success, data = self.run_test("Get Cash Reserve", "GET", "/cash-reserve")
        if success and data:
            expected_fields = ["total", "ledger"]
            missing_fields = [field for field in expected_fields if field not in data]
            self.log_result("Cash Reserve - Required Fields", len(missing_fields) == 0, f"Missing: {missing_fields}")
            
            # Test field types
            total = data.get('total')
            ledger = data.get('ledger')
            self.log_result("Cash Reserve - Total Number", isinstance(total, (int, float)), f"Total type: {type(total)}")
            self.log_result("Cash Reserve - Ledger List", isinstance(ledger, list), f"Ledger type: {type(ledger)}")
        
        return success

    def test_take_profit_endpoints(self):
        """Test take profit endpoints"""
        print("\n🔍 Testing Take Profit Endpoints...")
        
        # Test take profit for TSLA (should return 400 if no positive profit)
        success, data = self.run_test("Take Profit TSLA (No Profit)", "POST", "/tickers/TSLA/take-profit", 400)
        # This should fail with 400 because typically there's no positive P&L to take
        
        # Test with invalid symbol
        success, data = self.run_test("Take Profit Invalid Symbol", "POST", "/tickers/INVALID/take-profit", 400)
        
        return True

    def test_engine_state_persistence(self):
        """Test engine state restoration works - running/paused state persisted in MongoDB"""
        print("\n🔍 Testing Engine State Persistence...")
        
        # Test sequence: Start bot, verify health, stop bot, verify health, start again
        print("  📋 Testing start->stop->start sequence...")
        
        # Start the bot
        start_success, start_data = self.run_test("Engine Test - Start Bot", "POST", "/bot/start")
        if start_success:
            # Check health shows running
            health_success, health_data = self.run_test("Engine Test - Health After Start", "GET", "/health")
            if health_success:
                running_state = health_data.get('running')
                self.log_result("Engine State - Start Persisted", running_state == True,
                              f"Health shows running: {running_state}")
        
        # Stop the bot
        stop_success, stop_data = self.run_test("Engine Test - Stop Bot", "POST", "/bot/stop")
        if stop_success:
            # Check health shows stopped
            health_success, health_data = self.run_test("Engine Test - Health After Stop", "GET", "/health")
            if health_success:
                running_state = health_data.get('running')
                self.log_result("Engine State - Stop Persisted", running_state == False,
                              f"Health shows running: {running_state}")
        
        # Start the bot again to verify persistence works
        restart_success, restart_data = self.run_test("Engine Test - Restart Bot", "POST", "/bot/start")
        if restart_success:
            # Final health check
            health_success, health_data = self.run_test("Engine Test - Health After Restart", "GET", "/health")
            if health_success:
                running_state = health_data.get('running')
                simulate_247 = health_data.get('market_open')  # Should be True if simulate_24_7 is enabled
                self.log_result("Engine State - Restart Persisted", running_state == True,
                              f"Health shows running: {running_state}")
                self.log_result("Engine State - Simulate 24/7 Active", simulate_247 == True,
                              f"Market open (simulate_24_7): {simulate_247}")
        
        print("  📋 Engine state persistence test sequence completed")
        return True

    def test_telegram_endpoints(self):
        """Test Telegram-specific endpoints"""
        print("\n🔍 Testing Telegram Endpoints...")
        
        # Test telegram test endpoint when bot not connected
        # This should return 400 because no real token is configured
        success, data = self.run_test("Telegram Test (No Connection)", "POST", "/settings/telegram/test", 400)
        if not success:
            # If it didn't return 400, check if it returned some other error indicating not connected
            _, actual_response = self.run_test("Telegram Test Check Response", "POST", "/settings/telegram/test", expected_status=None)
            # The test should fail with 400, so if it passes, that's wrong too
            self.log_result("Telegram Test - Correct Error Response", False, "Expected 400 status when bot not connected")
        
        return True

    def test_dollar_vs_percent_mode(self):
        """Test the dollar mode vs percent mode fix for buy/sell offset calculations"""
        print("\n🔍 Testing Dollar Mode vs Percent Mode...")
        
        # First, get current tickers to see existing configuration
        success, tickers = self.run_test("Get Tickers for Mode Testing", "GET", "/tickers")
        if not success:
            return False
            
        # Find AAPL and NVDA tickers
        aapl_ticker = None
        nvda_ticker = None
        
        if isinstance(tickers, list):
            for ticker in tickers:
                if ticker.get('symbol') == 'AAPL':
                    aapl_ticker = ticker
                elif ticker.get('symbol') == 'NVDA':
                    nvda_ticker = ticker
        
        # Test AAPL in dollar mode configuration
        if aapl_ticker:
            print(f"  📋 AAPL Current Config: buy_percent={aapl_ticker.get('buy_percent')}, sell_percent={aapl_ticker.get('sell_percent')}")
            print(f"      buy_offset={aapl_ticker.get('buy_offset')}, sell_offset={aapl_ticker.get('sell_offset')}")
            
            # Verify AAPL is in dollar mode
            is_dollar_mode = (aapl_ticker.get('buy_percent') == False and aapl_ticker.get('sell_percent') == False)
            self.log_result("AAPL - Dollar Mode Configuration", is_dollar_mode, 
                          f"buy_percent={aapl_ticker.get('buy_percent')}, sell_percent={aapl_ticker.get('sell_percent')}")
            
            # Verify the expected buy/sell offset values
            expected_buy = 250.0
            expected_sell = 250.10
            actual_buy = aapl_ticker.get('buy_offset')
            actual_sell = aapl_ticker.get('sell_offset')
            
            self.log_result("AAPL - Buy Offset Value", abs(actual_buy - expected_buy) < 0.01, 
                          f"Expected: {expected_buy}, Actual: {actual_buy}")
            self.log_result("AAPL - Sell Offset Value", abs(actual_sell - expected_sell) < 0.01, 
                          f"Expected: {expected_sell}, Actual: {actual_sell}")
        else:
            self.log_result("AAPL Ticker Found", False, "AAPL ticker not found for testing")
        
        # Test NVDA in percent mode configuration  
        if nvda_ticker:
            print(f"  📋 NVDA Current Config: buy_percent={nvda_ticker.get('buy_percent')}, sell_percent={nvda_ticker.get('sell_percent')}")
            print(f"      buy_offset={nvda_ticker.get('buy_offset')}, sell_offset={nvda_ticker.get('sell_offset')}")
            
            # Verify NVDA is in percent mode (default)
            is_percent_mode = (nvda_ticker.get('buy_percent') == True and nvda_ticker.get('sell_percent') == True)
            self.log_result("NVDA - Percent Mode Configuration", is_percent_mode,
                          f"buy_percent={nvda_ticker.get('buy_percent')}, sell_percent={nvda_ticker.get('sell_percent')}")
            
            # Check that offsets are reasonable percent values (negative for buy, positive for sell)
            buy_offset = nvda_ticker.get('buy_offset', 0)
            sell_offset = nvda_ticker.get('sell_offset', 0)
            
            self.log_result("NVDA - Buy Offset Negative", buy_offset < 0, f"Buy offset: {buy_offset}%")
            self.log_result("NVDA - Sell Offset Positive", sell_offset > 0, f"Sell offset: {sell_offset}%")
        else:
            self.log_result("NVDA Ticker Found", False, "NVDA ticker not found for testing")
        
        # Test updating a ticker to switch between modes
        test_updates = {
            "buy_percent": False,
            "sell_percent": False, 
            "buy_offset": 100.50,
            "sell_offset": 101.75
        }
        
        success, updated_ticker = self.run_test("Update NVDA to Dollar Mode", "PUT", "/tickers/NVDA", 200, test_updates)
        if success and updated_ticker:
            self.log_result("NVDA - Updated to Dollar Mode", 
                          updated_ticker.get('buy_percent') == False and updated_ticker.get('sell_percent') == False,
                          f"buy_percent={updated_ticker.get('buy_percent')}, sell_percent={updated_ticker.get('sell_percent')}")
            self.log_result("NVDA - Dollar Mode Buy Offset", abs(updated_ticker.get('buy_offset', 0) - 100.50) < 0.01,
                          f"Expected: 100.50, Actual: {updated_ticker.get('buy_offset')}")
            self.log_result("NVDA - Dollar Mode Sell Offset", abs(updated_ticker.get('sell_offset', 0) - 101.75) < 0.01,
                          f"Expected: 101.75, Actual: {updated_ticker.get('sell_offset')}")
        
        # Switch back to percent mode
        percent_updates = {
            "buy_percent": True,
            "sell_percent": True,
            "buy_offset": -3.0,
            "sell_offset": 3.0
        }
        
        success, restored_ticker = self.run_test("Restore NVDA to Percent Mode", "PUT", "/tickers/NVDA", 200, percent_updates)
        if success and restored_ticker:
            self.log_result("NVDA - Restored to Percent Mode",
                          restored_ticker.get('buy_percent') == True and restored_ticker.get('sell_percent') == True,
                          f"buy_percent={restored_ticker.get('buy_percent')}, sell_percent={restored_ticker.get('sell_percent')}")
        
        return True

    def run_all_tests(self):
        """Run comprehensive API test suite"""
        print("🚀 Starting BracketBot API Test Suite")
        print(f"Testing against: {self.base_url}")
        print("=" * 60)

        # Run all test categories
        self.test_health_endpoint()
        self.test_tickers_crud() 
        self.test_strategies_endpoint()
        self.test_portfolio_endpoint()
        self.test_trades_endpoint()
        self.test_bot_control()
        self.test_engine_state_persistence()  # NEW: Test engine state persistence specifically
        self.test_settings_endpoints()
        self.test_cash_reserve_endpoints()  # NEW: Test cash reserve endpoints
        self.test_take_profit_endpoints()    # NEW: Test take profit endpoints
        self.test_telegram_endpoints()  # NEW: Test Telegram-specific endpoints
        self.test_dollar_vs_percent_mode()   # NEW: Test dollar vs percent mode fix

        # Print final results
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests PASSED!")
            return True
        else:
            failure_rate = ((self.tests_run - self.tests_passed) / self.tests_run) * 100
            print(f"⚠️  {failure_rate:.1f}% failure rate")
            
            # List failed tests
            failed_tests = [r for r in self.test_results if r["status"] == "FAIL"]
            if failed_tests:
                print("\n❌ Failed Tests:")
                for test in failed_tests[:5]:  # Show first 5 failures
                    print(f"  - {test['test']}: {test['details']}")
            return False

def main():
    tester = BracketBotAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())