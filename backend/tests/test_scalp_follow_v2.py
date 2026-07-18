from datetime import datetime, timedelta, timezone

import pytest

from trading.scalp_follow_v2 import (
    ScalpAction,
    ScalpFollowConfig,
    ScalpFollowController,
    ScalpState,
)


def ts(minute: int = 0) -> datetime:
    return datetime(2026, 7, 1, 14, 30, tzinfo=timezone.utc) + timedelta(minutes=minute)


def controller() -> ScalpFollowController:
    return ScalpFollowController(
        ScalpFollowConfig(
            half_width=0.50,
            recenter_trigger=2.00,
            recenter_cooldown_seconds=900,
            max_hold_seconds=2700,
        ),
        initial_center=750.00,
    )


def test_sticky_zone_does_not_follow_each_penny():
    c = controller()
    for minute, price in enumerate([750.01, 750.20, 750.40, 750.10]):
        decision = c.observe_flat(timestamp=ts(minute), price=price)
        assert decision.action in {ScalpAction.HOLD, ScalpAction.BUY_READY}
        assert decision.center == 750.00


def test_three_confirmed_closes_recenter_up_once():
    c = controller()
    prices = [750.0, 750.1, 752.1, 752.2, 752.3]
    decisions = [
        c.observe_flat(timestamp=ts(i), price=price)
        for i, price in enumerate(prices)
    ]
    assert decisions[-1].action is ScalpAction.RECENTER
    assert decisions[-1].direction == "UP"
    assert decisions[-1].center > 750.0


def test_recenter_cooldown_prevents_immediate_second_jump():
    c = controller()
    for i, price in enumerate([750.0, 750.1, 752.1, 752.2, 752.3]):
        c.observe_flat(timestamp=ts(i), price=price)
    center = c.runtime.center
    for i, price in enumerate([754.5, 754.6, 754.7], start=5):
        decision = c.observe_flat(timestamp=ts(i), price=price)
    assert decision.action is not ScalpAction.RECENTER
    assert c.runtime.center == center


def test_open_position_freezes_atomic_target_and_stop():
    c = controller()
    bracket = c.open_position(timestamp=ts(), entry_price=749.50)
    assert bracket.target == 750.50
    assert bracket.stop == 748.25
    c.observe_position(timestamp=ts(1), price=752.00)
    assert c.runtime.position.target == 750.50
    assert c.runtime.position.stop == 748.25
    flat_decision = c.observe_flat(timestamp=ts(2), price=754.00)
    assert flat_decision.reason == "position_bracket_frozen"


def test_weak_trade_tightens_stop_after_review_window():
    c = controller()
    c.open_position(timestamp=ts(), entry_price=749.50)
    decision = c.observe_position(timestamp=ts(20), price=749.55)
    assert decision.action is ScalpAction.TIGHTEN_STOP
    assert decision.stop_price == 749.00


def test_time_exit_prevents_long_term_hold():
    c = controller()
    c.open_position(timestamp=ts(), entry_price=749.50)
    decision = c.observe_position(timestamp=ts(46), price=749.60)
    assert decision.action is ScalpAction.TIME_EXIT


def test_exit_cooldown_blocks_recenter_and_reentry():
    c = controller()
    c.open_position(timestamp=ts(), entry_price=749.50)
    c.close_position(timestamp=ts(1), profitable=False)
    decision = c.observe_flat(timestamp=ts(2), price=745.00)
    assert decision.state is ScalpState.EXIT_COOLDOWN
    assert decision.action is ScalpAction.HOLD


def test_target_must_be_above_actual_entry():
    c = controller()
    with pytest.raises(ValueError, match="sell target"):
        c.open_position(timestamp=ts(), entry_price=751.00)


def test_config_rejects_follow_trigger_inside_trading_zone():
    with pytest.raises(ValueError, match="recenter_trigger"):
        ScalpFollowConfig(half_width=1.0, recenter_trigger=0.5)
