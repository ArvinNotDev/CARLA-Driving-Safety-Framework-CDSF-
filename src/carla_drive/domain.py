"""Small values shared by the driving loop and presentation layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CameraMode(str, Enum):
    COCKPIT = "Cockpit"
    CHASE = "Chase"
    OVERHEAD = "Overhead"


@dataclass(frozen=True)
class ControlInput:
    steering: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0
    handbrake: bool = False
    pressed: frozenset[str] = frozenset()


@dataclass(frozen=True)
class VehicleSnapshot:
    speed_kmh: float = 0.0
    gear: str = "D"
    reverse: bool = False
    steering: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0


@dataclass(frozen=True)
class RearDistanceState:
    left_m: float | None = None
    center_m: float | None = None
    right_m: float | None = None
    sampled_at: float = 0.0

    @property
    def closest_m(self) -> float | None:
        distances = [distance for distance in (self.left_m, self.center_m, self.right_m) if distance is not None]
        return min(distances) if distances else None


@dataclass(frozen=True)
class DrivingSnapshot:
    vehicle: VehicleSnapshot = field(default_factory=VehicleSnapshot)
    rear_distance: RearDistanceState = field(default_factory=RearDistanceState)
    camera_mode: CameraMode = CameraMode.CHASE
