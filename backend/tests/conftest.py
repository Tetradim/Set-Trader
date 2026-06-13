"""Pytest collection rules for Sentinel Pulse backend tests."""
import os
from pathlib import Path


LIVE_BACKEND_TEST_MODULES = {
    "test_account_balance_feature.py",
    "test_audit_log_feature.py",
    "test_beta_brokers_metrics.py",
    "test_brokers_api.py",
    "test_chart_preset_features.py",
    "test_feedback_broker_test.py",
    "test_loss_log_feature.py",
    "test_manual_sell_feature.py",
    "test_markets_feature.py",
    "test_opening_bell_feature.py",
    "test_order_type_feature.py",
    "test_partial_fills_feature.py",
    "test_rebracket_params.py",
    "test_refactor_regression.py",
    "test_reorder_config_modal.py",
    "test_resilience_feature.py",
    "test_trade_metadata_feature.py",
    "test_traces_api.py",
    "test_trading_cooldown.py",
    "test_trading_mode_features.py",
}


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires REACT_APP_BACKEND_URL pointing at a running Sentinel Pulse backend",
    )


def pytest_ignore_collect(collection_path, config):
    """Skip live HTTP API tests during local unit-test runs."""
    has_backend_url = bool(os.environ.get("REACT_APP_BACKEND_URL", "").strip())
    path = Path(str(collection_path))
    return (not has_backend_url) and path.name in LIVE_BACKEND_TEST_MODULES
