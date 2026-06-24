import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import deps  # noqa: E402
from risk_controls import ExposureLimit  # noqa: E402
from trading_engine import TradingEngine  # noqa: E402


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass


def _engine(monkeypatch):
    monkeypatch.setattr(deps, "logger", _Logger())
    engine = TradingEngine()
    engine.risk_controls.add_exposure_limit(
        ExposureLimit(
            limit_id="test_portfolio",
            level="portfolio",
            level_id="global",
            max_notional=100.0,
            current_notional=90.0,
        )
    )
    return engine


def test_pre_trade_check_rejects_buy_that_would_exceed_portfolio_notional(monkeypatch):
    engine = _engine(monkeypatch)

    allowed, reason = asyncio.run(engine.pre_trade_check("SPY", "BUY", 1.0, 20.0))

    assert allowed is False
    assert "Projected notional limit exceeded" in reason
    assert "$110.0 > $100.0" in reason


def test_pre_trade_check_allows_sell_that_reduces_over_limit_portfolio_notional(monkeypatch):
    engine = _engine(monkeypatch)
    portfolio_limit = engine.risk_controls.get_exposure_limit("portfolio", "global")
    portfolio_limit.current_notional = 110.0

    allowed, reason = asyncio.run(engine.pre_trade_check("SPY", "SELL", 1.0, 20.0))

    assert allowed is True
    assert reason == ""


def test_pre_trade_check_rejects_buy_that_would_exceed_symbol_notional(monkeypatch):
    engine = _engine(monkeypatch)
    portfolio_limit = engine.risk_controls.get_exposure_limit("portfolio", "global")
    portfolio_limit.max_notional = 1000.0
    engine.risk_controls.add_exposure_limit(
        ExposureLimit(
            limit_id="spy_symbol",
            level="symbol",
            level_id="SPY",
            max_notional=100.0,
            current_notional=90.0,
        )
    )

    allowed, reason = asyncio.run(engine.pre_trade_check("SPY", "BUY", 1.0, 20.0))

    assert allowed is False
    assert "Projected symbol notional limit exceeded" in reason
    assert "$110.0 > $100.0" in reason


def test_pre_trade_check_applies_default_symbol_position_limit(monkeypatch):
    engine = _engine(monkeypatch)
    portfolio_limit = engine.risk_controls.get_exposure_limit("portfolio", "global")
    portfolio_limit.max_notional = 1000.0
    default_limit = engine.risk_controls.get_exposure_limit("symbol", "default")
    default_limit.max_position_size = 10.0

    allowed, reason = asyncio.run(engine.pre_trade_check("AAPL", "BUY", 11.0, 10.0))

    assert allowed is False
    assert "Projected symbol position size exceeded" in reason
