from decimal import Decimal

from pydantic import ValidationError

from schemas import TickerConfig
from trading.passive_range_patch import _quantity_for_power
from trading.price_precision import bracket_target, infer_tick_size, normalize_price


def test_sub_dollar_targets_preserve_four_decimal_prices():
    tick = infer_tick_size(0.955)

    assert tick == Decimal("0.0001")
    assert normalize_price("0.955", tick) == Decimal("0.9550")
    assert normalize_price("0.966", tick) == Decimal("0.9660")


def test_passive_buy_rounds_down_and_sell_rounds_up_to_tick():
    tick = Decimal("0.0001")

    buy = bracket_target(
        "1", "0.95505", is_percent=False, tick_size=tick, side="buy"
    )
    sell = bracket_target(
        "1", "0.96595", is_percent=False, tick_size=tick, side="sell"
    )

    assert buy == Decimal("0.9550")
    assert sell == Decimal("0.9660")


def test_whole_share_sizing_never_exceeds_buying_power():
    quantity = _quantity_for_power(500, 0.955, fractional=False)

    assert quantity == 523
    assert quantity * 0.955 <= 500


def test_fractional_share_sizing_is_available_but_not_default():
    quantity = _quantity_for_power(500, 0.955, fractional=True)

    assert quantity == 523.56020942


def test_ticker_schema_accepts_absolute_sub_dollar_buy_price():
    ticker = TickerConfig(
        symbol="QSI",
        buy_percent=False,
        buy_offset=0.955,
        sell_percent=False,
        sell_offset=0.966,
        passive_range_enabled=True,
        price_tick_size=0.0001,
    )

    assert ticker.buy_offset == 0.955
    assert ticker.sell_offset == 0.966
    assert ticker.passive_range_enabled is True


def test_ticker_schema_rejects_absolute_price_in_percent_mode():
    try:
        TickerConfig(symbol="QSI", buy_percent=True, buy_offset=0.955)
    except ValidationError as exc:
        assert "buy_offset must be between -50 and 0" in str(exc)
    else:
        raise AssertionError("positive absolute buy price was accepted as a percentage")


def test_ticker_schema_rejects_inverted_passive_range():
    try:
        TickerConfig(
            symbol="QSI",
            buy_percent=False,
            buy_offset=0.966,
            sell_percent=False,
            sell_offset=0.955,
            passive_range_enabled=True,
        )
    except ValidationError as exc:
        assert "buy price must be below the sell price" in str(exc)
    else:
        raise AssertionError("inverted passive range was accepted")


def test_ticker_schema_rejects_stop_above_passive_buy():
    try:
        TickerConfig(
            symbol="QSI",
            buy_percent=False,
            buy_offset=0.955,
            sell_percent=False,
            sell_offset=0.966,
            stop_percent=False,
            stop_offset=0.96,
            passive_range_enabled=True,
        )
    except ValidationError as exc:
        assert "stop price must be below the buy price" in str(exc)
    else:
        raise AssertionError("passive stop above entry was accepted")
