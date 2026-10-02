import pytest

from carla_drive.config import KinematicCollisionConfig
from carla_drive.safety.kinematic_collision import KinematicCollisionDetector, is_reportable_collision


def feed(detector, speeds_mps, brake=0.0, throttle=0.0, dt=0.05, start_time=0.0, reverse=False):
    events = []
    for index, speed in enumerate(speeds_mps):
        event = detector.update(
            start_time + index * dt,
            -speed if reverse else speed,
            brake,
            throttle,
            reverse,
        )
        if event:
            events.append(event)
    return events


def test_constant_speed_and_acceleration_from_rest_do_not_trigger():
    detector = KinematicCollisionDetector()

    assert feed(detector, [15.0] * 20) == []
    detector.reset()
    assert feed(detector, [0.0, 0.1, 0.25, 0.45, 0.7, 1.0], throttle=0.7) == []


def test_gradual_braking_and_smooth_stop_do_not_trigger():
    detector = KinematicCollisionDetector()
    gradual = [20.0 - 1.5 * 0.05 * i for i in range(16)]
    assert feed(detector, gradual, brake=0.2) == []

    detector.reset()
    smooth_stop = [max(0.0, 8.0 - 4.0 * 0.05 * i) for i in range(45)]
    assert feed(detector, smooth_stop, brake=0.4) == []


def test_aggressive_normal_braking_is_accounted_for_by_brake_envelope():
    detector = KinematicCollisionDetector()
    hard_braking = [max(0.0, 25.0 - 9.0 * 0.05 * i) for i in range(45)]

    assert feed(detector, hard_braking, brake=0.9) == []


def test_throttle_release_and_normal_coasting_do_not_trigger():
    detector = KinematicCollisionDetector()
    events = []
    speeds = [20.0, 20.0, 19.8, 19.6, 19.4, 19.2, 19.0]
    throttles = [1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    for index, (speed, throttle) in enumerate(zip(speeds, throttles)):
        event = detector.update(index * 0.05, speed, 0.0, throttle)
        if event:
            events.append(event)

    assert events == []


@pytest.mark.parametrize(
    ("initial_speed", "post_impact_speed"),
    [
        (2.8, 0.5),  # about 10 km/h, above the configured 2 m/s floor
        (25.0, 10.0),  # very sudden loss
        (27.8, 22.0),  # high-speed case
    ],
)
def test_abrupt_speed_losses_produce_one_impact_candidate(initial_speed, post_impact_speed):
    detector = KinematicCollisionDetector()
    events = feed(detector, [initial_speed, initial_speed, post_impact_speed, post_impact_speed])

    assert len(events) == 1
    event = events[0]
    assert event.detected
    assert event.pre_impact_speed_mps == initial_speed
    assert event.post_impact_speed_mps == post_impact_speed
    assert event.peak_deceleration_mps2 > 4.0
    assert event.peak_jerk_mps3 > 75.0
    assert 0.0 < event.impact_score <= 1.0
    assert "brake/throttle-aware envelope" in event.reason
    assert event.impact_score >= 0.8


def test_low_speed_sudden_loss_below_minimum_speed_is_ignored():
    detector = KinematicCollisionDetector()

    assert feed(detector, [1.5, 1.5, 0.0, 0.0]) == []


def test_example_gradual_speed_change_is_normal_but_large_step_drop_is_flagged():
    normal_detector = KinematicCollisionDetector()
    gradual_kmh = [50.0, 49.8, 49.5, 48.9, 48.0, 47.2]
    assert feed(normal_detector, [speed / 3.6 for speed in gradual_kmh]) == []

    impact_detector = KinematicCollisionDetector()
    abrupt_kmh = [50.0, 49.8, 49.6, 49.3, 42.0, 34.0]
    assert len(feed(impact_detector, [speed / 3.6 for speed in abrupt_kmh])) == 1


def test_small_noisy_velocity_measurements_do_not_confirm_an_event():
    detector = KinematicCollisionDetector()
    noisy = [15.0, 15.04, 14.98, 15.03, 14.99, 15.02, 14.97, 15.01, 14.99, 15.0]

    assert feed(detector, noisy) == []


def test_braking_followed_by_abnormal_additional_speed_loss_is_detected():
    detector = KinematicCollisionDetector()
    speeds = [20.0, 19.6, 19.2, 18.8, 18.4, 18.0, 16.3, 16.3]

    events = feed(detector, speeds, brake=0.8)

    assert len(events) == 1
    assert events[0].brake_input == 0.8
    assert events[0].peak_deceleration_mps2 > 30.0


def test_low_confidence_event_is_suppressed_without_blocking_a_later_strong_event():
    detector = KinematicCollisionDetector()

    assert feed(detector, [15.0, 15.0, 14.6]) == []
    assert feed(detector, [14.2], start_time=0.15) == []
    assert detector._cooldown_until_s is None
    events = feed(detector, [9.0], start_time=0.20)

    assert len(events) == 1
    assert events[0].timestamp_s == pytest.approx(0.20)
    assert events[0].impact_score >= 0.8


def test_variable_sample_intervals_use_elapsed_seconds_for_acceleration():
    detector = KinematicCollisionDetector()
    detector.update(10.0, 20.0, 0.0, 0.0)
    detector.update(10.1, 19.0, 0.0, 0.0)

    assert detector.history[-1].acceleration_mps2 == pytest.approx(-10.0)
    assert detector.history[-1].deceleration_mps2 == pytest.approx(10.0)


def test_reverse_motion_is_oriented_and_direction_switch_clears_old_history():
    detector = KinematicCollisionDetector()

    reverse_events = feed(detector, [12.0, 12.0, 9.0, 9.0], reverse=True)
    assert len(reverse_events) == 1

    detector.reset()
    detector.update(0.0, -12.0, 0.0, 0.0, reverse=True)
    detector.update(0.05, -12.0, 0.0, 0.0, reverse=True)
    assert detector.update(0.1, 15.0, 0.0, 0.0, reverse=False) is None
    assert len(detector.history) == 1
    detector.update(0.15, 15.0, 0.0, 0.0, reverse=False)
    assert detector.update(0.20, 12.0, 0.0, 0.0, reverse=False) is not None


def test_abrupt_longitudinal_direction_reversal_can_still_be_detected():
    detector = KinematicCollisionDetector()

    events = feed(detector, [15.0, 15.0, -2.0])

    assert len(events) == 1
    assert events[0].pre_impact_speed_mps == 15.0
    assert events[0].post_impact_speed_mps == 2.0


def test_cooldown_suppresses_duplicates_then_detector_can_report_a_later_event():
    detector = KinematicCollisionDetector(KinematicCollisionConfig(cooldown_seconds=0.4))
    speeds = [15.0, 15.0, 12.0, 12.0] + [12.0] * 8 + [9.0, 9.0]

    events = feed(detector, speeds)

    assert len(events) == 2
    assert events[1].timestamp_s - events[0].timestamp_s > 0.4


def test_invalid_or_restarted_simulation_time_restarts_history():
    detector = KinematicCollisionDetector()
    detector.update(5.0, 15.0, 0.0, 0.0)
    detector.update(5.05, 15.0, 0.0, 0.0)
    detector.update(0.0, 5.0, 0.0, 0.0)

    assert len(detector.history) == 1
    assert detector.history[0].timestamp_s == 0.0
    detector.update(0.05, float("nan"), 0.0, 0.0)
    assert len(detector.history) == 0


def test_motion_history_stays_bounded():
    detector = KinematicCollisionDetector()

    feed(detector, [15.0] * 20)

    assert len(detector.history) == 8


def test_only_collision_confidence_at_or_above_threshold_is_reportable():
    from types import SimpleNamespace

    assert not is_reportable_collision(SimpleNamespace(impact_score=0.799))
    assert is_reportable_collision(SimpleNamespace(impact_score=0.8))
    assert not is_reportable_collision(None)
