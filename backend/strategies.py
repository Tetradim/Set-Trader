"""Preset trading strategies."""
from schemas import PresetStrategy

PRESET_STRATEGIES = {
    "conservative_1y": PresetStrategy(
        name="Conservative 1-Year Bracket",
        avg_days=365, buy_offset=-5.0, buy_percent=True,
        sell_offset=8.0, sell_percent=True, stop_offset=-10.0,
        stop_percent=True, trailing_enabled=False, trailing_percent=3.0
    ),
    "aggressive_monthly": PresetStrategy(
        name="Aggressive Monthly Dip-Buy",
        avg_days=30, buy_offset=-2.0, buy_percent=True,
        sell_offset=4.0, sell_percent=True, stop_offset=-5.0,
        stop_percent=True, trailing_enabled=True, trailing_percent=1.5
    ),
    "swing_trader": PresetStrategy(
        name="Swing Trader",
        avg_days=14, buy_offset=-1.5, buy_percent=True,
        sell_offset=3.0, sell_percent=True, stop_offset=-3.0,
        stop_percent=True, trailing_enabled=True, trailing_percent=2.0
    ),
}
