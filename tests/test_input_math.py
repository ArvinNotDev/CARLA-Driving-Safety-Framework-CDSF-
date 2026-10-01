from carla_drive.input.controller import normalize_steering, normalize_trigger


def test_steering_deadzone_and_symmetric_limits():
    assert normalize_steering(0.04, 0.06, 1.0) == 0.0
    assert normalize_steering(-1.0, 0.06, 1.0) == -1.0
    assert normalize_steering(1.0, 0.06, 1.0) == 1.0


def test_steering_response_keeps_center_control_small():
    linear = normalize_steering(0.4, 0.05, 1.0)
    curved = normalize_steering(0.4, 0.05, 1.5)
    assert 0 < curved < linear < 1


def test_trigger_normalization_supports_resting_negative_axis():
    assert normalize_trigger(-1.0, -1.0, 1.0, 0.04) == 0.0
    assert 0 < normalize_trigger(0.0, -1.0, 1.0, 0.04) < 1
    assert normalize_trigger(1.0, -1.0, 1.0, 0.04) == 1.0


def test_trigger_normalization_supports_zero_based_axis():
    assert normalize_trigger(0.0, 0.0, 1.0, 0.02) == 0.0
    assert normalize_trigger(0.5, 0.0, 1.0, 0.02) > 0.4
