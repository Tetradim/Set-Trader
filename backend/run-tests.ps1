param(
    [switch]$Live
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

$staticSuites = @(
    "backend.tests.test_advanced_risk",
    "backend.tests.test_advanced_risk_routes_static",
    "backend.tests.test_readme_advanced_risk_static",
    "backend.tests.test_no_demo_artifacts",
    "backend.tests.test_upload_hygiene_static",
    "backend.tests.test_release_security_static",
    "backend.tests.test_edge_route_contract_static",
    "backend.tests.test_edge_resilience",
    "backend.tests.test_edge_contract_integration",
    "backend.tests.test_market_calendar",
    "backend.tests.test_launcher_and_test_env_static",
    "backend.tests.test_preflight_static",
    "backend.tests.test_ui_logging_static",
    "backend.tests.test_uninstall_cleanup_static"
)

Write-Host "Running backend static/unit suites..."
& $python -m unittest @staticSuites
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Live) {
    if (-not $env:REACT_APP_BACKEND_URL) {
        throw "Live backend tests require REACT_APP_BACKEND_URL, for example http://127.0.0.1:8002"
    }

    & $python -c "import pytest" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "pytest is not installed. Run: python -m pip install -r backend\requirements.txt"
    }

    Write-Host "Running backend live/API suites against $env:REACT_APP_BACKEND_URL..."
    & $python -m pytest backend/tests/test_refactor_regression.py backend/tests/test_markets_feature.py backend/tests/test_trading_mode_features.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
