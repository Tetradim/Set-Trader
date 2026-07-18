from brokers.base import BrokerOrder, OrderSide, OrderType
from trading.edge_execution_attribution_patch import mark_post_fill_movement
from trading.edge_execution_style import execution_attribution, select_execution_style


def _policy(style, **overrides):
    value = {
        "reference_price": 100.0,
        "ideal_entry_price": 100.0,
        "maximum_entry_price": 101.0,
        "execution_style_policy": {
            "contract_version": "edge.execution_style.v1",
            "preferred_style": style,
            "allowed_styles": ["passive_limit", "timed_limit", "breakout_stop_limit"],
            "timeout_seconds": 5,
            "passive_offset_bps": 2,
            "aggressive_limit_buffer_bps": 4,
            "stop_trigger_price": 100.20,
            "post_fill_horizons_seconds": [30, 60, 300],
            "orb_confirmation": {"direction": "bullish"},
            "squeeze_state": "triggering",
        },
    }
    value.update(overrides)
    return value


def test_passive_limit_joins_bid_without_crossing_reference():
    selected = select_execution_style(_policy("passive_limit"), bid=99.90, ask=100.10)
    assert selected["style"] == "passive_limit"
    assert selected["order_type"] == "LIMIT"
    assert 99.90 <= selected["limit_price"] <= 100.0
    assert selected["timeout_seconds"] is None


def test_timed_limit_crosses_only_inside_edge_maximum():
    selected = select_execution_style(_policy("timed_limit"), bid=99.95, ask=100.10)
    assert selected["style"] == "timed_limit"
    assert selected["order_type"] == "LIMIT"
    assert selected["timeout_seconds"] == 5
    assert 100.10 <= selected["limit_price"] <= 101.0


def test_breakout_stop_limit_uses_orb_trigger_and_capped_limit():
    selected = select_execution_style(_policy("breakout_stop_limit"), bid=100.05, ask=100.15)
    assert selected["style"] == "breakout_stop_limit"
    assert selected["order_type"] == "STOP_LIMIT"
    assert selected["stop_price"] == 100.20
    assert selected["limit_price"] <= 101.0
    assert selected["timeout_seconds"] == 5


def test_broker_order_carries_style_and_timeout():
    order = BrokerOrder(
        symbol="GME",
        side=OrderSide.BUY,
        order_type=OrderType.STOP_LIMIT,
        quantity=10,
        limit_price=100.50,
        stop_price=100.20,
        timeout_seconds=5,
        execution_style="breakout_stop_limit",
    )
    assert order.execution_style == "breakout_stop_limit"
    assert order.timeout_seconds == 5
    assert order.order_type == OrderType.STOP_LIMIT


def test_attribution_distinguishes_fill_quality_and_missed_fill():
    selection = select_execution_style(_policy("timed_limit"), bid=99.95, ask=100.10)
    filled = execution_attribution(
        selection,
        status="filled",
        fill_price=100.12,
        filled_quantity=10,
        post_fill_prices={"30": 100.50},
    )
    missed = execution_attribution(selection, status="canceled")

    assert filled["missed_fill"] is False
    assert filled["fill_slippage_bps"] > 0
    assert filled["post_fill_movement"]["30"]["move_bps"] > 0
    assert missed["missed_fill"] is True


def test_post_fill_watch_marks_each_due_horizon_once():
    watch = {
        "fill_price": 100.0,
        "filled_at_epoch": 1_000.0,
        "horizons_seconds": [30, 60, 300],
        "marks": {},
    }
    watch, changed = mark_post_fill_movement(watch, current_price=101.0, now_epoch=1_061.0)
    assert changed is True
    assert set(watch["marks"]) == {"30", "60"}
    assert watch["marks"]["30"]["move_bps"] == 100.0
    assert watch["complete"] is False

    watch, changed = mark_post_fill_movement(watch, current_price=102.0, now_epoch=1_301.0)
    assert changed is True
    assert set(watch["marks"]) == {"30", "60", "300"}
    assert watch["complete"] is True
