from trading_engine import TradingEngine


def test_default_symbol_position_limit_is_notional():
    engine = TradingEngine()
    limit = engine.ensure_symbol_exposure_limit("QSI")

    assert limit.max_notional == 10000
    assert limit.max_position_size == 0


def test_sub_dollar_and_high_price_symbols_share_same_dollar_limit():
    engine = TradingEngine()

    qsi_allowed = engine.check_projected_symbol_risk("QSI", "BUY", 523, 0.955)
    qsi_blocked = engine.check_projected_symbol_risk("QSI", "BUY", 11000, 0.955)
    asts_blocked = engine.check_projected_symbol_risk("ASTS", "BUY", 118, 90)

    assert qsi_allowed.is_allowed is True
    assert qsi_blocked.is_allowed is False
    assert asts_blocked.is_allowed is False
    assert qsi_blocked.rejected_fields["notional"] > 10000
    assert asts_blocked.rejected_fields["notional"] > 10000
