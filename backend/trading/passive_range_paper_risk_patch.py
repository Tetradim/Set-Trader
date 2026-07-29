"""Apply the live pre-trade risk gateway to passive paper entries."""

from __future__ import annotations

import deps
from trading import passive_range_patch as passive


_ORIGINAL_ARM_BUY = passive._arm_buy


async def _arm_buy_with_paper_risk(
    self,
    *,
    ticker_doc: dict,
    state: dict,
    buy_target: float,
    effective_power: float,
) -> None:
    if passive._is_paper(self, ticker_doc) and hasattr(self, "pre_trade_check"):
        quantity = passive._quantity_for_power(
            effective_power,
            buy_target,
            bool(ticker_doc.get("passive_fractional_shares", False)),
        )
        if quantity <= 0:
            return
        allowed, reason = await self.pre_trade_check(
            state.get("symbol") or ticker_doc.get("symbol") or "",
            "BUY",
            quantity,
            buy_target,
        )
        if not allowed:
            state["last_risk_block_reason"] = str(reason or "pre-trade risk check failed")
            await passive._persist_state(state)
            deps.logger.warning(
                "Passive paper BUY blocked for %s: %s",
                state.get("symbol") or ticker_doc.get("symbol"),
                reason,
            )
            return

    await _ORIGINAL_ARM_BUY(
        self,
        ticker_doc=ticker_doc,
        state=state,
        buy_target=buy_target,
        effective_power=effective_power,
    )


passive._arm_buy = _arm_buy_with_paper_risk
