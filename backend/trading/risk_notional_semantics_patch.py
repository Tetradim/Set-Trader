"""Normalize legacy dollar-labeled position limits to notional exposure caps.

Pulse's default risk configuration historically populated ``max_position_size``
with comments and values expressed in dollars, while the risk checker compared
that field to share quantity. That makes a single value mean radically different
risk for a sub-dollar stock and an expensive stock.

The explicit ``max_notional`` field is the correct unit for those defaults. This
compatibility patch runs before ``TradingEngine`` initializes its limits:

* symbol-level legacy dollar position limits become notional limits;
* portfolio-level ``max_position_size`` is disabled because a portfolio bucket
  cannot represent one symbol's share position, while its existing portfolio
  notional limit and symbol notional limits remain active.
"""

from __future__ import annotations

from risk_controls import ExposureLimit, RiskControls


_ORIGINAL_ADD_EXPOSURE_LIMIT = RiskControls.add_exposure_limit


def _add_exposure_limit_with_notional_units(
    self: RiskControls,
    limit: ExposureLimit,
):
    if limit.level == "symbol" and limit.max_position_size > 0 and limit.max_notional <= 0:
        limit.max_notional = float(limit.max_position_size)
        limit.max_position_size = 0.0
    elif limit.level == "portfolio" and limit.max_position_size > 0:
        # Portfolio current_position aggregates shares across unlike instruments
        # and therefore has no coherent unit. Portfolio notional and per-symbol
        # notional limits remain the enforceable controls.
        limit.max_position_size = 0.0
    return _ORIGINAL_ADD_EXPOSURE_LIMIT(self, limit)


RiskControls.add_exposure_limit = _add_exposure_limit_with_notional_units
