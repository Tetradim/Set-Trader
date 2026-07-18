"""Paper-only stateful scalp-follow bracket controller.

This module intentionally does not submit orders or mutate ticker-card configuration.
It keeps a runtime center while flat and creates an immutable position bracket at
entry. Integration with the live trading engine must remain opt-in until replay
and broker-sandbox validation are complete.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from statistics import median
from typing import Deque, Optional


class ScalpState(str, Enum):
    RANGE_ACTIVE = "range_active"
    TREND_PAUSE = "trend_pause"
    POSITION_ACTIVE = "position_active"
    EXIT_COOLDOWN = "exit_cooldown"


class ScalpAction(str, Enum):
    HOLD = "hold"
    RECENTER = "recenter"
    PAUSE = "pause"
    RESUME = "resume"
    BUY_READY = "buy_ready"
    TARGET_EXIT = "target_exit"
    STOP_EXIT = "stop_exit"
    TIME_EXIT = "time_exit"
    END_OF_DAY_EXIT = "end_of_day_exit"
    TIGHTEN_STOP = "tighten_stop"


@dataclass(frozen=True)
class ScalpFollowConfig:
    half_width: float
    recenter_trigger: float
    up_confirmations: int = 3
    down_confirmations: int = 5
    recenter_cooldown_seconds: int = 900
    max_recenters_per_hour: int = 4
    trend_pause_multiple: float = 2.0
    risk_multiple: float = 1.25
    weak_review_seconds: int = 1200
    weak_mfe_fraction: float = 0.25
    tightened_stop_r: float = 0.50
    max_hold_seconds: int = 3600
    win_cooldown_seconds: int = 300
    loss_cooldown_seconds: int = 900

    def __post_init__(self) -> None:
        if self.half_width <= 0:
            raise ValueError("half_width must be positive")
        if self.recenter_trigger < self.half_width:
            raise ValueError("recenter_trigger must be at least half_width")
        if self.up_confirmations < 1 or self.down_confirmations < 1:
            raise ValueError("confirmation counts must be positive")
        if self.risk_multiple <= 0:
            raise ValueError("risk_multiple must be positive")
        if self.max_hold_seconds <= 0:
            raise ValueError("max_hold_seconds must be positive")


@dataclass(frozen=True)
class PositionBracket:
    entry: float
    target: float
    stop: float
    reward: float
    opened_at: datetime
    center_generation: int


@dataclass(frozen=True)
class ScalpDecision:
    action: ScalpAction
    state: ScalpState
    reason: str
    center: float
    buy_price: float
    sell_price: float
    stop_price: Optional[float] = None
    direction: Optional[str] = None
    generation: int = 0


@dataclass
class ScalpFollowRuntime:
    center: float
    state: ScalpState = ScalpState.RANGE_ACTIVE
    generation: int = 0
    up_count: int = 0
    down_count: int = 0
    last_recenter_at: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    position: Optional[PositionBracket] = None
    position_high: float = 0.0
    weak_tightened: bool = False
    recent_closes: Deque[float] = field(default_factory=lambda: deque(maxlen=7))
    recenter_times: Deque[datetime] = field(default_factory=deque)


class ScalpFollowController:
    """Discrete, hysteretic scalp bracket that never follows price tick-for-tick."""

    def __init__(self, config: ScalpFollowConfig, initial_center: float):
        if initial_center <= 0:
            raise ValueError("initial_center must be positive")
        self.config = config
        self.runtime = ScalpFollowRuntime(center=round(initial_center, 2))

    @property
    def buy_price(self) -> float:
        return round(self.runtime.center - self.config.half_width, 2)

    @property
    def sell_price(self) -> float:
        return round(self.runtime.center + self.config.half_width, 2)

    def _decision(
        self,
        action: ScalpAction,
        reason: str,
        *,
        direction: Optional[str] = None,
        stop_price: Optional[float] = None,
    ) -> ScalpDecision:
        return ScalpDecision(
            action=action,
            state=self.runtime.state,
            reason=reason,
            center=self.runtime.center,
            buy_price=self.buy_price,
            sell_price=self.sell_price,
            stop_price=stop_price,
            direction=direction,
            generation=self.runtime.generation,
        )

    def observe_flat(
        self,
        *,
        timestamp: datetime,
        price: float,
        atr: float = 0.0,
        reentry_cooldown_active: bool = False,
    ) -> ScalpDecision:
        """Observe a flat-position price and possibly move the zone once.

        The controller never re-centers while an open position exists or during
        exit/re-entry cooldown. Upward migration requires consecutive closes;
        downward migration also requires the latest three closes to stop making
        new lows.
        """
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if price <= 0:
            raise ValueError("price must be positive")
        if self.runtime.position is not None:
            return self._decision(ScalpAction.HOLD, "position_bracket_frozen")

        self.runtime.recent_closes.append(float(price))
        if reentry_cooldown_active or (
            self.runtime.cooldown_until is not None
            and timestamp < self.runtime.cooldown_until
        ):
            self.runtime.state = ScalpState.EXIT_COOLDOWN
            return self._decision(ScalpAction.HOLD, "exit_cooldown")

        if self.runtime.state is ScalpState.EXIT_COOLDOWN:
            self.runtime.state = ScalpState.RANGE_ACTIVE

        trigger = max(self.config.recenter_trigger, max(0.0, atr))
        distance = price - self.runtime.center

        while self.runtime.recenter_times and (
            timestamp - self.runtime.recenter_times[0]
        ).total_seconds() > 3600:
            self.runtime.recenter_times.popleft()

        if len(self.runtime.recenter_times) >= self.config.max_recenters_per_hour:
            self.runtime.state = ScalpState.TREND_PAUSE
            return self._decision(ScalpAction.PAUSE, "recenter_rate_limit")

        if abs(distance) >= self.config.trend_pause_multiple * trigger:
            self.runtime.state = ScalpState.TREND_PAUSE

        if self.runtime.state is ScalpState.TREND_PAUSE:
            if len(self.runtime.recent_closes) < 5:
                return self._decision(
                    ScalpAction.HOLD, "trend_pause_waiting_for_range"
                )
            recent = list(self.runtime.recent_closes)[-5:]
            stable = (
                max(recent) - min(recent)
                <= max(2 * self.config.half_width, 0.75 * max(atr, 0.0))
                and abs(recent[-1] - recent[0])
                <= max(self.config.half_width, 0.5 * max(atr, 0.0))
            )
            if not stable:
                return self._decision(ScalpAction.HOLD, "trend_pause_unstable")
            return self._recenter(timestamp, median(recent), "trend_stabilized")

        upper = self.runtime.center + trigger
        lower = self.runtime.center - trigger
        self.runtime.up_count = self.runtime.up_count + 1 if price >= upper else 0
        self.runtime.down_count = (
            self.runtime.down_count + 1 if price <= lower else 0
        )

        if not self._recenter_cooldown_elapsed(timestamp):
            return self._entry_decision(price)

        recent = list(self.runtime.recent_closes)
        if self.runtime.up_count >= self.config.up_confirmations and len(recent) >= 5:
            recent5 = recent[-5:]
            if median(recent5) >= upper:
                return self._recenter(
                    timestamp, median(recent5), "confirmed_up_migration"
                )

        if (
            self.runtime.down_count >= self.config.down_confirmations
            and len(recent) >= 5
        ):
            recent5 = recent[-5:]
            last3 = recent5[-3:]
            stopped_making_lows = (
                min(range(len(last3)), key=last3.__getitem__) == 0
                and last3[-1] >= last3[-2]
            )
            if median(recent5) <= lower and stopped_making_lows:
                return self._recenter(
                    timestamp, median(recent5), "confirmed_down_migration"
                )

        return self._entry_decision(price)

    def _entry_decision(self, price: float) -> ScalpDecision:
        if self.runtime.state is ScalpState.RANGE_ACTIVE and price <= self.buy_price:
            return self._decision(
                ScalpAction.BUY_READY, "price_at_or_below_buy_zone"
            )
        return self._decision(ScalpAction.HOLD, "range_active")

    def _recenter_cooldown_elapsed(self, timestamp: datetime) -> bool:
        if self.runtime.last_recenter_at is None:
            return True
        return (
            timestamp - self.runtime.last_recenter_at
        ).total_seconds() >= self.config.recenter_cooldown_seconds

    def _recenter(
        self, timestamp: datetime, proposed_center: float, reason: str
    ) -> ScalpDecision:
        old_center = self.runtime.center
        increment = min(0.25, max(0.01, self.config.half_width / 2))
        center = round(round(proposed_center / increment) * increment, 2)
        if abs(center - old_center) < self.config.half_width:
            self.runtime.state = ScalpState.RANGE_ACTIVE
            return self._decision(
                ScalpAction.HOLD, "stable_range_inside_existing_zone"
            )
        direction = "UP" if center > old_center else "DOWN"
        self.runtime.center = center
        self.runtime.generation += 1
        self.runtime.last_recenter_at = timestamp
        self.runtime.recenter_times.append(timestamp)
        self.runtime.up_count = 0
        self.runtime.down_count = 0
        self.runtime.state = ScalpState.RANGE_ACTIVE
        return self._decision(
            ScalpAction.RECENTER, reason, direction=direction
        )

    def open_position(
        self, *, timestamp: datetime, entry_price: float
    ) -> PositionBracket:
        """Freeze an atomic target and stop at the actual fill price."""
        if self.runtime.position is not None:
            raise ValueError("position already open")
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")
        target = self.sell_price
        if target <= entry_price:
            raise ValueError("sell target must be above entry")
        reward = target - entry_price
        stop = max(
            0.01,
            round(entry_price - self.config.risk_multiple * reward, 2),
        )
        bracket = PositionBracket(
            entry=round(entry_price, 2),
            target=round(target, 2),
            stop=stop,
            reward=round(reward, 4),
            opened_at=timestamp,
            center_generation=self.runtime.generation,
        )
        self.runtime.position = bracket
        self.runtime.position_high = bracket.entry
        self.runtime.weak_tightened = False
        self.runtime.state = ScalpState.POSITION_ACTIVE
        return bracket

    def observe_position(
        self,
        *,
        timestamp: datetime,
        price: float,
        session_exit_due: bool = False,
    ) -> ScalpDecision:
        position = self.runtime.position
        if position is None:
            raise ValueError("no open position")
        self.runtime.position_high = max(self.runtime.position_high, price)
        held_seconds = (timestamp - position.opened_at).total_seconds()
        current_stop = position.stop

        if price <= current_stop:
            return self._decision(
                ScalpAction.STOP_EXIT,
                "frozen_stop_hit",
                stop_price=current_stop,
            )
        if price >= position.target:
            return self._decision(
                ScalpAction.TARGET_EXIT,
                "frozen_target_hit",
                stop_price=current_stop,
            )
        if session_exit_due:
            return self._decision(
                ScalpAction.END_OF_DAY_EXIT,
                "intraday_strategy_session_exit",
                stop_price=current_stop,
            )
        if held_seconds >= self.config.max_hold_seconds:
            return self._decision(
                ScalpAction.TIME_EXIT,
                "maximum_holding_time",
                stop_price=current_stop,
            )

        if (
            not self.runtime.weak_tightened
            and held_seconds >= self.config.weak_review_seconds
        ):
            mfe = self.runtime.position_high - position.entry
            if mfe < self.config.weak_mfe_fraction * position.reward:
                tightened = round(
                    position.entry
                    - self.config.tightened_stop_r * position.reward,
                    2,
                )
                if tightened > current_stop:
                    position = PositionBracket(
                        entry=position.entry,
                        target=position.target,
                        stop=tightened,
                        reward=position.reward,
                        opened_at=position.opened_at,
                        center_generation=position.center_generation,
                    )
                    self.runtime.position = position
                    current_stop = tightened
                self.runtime.weak_tightened = True
                return self._decision(
                    ScalpAction.TIGHTEN_STOP,
                    "weak_trade_failed_to_reach_mfe_threshold",
                    stop_price=current_stop,
                )

        return self._decision(
            ScalpAction.HOLD, "position_active", stop_price=current_stop
        )

    def close_position(self, *, timestamp: datetime, profitable: bool) -> None:
        if self.runtime.position is None:
            raise ValueError("no open position")
        cooldown = (
            self.config.win_cooldown_seconds
            if profitable
            else self.config.loss_cooldown_seconds
        )
        self.runtime.position = None
        self.runtime.position_high = 0.0
        self.runtime.weak_tightened = False
        self.runtime.cooldown_until = timestamp + timedelta(seconds=cooldown)
        self.runtime.state = ScalpState.EXIT_COOLDOWN
        self.runtime.up_count = 0
        self.runtime.down_count = 0
