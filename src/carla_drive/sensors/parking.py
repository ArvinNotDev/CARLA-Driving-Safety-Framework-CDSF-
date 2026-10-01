"""Pure parking-indicator and beep-timing calculations."""

from __future__ import annotations

from carla_drive.domain import RearDistanceState


def parking_fill(distance_m: float | None, sensor_range_m: float) -> float:
    """Return [0, 1] fill, where full means an obstacle is at the vehicle."""
    if distance_m is None or sensor_range_m <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - distance_m / sensor_range_m))


def parking_side_fills(state: RearDistanceState, sensor_range_m: float) -> tuple[float, float]:
    """Center trace affects both sides; side traces affect their own half."""
    def nearest(*distances: float | None) -> float | None:
        visible = [distance for distance in distances if distance is not None]
        return min(visible) if visible else None

    return (
        parking_fill(nearest(state.left_m, state.center_m), sensor_range_m),
        parking_fill(nearest(state.right_m, state.center_m), sensor_range_m),
    )


def beep_interval_ms(
    distance_m: float | None,
    warning_distance_m: float,
    critical_distance_m: float,
    slowest_ms: int,
    fastest_ms: int,
) -> int | None:
    """Return the distance-dependent beep period, or None outside warning range."""
    if distance_m is None or distance_m > warning_distance_m:
        return None
    if distance_m <= critical_distance_m:
        return fastest_ms
    span = warning_distance_m - critical_distance_m
    ratio = (warning_distance_m - distance_m) / span
    return round(slowest_ms + (fastest_ms - slowest_ms) * ratio)
