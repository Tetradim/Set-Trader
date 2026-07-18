"""Shared Edge entry-price and execution-cost policy for Pulse.

The policy is evaluated twice:

* when Pulse accepts an Edge handoff, before ticker capital is mutated; and
* immediately before live broker order placement against fresh executable quotes.

This keeps a profitable Edge thesis from becoming an unprofitable Pulse fill.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


class EdgeEntryPolicyError(RuntimeError):
    """Structured profitability veto that can cross the handoff boundary."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        execution_code: str,
        status: str = "rejected",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.execution_code = execution_code
        self.status = status
        self.details = dict(details or {})


def finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def positive(value: Any) -> float | None:
    number = finite(value)
    return number if number > 0 else None


def _first_positive(*values: Any) -> float | None:
    for value in values:
        number = positive(value)
        if number is not None:
            return number
    return None


def normalise_entry_policy(intent: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Merge the typed intent with trade-card/lifecycle compatibility fields."""
    intent = intent if isinstance(intent, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    raw = intent.get("entry_policy") if isinstance(intent.get("entry_policy"), dict) else {}
    card = metadata.get("trade_card") if isinstance(metadata.get("trade_card"), dict) else {}
    lifecycle = metadata.get("strategy_lifecycle") if isinstance(metadata.get("strategy_lifecycle"), dict) else {}
    card_meta = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}

    reference_price = _first_positive(
        raw.get("reference_price"),
        raw.get("ideal_entry_price"),
        card.get("entry_price"),
        lifecycle.get("entry_price"),
        metadata.get("entry_price"),
        metadata.get("price"),
    )
    maximum_entry_price = _first_positive(
        raw.get("maximum_entry_price"),
        card.get("maximum_entry_price"),
        lifecycle.get("maximum_entry_price"),
        metadata.get("maximum_entry_price"),
    )
    expected_value_pct = finite(
        raw.get("expected_value_pct"),
        finite(metadata.get("expected_value_pct"), finite(card.get("expected_value_pct"))),
    )
    estimated_cost_pct = max(
        0.0,
        finite(
            raw.get("estimated_cost_pct"),
            finite(metadata.get("estimated_cost_pct"), finite(card_meta.get("estimated_cost_pct"))),
        ),
    )
    maximum_execution_cost_pct = _first_positive(
        raw.get("maximum_execution_cost_pct"),
        raw.get("cost_allowance_pct"),
        metadata.get("maximum_execution_cost_pct"),
        metadata.get("execution_cost_allowance_pct"),
        card_meta.get("maximum_execution_cost_pct"),
    )
    minimum_remaining_expected_value_pct = max(
        0.0,
        finite(
            raw.get("minimum_remaining_expected_value_pct"),
            finite(metadata.get("minimum_remaining_expected_value_pct"), 0.0),
        ),
    )
    maximum_spread_pct = _first_positive(
        raw.get("maximum_spread_pct"),
        metadata.get("maximum_spread_pct"),
    )

    return {
        "contract_version": "edge.entry_policy.v1",
        "reference_price": reference_price,
        "maximum_entry_price": maximum_entry_price,
        "expected_value_pct": round(expected_value_pct, 6),
        "estimated_cost_pct": round(estimated_cost_pct, 6),
        "maximum_execution_cost_pct": maximum_execution_cost_pct,
        "minimum_remaining_expected_value_pct": round(minimum_remaining_expected_value_pct, 6),
        "maximum_spread_pct": maximum_spread_pct,
        "position_id": str(raw.get("position_id") or metadata.get("position_id") or card.get("position_id") or ""),
        "card_id": str(raw.get("card_id") or metadata.get("card_id") or card.get("card_id") or ""),
        "trigger_state": str(raw.get("trigger_state") or metadata.get("entry_trigger_state") or ""),
    }


def execution_cost_metrics(
    policy: Dict[str, Any],
    *,
    observed_price: float,
    bid: float | None = None,
    ask: float | None = None,
    fee_bps: float = 0.0,
    slippage_buffer_bps: float = 0.0,
) -> Dict[str, Any]:
    """Estimate all-in round-trip execution cost conservatively for a long entry."""
    observed = positive(observed_price)
    if observed is None:
        raise EdgeEntryPolicyError(
            "Pulse could not establish a positive executable entry price.",
            reason="entry_price_unavailable",
            execution_code="ENTRY_DEFERRED_PRICE_UNAVAILABLE",
            status="deferred",
        )

    bid_value, ask_value = positive(bid), positive(ask)
    if bid_value is not None and ask_value is not None and ask_value < bid_value:
        raise EdgeEntryPolicyError(
            f"Non-executable quote bid={bid_value:.6f} ask={ask_value:.6f}.",
            reason="entry_deferred_poor_liquidity",
            execution_code="ENTRY_DEFERRED_POOR_LIQUIDITY",
            status="deferred",
            details={"bid": bid_value, "ask": ask_value},
        )

    executable = ask_value or observed
    reference = positive(policy.get("reference_price")) or observed
    spread_pct = 0.0
    if bid_value is not None and ask_value is not None:
        mid = (bid_value + ask_value) / 2.0
        spread_pct = ((ask_value - bid_value) / mid) * 100.0 if mid > 0 else 0.0
    adverse_move_pct = max(0.0, ((executable - reference) / reference) * 100.0) if reference > 0 else 0.0
    fee_pct = max(0.0, finite(fee_bps)) / 100.0
    slippage_buffer_pct = max(0.0, finite(slippage_buffer_bps)) / 100.0

    # A last/mid reference already includes roughly half the spread. Taking the
    # maximum avoids double counting while remaining conservative.
    estimated_execution_cost_pct = max(spread_pct, adverse_move_pct) + fee_pct + slippage_buffer_pct
    baseline_cost_pct = max(0.0, finite(policy.get("estimated_cost_pct")))
    expected_value_pct = finite(policy.get("expected_value_pct"))
    incremental_cost_pct = max(0.0, estimated_execution_cost_pct - baseline_cost_pct)
    remaining_expected_value_pct = expected_value_pct - incremental_cost_pct

    return {
        "reference_price": round(reference, 8),
        "observed_price": round(observed, 8),
        "executable_price": round(executable, 8),
        "bid": round(bid_value, 8) if bid_value is not None else None,
        "ask": round(ask_value, 8) if ask_value is not None else None,
        "spread_pct": round(spread_pct, 6),
        "adverse_move_pct": round(adverse_move_pct, 6),
        "fee_pct": round(fee_pct, 6),
        "slippage_buffer_pct": round(slippage_buffer_pct, 6),
        "estimated_execution_cost_pct": round(estimated_execution_cost_pct, 6),
        "baseline_estimated_cost_pct": round(baseline_cost_pct, 6),
        "incremental_cost_pct": round(incremental_cost_pct, 6),
        "remaining_expected_value_pct": round(remaining_expected_value_pct, 6),
    }


def validate_long_entry(
    policy: Dict[str, Any],
    *,
    observed_price: float,
    bid: float | None = None,
    ask: float | None = None,
    fee_bps: float = 0.0,
    slippage_buffer_bps: float = 0.0,
) -> Dict[str, Any]:
    """Validate maximum price, liquidity and remaining net expectancy."""
    metrics = execution_cost_metrics(
        policy,
        observed_price=observed_price,
        bid=bid,
        ask=ask,
        fee_bps=fee_bps,
        slippage_buffer_bps=slippage_buffer_bps,
    )
    executable = metrics["executable_price"]
    maximum_entry = positive(policy.get("maximum_entry_price"))
    if maximum_entry is not None and executable > maximum_entry:
        raise EdgeEntryPolicyError(
            f"Executable entry {executable:.6f} exceeds Edge maximum {maximum_entry:.6f}.",
            reason="maximum_entry_price_exceeded",
            execution_code="ENTRY_REJECTED_MAXIMUM_ENTRY_PRICE",
            details={**metrics, "maximum_entry_price": maximum_entry},
        )

    maximum_spread = positive(policy.get("maximum_spread_pct"))
    if maximum_spread is not None and metrics["spread_pct"] > maximum_spread:
        raise EdgeEntryPolicyError(
            f"Spread {metrics['spread_pct']:.6f}% exceeds Edge allowance {maximum_spread:.6f}%.",
            reason="entry_deferred_poor_liquidity",
            execution_code="ENTRY_DEFERRED_POOR_LIQUIDITY",
            status="deferred",
            details={**metrics, "maximum_spread_pct": maximum_spread},
        )

    maximum_cost = positive(policy.get("maximum_execution_cost_pct"))
    if maximum_cost is not None and metrics["estimated_execution_cost_pct"] > maximum_cost:
        raise EdgeEntryPolicyError(
            f"Estimated execution cost {metrics['estimated_execution_cost_pct']:.6f}% exceeds allowance {maximum_cost:.6f}%.",
            reason="entry_rejected_slippage_limit",
            execution_code="ENTRY_REJECTED_SLIPPAGE_LIMIT",
            details={**metrics, "maximum_execution_cost_pct": maximum_cost},
        )

    minimum_remaining = max(0.0, finite(policy.get("minimum_remaining_expected_value_pct")))
    if policy.get("expected_value_pct") is not None and metrics["remaining_expected_value_pct"] < minimum_remaining:
        raise EdgeEntryPolicyError(
            f"Execution would leave {metrics['remaining_expected_value_pct']:.6f}% expected value, below {minimum_remaining:.6f}%.",
            reason="entry_rejected_insufficient_remaining_edge",
            execution_code="ENTRY_REJECTED_EXPECTED_VALUE_ERODED",
            details={**metrics, "minimum_remaining_expected_value_pct": minimum_remaining},
        )

    return {**metrics, "accepted": True}
