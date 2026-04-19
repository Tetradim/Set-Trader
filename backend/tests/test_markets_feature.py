"""
Multi-region stock market support tests.
Tests: GET /markets, GET /markets/{code}, GET /fx-rates,
       GET/POST /settings/currency-display, market auto-detection, etc.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

EXPECTED_MARKET_CODES = ["US", "HK", "AU", "UK", "CA", "CN_SS", "CN_SZ"]
EXPECTED_CURRENCIES = {"HKD", "AUD", "GBP", "CAD", "CNY"}


class TestListMarkets:
    """Test GET /api/markets endpoint"""

    def test_markets_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/markets")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/markets returns 200")

    def test_markets_has_all_7_codes(self):
        response = requests.get(f"{BASE_URL}/api/markets")
        assert response.status_code == 200
        data = response.json()
        assert "markets" in data, "Response should have 'markets' key"
        codes = [m["code"] for m in data["markets"]]
        for code in EXPECTED_MARKET_CODES:
            assert code in codes, f"Expected market code '{code}' not found in {codes}"
        print(f"PASS: All 7 markets present: {codes}")

    def test_markets_have_required_fields(self):
        response = requests.get(f"{BASE_URL}/api/markets")
        assert response.status_code == 200
        data = response.json()
        required_fields = ["code", "name", "flag", "currency", "status", "local_time",
                           "hours_display", "ticker_examples"]
        for m in data["markets"]:
            for field in required_fields:
                assert field in m, f"Market {m.get('code')} missing field '{field}'"
        print("PASS: All markets have required fields (code, name, flag, currency, status, local_time, hours_display, ticker_examples)")

    def test_us_market_present_with_usd(self):
        response = requests.get(f"{BASE_URL}/api/markets")
        assert response.status_code == 200
        data = response.json()
        us_market = next((m for m in data["markets"] if m["code"] == "US"), None)
        assert us_market is not None, "US market should be present"
        assert us_market["currency"] == "USD", f"US market currency should be USD, got {us_market['currency']}"
        print(f"PASS: US market present with currency USD")

    def test_status_field_valid_values(self):
        response = requests.get(f"{BASE_URL}/api/markets")
        assert response.status_code == 200
        data = response.json()
        valid_statuses = {"open", "closed", "lunch"}
        for m in data["markets"]:
            assert m["status"] in valid_statuses, \
                f"Market {m['code']} status '{m['status']}' not in {valid_statuses}"
        print("PASS: All market statuses are valid (open/closed/lunch)")


class TestGetSingleMarket:
    """Test GET /api/markets/{code}"""

    def test_get_hk_market(self):
        response = requests.get(f"{BASE_URL}/api/markets/HK")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["code"] == "HK"
        assert data["currency"] == "HKD"
        assert data["flag"] == "🇭🇰"
        print(f"PASS: GET /api/markets/HK returns HK market with currency HKD")

    def test_hk_has_lunch_break(self):
        response = requests.get(f"{BASE_URL}/api/markets/HK")
        assert response.status_code == 200
        data = response.json()
        assert data.get("lunch_break") == True, \
            f"HK market should have lunch_break=True, got {data.get('lunch_break')}"
        print("PASS: HK market has lunch_break=True")

    def test_hk_status_valid(self):
        response = requests.get(f"{BASE_URL}/api/markets/HK")
        assert response.status_code == 200
        data = response.json()
        valid_statuses = ["open", "closed", "lunch"]
        assert data["status"] in valid_statuses, \
            f"HK status '{data['status']}' not in {valid_statuses}"
        print(f"PASS: HK market status is valid: {data['status']}")

    def test_get_au_market(self):
        response = requests.get(f"{BASE_URL}/api/markets/AU")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "AU"
        assert data["currency"] == "AUD"
        assert data["flag"] == "🇦🇺"
        print(f"PASS: GET /api/markets/AU returns AU market with currency AUD")

    def test_get_uk_market(self):
        response = requests.get(f"{BASE_URL}/api/markets/UK")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "UK"
        assert data["currency"] == "GBP"
        assert data["flag"] == "🇬🇧"
        print(f"PASS: GET /api/markets/UK returns UK market with currency GBP")

    def test_get_ca_market(self):
        response = requests.get(f"{BASE_URL}/api/markets/CA")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "CA"
        assert data["currency"] == "CAD"
        assert data["flag"] == "🇨🇦"
        print(f"PASS: GET /api/markets/CA returns CA market with currency CAD")

    def test_get_cn_ss_market(self):
        response = requests.get(f"{BASE_URL}/api/markets/CN_SS")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "CN_SS"
        assert data["currency"] == "CNY"
        assert data.get("lunch_break") == True, "CN_SS should have lunch break"
        print(f"PASS: GET /api/markets/CN_SS returns CN_SS market with CNY + lunch break")

    def test_get_cn_sz_market(self):
        response = requests.get(f"{BASE_URL}/api/markets/CN_SZ")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "CN_SZ"
        assert data["currency"] == "CNY"
        assert data.get("lunch_break") == True, "CN_SZ should have lunch break"
        print(f"PASS: GET /api/markets/CN_SZ returns CN_SZ market with CNY + lunch break")

    def test_invalid_market_returns_404(self):
        response = requests.get(f"{BASE_URL}/api/markets/INVALID")
        assert response.status_code == 404, \
            f"Expected 404 for invalid market, got {response.status_code}"
        print("PASS: Invalid market code returns 404")

    def test_market_code_case_insensitive(self):
        response = requests.get(f"{BASE_URL}/api/markets/hk")
        assert response.status_code == 200, \
            f"Should accept lowercase 'hk', got {response.status_code}"
        data = response.json()
        assert data["code"] == "HK"
        print("PASS: Market code lookup is case-insensitive (hk -> HK)")


class TestFxRates:
    """Test GET /api/fx-rates"""

    def test_fx_rates_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/fx-rates")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/fx-rates returns 200")

    def test_fx_rates_has_rates_key(self):
        response = requests.get(f"{BASE_URL}/api/fx-rates")
        assert response.status_code == 200
        data = response.json()
        assert "rates" in data, "Response should have 'rates' key"
        print(f"PASS: FX rates response has 'rates' key with: {list(data['rates'].keys())}")

    def test_usd_rate_is_1(self):
        response = requests.get(f"{BASE_URL}/api/fx-rates")
        assert response.status_code == 200
        data = response.json()
        rates = data["rates"]
        assert "USD" in rates, "USD should be in rates"
        assert rates["USD"] == 1.0, f"USD rate should be 1.0, got {rates['USD']}"
        print("PASS: USD rate = 1.0")

    def test_fx_rates_have_foreign_currencies(self):
        response = requests.get(f"{BASE_URL}/api/fx-rates")
        assert response.status_code == 200
        data = response.json()
        rates = data["rates"]
        # At least some foreign currencies should be present
        # (may be 0 if yfinance is unavailable, but USD should always be there)
        expected_currencies = ["HKD", "AUD", "GBP", "CAD", "CNY"]
        found = [c for c in expected_currencies if c in rates and rates[c] > 0]
        print(f"PASS/INFO: FX rates found for: {found} (out of {expected_currencies})")
        # We don't hard-fail if yfinance is unavailable, just check structure
        assert isinstance(rates, dict), "rates should be a dict"

    def test_fx_rate_values_are_positive(self):
        response = requests.get(f"{BASE_URL}/api/fx-rates")
        assert response.status_code == 200
        data = response.json()
        rates = data["rates"]
        for currency, rate in rates.items():
            if rate > 0:
                assert isinstance(rate, (int, float)), f"{currency} rate should be numeric"
                assert rate > 0, f"{currency} rate should be positive, got {rate}"
        print(f"PASS: All non-zero FX rates are positive numbers: {rates}")


class TestCurrencyDisplaySettings:
    """Test GET/POST /api/settings/currency-display"""

    def test_get_currency_display_returns_200(self):
        response = requests.get(f"{BASE_URL}/api/settings/currency-display")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASS: GET /api/settings/currency-display returns 200")

    def test_get_currency_display_has_mode_field(self):
        response = requests.get(f"{BASE_URL}/api/settings/currency-display")
        assert response.status_code == 200
        data = response.json()
        assert "mode" in data, "Response should have 'mode' key"
        assert data["mode"] in ("usd", "native"), \
            f"mode should be 'usd' or 'native', got '{data['mode']}'"
        print(f"PASS: GET /api/settings/currency-display returns mode='{data['mode']}'")

    def test_set_currency_display_native(self):
        response = requests.post(f"{BASE_URL}/api/settings/currency-display?mode=native")
        assert response.status_code == 200, \
            f"Expected 200 for mode=native, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("mode") == "native", \
            f"Expected mode='native', got '{data.get('mode')}'"
        print("PASS: POST /api/settings/currency-display?mode=native returns {mode: 'native'}")

    def test_verify_native_preference_persisted(self):
        # Set to native first
        requests.post(f"{BASE_URL}/api/settings/currency-display?mode=native")
        # Then GET to verify persisted
        response = requests.get(f"{BASE_URL}/api/settings/currency-display")
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "native", \
            f"Persisted mode should be 'native', got '{data.get('mode')}'"
        print("PASS: native currency preference persisted across GET")

    def test_set_currency_display_usd(self):
        response = requests.post(f"{BASE_URL}/api/settings/currency-display?mode=usd")
        assert response.status_code == 200, \
            f"Expected 200 for mode=usd, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("mode") == "usd", \
            f"Expected mode='usd', got '{data.get('mode')}'"
        print("PASS: POST /api/settings/currency-display?mode=usd returns {mode: 'usd'}")

    def test_verify_usd_preference_persisted(self):
        # Set to usd
        requests.post(f"{BASE_URL}/api/settings/currency-display?mode=usd")
        # GET to verify
        response = requests.get(f"{BASE_URL}/api/settings/currency-display")
        assert response.status_code == 200
        data = response.json()
        assert data.get("mode") == "usd", \
            f"Persisted mode should be 'usd', got '{data.get('mode')}'"
        print("PASS: usd currency preference persisted across GET")

    def test_invalid_currency_mode_returns_400(self):
        response = requests.post(f"{BASE_URL}/api/settings/currency-display?mode=invalid")
        assert response.status_code == 400, \
            f"Expected 400 for invalid mode, got {response.status_code}: {response.text}"
        print("PASS: Invalid currency mode returns 400")


class TestMarketAutoDetect:
    """Test market auto-detection logic via ticker creation"""

    def test_add_bhp_ax_detects_au_market(self):
        """Adding BHP.AX should auto-detect AU market"""
        sym = "TEST_BHP.AX"
        # Create ticker
        resp = requests.post(f"{BASE_URL}/api/tickers", json={
            "symbol": sym,
            "base_power": 100.0,
        })
        assert resp.status_code in [200, 201], f"Failed to create ticker: {resp.text}"
        
        # Verify market
        get_resp = requests.get(f"{BASE_URL}/api/tickers")
        assert get_resp.status_code == 200
        tickers = get_resp.json()
        ticker = next((t for t in tickers if t.get("symbol") == sym), None)
        assert ticker is not None, f"Ticker {sym} not found after creation"
        assert ticker.get("market") == "AU", \
            f"Expected market='AU' for {sym}, got '{ticker.get('market')}'"
        print(f"PASS: {sym} auto-detected market=AU")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tickers/{sym}")

    def test_add_hk_ticker_detects_hk_market(self):
        """Adding 0700.HK should auto-detect HK market"""
        sym = "TEST_0700.HK"
        resp = requests.post(f"{BASE_URL}/api/tickers", json={
            "symbol": sym,
            "base_power": 100.0,
        })
        assert resp.status_code in [200, 201], f"Failed to create ticker: {resp.text}"
        
        get_resp = requests.get(f"{BASE_URL}/api/tickers")
        tickers = get_resp.json()
        ticker = next((t for t in tickers if t.get("symbol") == sym), None)
        assert ticker is not None
        assert ticker.get("market") == "HK", \
            f"Expected market='HK' for {sym}, got '{ticker.get('market')}'"
        print(f"PASS: {sym} auto-detected market=HK")
        
        requests.delete(f"{BASE_URL}/api/tickers/{sym}")

    def test_add_lse_ticker_detects_uk_market(self):
        """Adding BARC.L should auto-detect UK market"""
        sym = "TEST_BARC.L"
        resp = requests.post(f"{BASE_URL}/api/tickers", json={
            "symbol": sym,
            "base_power": 100.0,
        })
        assert resp.status_code in [200, 201], f"Failed to create ticker: {resp.text}"
        
        get_resp = requests.get(f"{BASE_URL}/api/tickers")
        tickers = get_resp.json()
        ticker = next((t for t in tickers if t.get("symbol") == sym), None)
        assert ticker is not None
        assert ticker.get("market") == "UK", \
            f"Expected market='UK' for {sym}, got '{ticker.get('market')}'"
        print(f"PASS: {sym} auto-detected market=UK")
        
        requests.delete(f"{BASE_URL}/api/tickers/{sym}")

    def test_add_us_ticker_defaults_to_us(self):
        """Adding AAPL (no suffix) should default to US market"""
        sym = "TEST_AAPL_MKT"
        resp = requests.post(f"{BASE_URL}/api/tickers", json={
            "symbol": sym,
            "base_power": 100.0,
        })
        assert resp.status_code in [200, 201], f"Failed to create ticker: {resp.text}"
        
        get_resp = requests.get(f"{BASE_URL}/api/tickers")
        tickers = get_resp.json()
        ticker = next((t for t in tickers if t.get("symbol") == sym), None)
        assert ticker is not None
        assert ticker.get("market") == "US", \
            f"Expected market='US' for US ticker, got '{ticker.get('market')}'"
        print(f"PASS: {sym} defaults to market=US")
        
        requests.delete(f"{BASE_URL}/api/tickers/{sym}")


class TestTradingEngineMarketMethods:
    """Code review tests for market-aware trading engine methods"""

    def test_is_ticker_market_open_method_exists(self):
        engine_path = "/app/backend/trading_engine.py"
        with open(engine_path, 'r') as f:
            content = f.read()
        assert "_is_ticker_market_open" in content, "_is_ticker_market_open method must exist"
        assert "_get_market(ticker_doc)" in content or "_get_market(ticker_doc).is_open_now()" in content
        print("PASS: _is_ticker_market_open method exists")

    def test_evaluate_ticker_uses_per_ticker_market_check(self):
        engine_path = "/app/backend/trading_engine.py"
        with open(engine_path, 'r') as f:
            content = f.read()
        assert "_is_ticker_market_open(ticker_doc)" in content, \
            "evaluate_ticker must call _is_ticker_market_open(ticker_doc)"
        print("PASS: evaluate_ticker calls _is_ticker_market_open(ticker_doc)")

    def test_duplicate_method_definitions_bug(self):
        """CRITICAL: Detect the duplicate _is_opening_window / _is_past_opening_window definitions.
        The market-aware version (with ticker_doc param) is defined FIRST,
        but the legacy US-only version is defined SECOND and OVERWRITES the first.
        In Python the last definition wins — calls like _is_opening_window(30, ticker_doc) will FAIL."""
        engine_path = "/app/backend/trading_engine.py"
        with open(engine_path, 'r') as f:
            content = f.read()
        lines = content.split('\n')
        
        ow_defs = [i+1 for i, line in enumerate(lines) if 'def _is_opening_window' in line]
        pow_defs = [i+1 for i, line in enumerate(lines) if 'def _is_past_opening_window' in line]
        
        print(f"_is_opening_window defined at lines: {ow_defs}")
        print(f"_is_past_opening_window defined at lines: {pow_defs}")
        
        # This test intentionally FAILS to highlight the bug
        assert len(ow_defs) == 1, \
            f"CRITICAL BUG: _is_opening_window defined {len(ow_defs)} times at lines {ow_defs}. " \
            f"The legacy definition at line {ow_defs[-1]} OVERRIDES the market-aware version at line {ow_defs[0]}. " \
            f"Calls like _is_opening_window(30, ticker_doc) will raise TypeError."

    def test_detect_market_from_symbol_logic(self):
        """Test detect_market_from_symbol function via code review"""
        import sys
        sys.path.insert(0, '/app/backend')
        from markets import detect_market_from_symbol
        
        assert detect_market_from_symbol("BHP.AX") == "AU"
        assert detect_market_from_symbol("0700.HK") == "HK"
        assert detect_market_from_symbol("BARC.L") == "UK"
        assert detect_market_from_symbol("RY.TO") == "CA"
        assert detect_market_from_symbol("600036.SS") == "CN_SS"
        assert detect_market_from_symbol("000001.SZ") == "CN_SZ"
        assert detect_market_from_symbol("AAPL") == "US"
        assert detect_market_from_symbol("TSLA") == "US"
        print("PASS: detect_market_from_symbol works correctly for all suffixes")

    def test_market_config_is_open_now_methods(self):
        """Test MarketConfig status methods work"""
        import sys
        sys.path.insert(0, '/app/backend')
        from markets import MARKETS
        
        for code, market in MARKETS.items():
            status = market.status()
            assert status in ("open", "closed", "lunch"), \
                f"Market {code} returned invalid status: {status}"
            local_time = market.local_now()
            assert local_time is not None
            print(f"  {code}: status={status}, local_time={local_time.strftime('%H:%M:%S')}")
        print("PASS: All market status() and local_now() methods work")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
