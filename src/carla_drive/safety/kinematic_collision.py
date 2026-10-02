"""Detect strong impact-like events from short-term vehicle motion history.

This is a kinematic estimate, not CARLA ground truth. It compares longitudinal
deceleration against a brake-aware envelope and confirms short anomalies using
the positive rate of change of deceleration (jerk).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math

from carla_drive.config import KinematicCollisionConfig


@dataclass(frozen=True)
class MotionSample:
    timestamp_s: float
    longitudinal_velocity_mps: float
    speed_mps: float
    acceleration_mps2: float
    deceleration_mps2: float
    jerk_mps3: float
    brake_input: float
    throttle_input: float


@dataclass(frozen=True)
class CollisionEvent:
    detected: bool
    timestamp_s: float
    pre_impact_speed_mps: float
    post_impact_speed_mps: float
    peak_deceleration_mps2: float
    peak_jerk_mps3: float
    brake_input: float
    throttle_input: float
    impact_score: float
    reason: str


@dataclass(frozen=True)
class _ImpactEvidence:
    sample: MotionSample
    speed_before_mps: float
    excess_deceleration_mps2: float


class KinematicCollisionDetector:
    """Infer abrupt longitudinal speed losses without collision-specific sensors."""

    _HISTORY_SAMPLES = 8
    _COAST_DECELERATION_MPS2 = 1.0
    _MAX_SAMPLE_GAP_SECONDS = 0.25

    def __init__(self, config: KinematicCollisionConfig | None = None):
        self.config = config or KinematicCollisionConfig()
        self.history: deque[MotionSample] = deque(maxlen=self._HISTORY_SAMPLES)
        self._pending: deque[_ImpactEvidence] = deque(maxlen=4)
        self._last_reverse: bool | None = None
        self._cooldown_until_s: float | None = None
        self._rearm_required = False

    def reset(self) -> None:
        """Drop motion, confirmation, and cooldown state at a vehicle reset."""
        self.history.clear()
        self._pending.clear()
        self._last_reverse = None
        self._cooldown_until_s = None
        self._rearm_required = False

    def update(
        self,
        timestamp_s: float,
        longitudinal_velocity_mps: float,
        brake_input: float,
        throttle_input: float,
        reverse: bool = False,
    ) -> CollisionEvent | None:
        """Consume one simulation-time sample and return a newly detected event."""
        if not self.config.enabled:
            return None
        try:
            values = tuple(float(value) for value in (timestamp_s, longitudinal_velocity_mps, brake_input, throttle_input))
        except (TypeError, ValueError, OverflowError):
            self.reset()
            return None
        if not all(math.isfinite(value) for value in values):
            self.reset()
            return None
        timestamp_s, longitudinal_velocity_mps, brake_input, throttle_input = values

        reverse = bool(reverse)
        if self._last_reverse is not None and reverse != self._last_reverse:
            self.reset()
        self._last_reverse = reverse

        brake_input = max(0.0, min(1.0, brake_input))
        throttle_input = max(0.0, min(1.0, throttle_input))
        directed_velocity = longitudinal_velocity_mps * (-1.0 if reverse else 1.0)
        speed_mps = abs(directed_velocity)

        if not self.history:
            self._append_baseline(timestamp_s, longitudinal_velocity_mps, speed_mps, brake_input, throttle_input)
            return None

        previous = self.history[-1]
        dt = timestamp_s - previous.timestamp_s
        if dt == 0.0:
            return None
        if dt < 0.0 or dt > self._MAX_SAMPLE_GAP_SECONDS:
            self.reset()
            self._last_reverse = reverse
            self._append_baseline(timestamp_s, longitudinal_velocity_mps, speed_mps, brake_input, throttle_input)
            return None

        acceleration = (speed_mps - previous.speed_mps) / dt
        deceleration = max(0.0, -acceleration)
        jerk = max(0.0, (deceleration - previous.deceleration_mps2) / dt)

        sample = MotionSample(
            timestamp_s=timestamp_s,
            longitudinal_velocity_mps=longitudinal_velocity_mps,
            speed_mps=speed_mps,
            acceleration_mps2=acceleration,
            deceleration_mps2=deceleration,
            jerk_mps3=jerk,
            brake_input=brake_input,
            throttle_input=throttle_input,
        )
        self.history.append(sample)

        brake_over_interval = (previous.brake_input + brake_input) * 0.5
        throttle_over_interval = (previous.throttle_input + throttle_input) * 0.5
        expected_coast_deceleration = self._COAST_DECELERATION_MPS2 + (
            1.0 - throttle_over_interval
        ) * self.config.throttle_release_deceleration_mps2
        expected_braking_deceleration = self._COAST_DECELERATION_MPS2 + brake_over_interval * (
            self.config.normal_braking_deceleration_mps2 - self._COAST_DECELERATION_MPS2
        )
        expected_deceleration = max(expected_coast_deceleration, expected_braking_deceleration)
        excess_deceleration = deceleration - expected_deceleration
        candidate = (
            previous.speed_mps >= self.config.minimum_speed_mps
            and excess_deceleration >= self.config.excess_deceleration_mps2
        )

        if self._cooldown_until_s is not None:
            if not candidate:
                self._rearm_required = False
            if timestamp_s < self._cooldown_until_s:
                self._pending.clear()
                return None
            if self._rearm_required:
                if candidate:
                    self._pending.clear()
                    return None
                self._rearm_required = False

        if not candidate:
            self._pending.clear()
            return None

        self._pending.append(_ImpactEvidence(sample, previous.speed_mps, excess_deceleration))
        while self._pending and timestamp_s - self._pending[0].sample.timestamp_s > self.config.confirmation_window_seconds:
            self._pending.popleft()

        strong_single_sample = (
            excess_deceleration >= self.config.excess_deceleration_mps2 * 2.5
            and jerk >= self.config.jerk_threshold_mps3
        )
        temporally_confirmed = len(self._pending) >= 2
        if not strong_single_sample and not temporally_confirmed:
            return None

        event = self._make_event(sample, strong_single_sample)
        self._pending.clear()
        self._cooldown_until_s = timestamp_s + self.config.cooldown_seconds
        self._rearm_required = True
        return event

    def _append_baseline(
        self,
        timestamp_s: float,
        longitudinal_velocity_mps: float,
        speed_mps: float,
        brake_input: float,
        throttle_input: float,
    ) -> None:
        self.history.append(
            MotionSample(
                timestamp_s=float(timestamp_s),
                longitudinal_velocity_mps=float(longitudinal_velocity_mps),
                speed_mps=speed_mps,
                acceleration_mps2=0.0,
                deceleration_mps2=0.0,
                jerk_mps3=0.0,
                brake_input=brake_input,
                throttle_input=throttle_input,
            )
        )

    def _make_event(self, current: MotionSample, strong_single_sample: bool) -> CollisionEvent:
        evidence = tuple(self._pending)
        peak_deceleration = max(item.sample.deceleration_mps2 for item in evidence)
        peak_jerk = max(item.sample.jerk_mps3 for item in evidence)
        peak_excess = max(item.excess_deceleration_mps2 for item in evidence)
        first = evidence[0]

        deceleration_score = min(1.0, peak_excess / (self.config.excess_deceleration_mps2 * 2.5))
        jerk_score = min(1.0, peak_jerk / (self.config.jerk_threshold_mps3 * 2.0))
        speed_score = min(1.0, first.speed_before_mps / (self.config.minimum_speed_mps * 5.0))
        persistence_score = min(1.0, (len(evidence) - 1) / 2.0)
        impact_score = min(
            1.0,
            0.50 * deceleration_score + 0.30 * jerk_score + 0.12 * speed_score + 0.08 * persistence_score,
        )

        confirmation = "strong one-sample deceleration/jerk signature" if strong_single_sample else (
            f"abnormal deceleration persisted across {len(evidence)} samples"
        )
        return CollisionEvent(
            detected=True,
            timestamp_s=current.timestamp_s,
            pre_impact_speed_mps=first.speed_before_mps,
            post_impact_speed_mps=current.speed_mps,
            peak_deceleration_mps2=peak_deceleration,
            peak_jerk_mps3=peak_jerk,
            brake_input=current.brake_input,
            throttle_input=current.throttle_input,
            impact_score=impact_score,
            reason=f"{confirmation}; deceleration exceeded the brake/throttle-aware envelope",
        )
