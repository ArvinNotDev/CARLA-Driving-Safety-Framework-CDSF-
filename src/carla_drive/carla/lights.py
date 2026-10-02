"""Small state owner for the ego vehicle's CARLA light flags."""

from __future__ import annotations

from enum import Enum
import math
from typing import Any


class HeadlightMode(str, Enum):
    OFF = "Off"
    LOW = "Low beam"
    HIGH = "High beam"


class EgoLightState:
    """Keeps manual light controls together and composes one cached CARLA flag."""

    BRAKE_THRESHOLD = 0.05
    _HEADLIGHT_SEQUENCE = (HeadlightMode.OFF, HeadlightMode.LOW, HeadlightMode.HIGH)

    def __init__(self) -> None:
        self.headlights = HeadlightMode.OFF
        self.left_indicator = False
        self.right_indicator = False
        self.braking = False
        self.reversing = False
        self._revision = 0
        self._cached_revision = -1
        self._cached_enum: Any = None
        self._cached_state: Any = None

    def set_brake_input(self, value: float) -> bool:
        braking = math.isfinite(value) and value >= self.BRAKE_THRESHOLD
        if braking == self.braking:
            return False
        self.braking = braking
        self._invalidate()
        return True

    def set_reverse(self, reversing: bool) -> bool:
        reversing = bool(reversing)
        if reversing == self.reversing:
            return False
        self.reversing = reversing
        self._invalidate()
        return True

    def cycle_headlights(self) -> HeadlightMode:
        current = self._HEADLIGHT_SEQUENCE.index(self.headlights)
        self.headlights = self._HEADLIGHT_SEQUENCE[(current + 1) % len(self._HEADLIGHT_SEQUENCE)]
        self._invalidate()
        return self.headlights

    def toggle_indicator(self, side: str) -> bool:
        if side == "left":
            self.left_indicator = not self.left_indicator
            self.right_indicator = False
            active = self.left_indicator
        elif side == "right":
            self.right_indicator = not self.right_indicator
            self.left_indicator = False
            active = self.right_indicator
        else:
            raise ValueError("Indicator side must be 'left' or 'right'.")
        self._invalidate()
        return active

    def clear_indicators(self) -> bool:
        if not self.left_indicator and not self.right_indicator:
            return False
        self.left_indicator = False
        self.right_indicator = False
        self._invalidate()
        return True

    def to_carla_state(self, light_flags: Any) -> Any:
        if self._cached_revision == self._revision and self._cached_enum is light_flags:
            return self._cached_state

        state = light_flags.NONE
        if self.headlights is HeadlightMode.LOW:
            state |= light_flags.LowBeam
        elif self.headlights is HeadlightMode.HIGH:
            state |= light_flags.HighBeam
        if self.left_indicator:
            state |= light_flags.LeftBlinker
        if self.right_indicator:
            state |= light_flags.RightBlinker
        if self.braking:
            state |= light_flags.Brake
        if self.reversing:
            state |= light_flags.Reverse

        self._cached_enum = light_flags
        self._cached_state = light_flags(int(state))
        self._cached_revision = self._revision
        return self._cached_state

    def _invalidate(self) -> None:
        self._revision += 1
