"""Bind live cycle accounting to the un-normalized base profit ledger method."""
from trading import live_cycle_capital_patch as cycle
from trading import live_truth_patch as live_truth


# live_truth._update_profit_from_recorded_trade intentionally replaces caller
# P&L with the trade's gross value. Cycle accounting has already calculated net
# P&L after broker fees, so it must call the original bookkeeping method directly.
cycle._current_update_profit = live_truth._original_update_profit
