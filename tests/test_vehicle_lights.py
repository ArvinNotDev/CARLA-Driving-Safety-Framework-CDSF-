from enum import IntFlag

from carla_drive.carla.lights import EgoLightState, HeadlightMode


class LightFlags(IntFlag):
    NONE = 0
    LowBeam = 1
    HighBeam = 2
    LeftBlinker = 4
    RightBlinker = 8
    Brake = 16
    Reverse = 32


def test_brake_lights_use_a_small_analog_threshold_and_release_cleanly():
    lights = EgoLightState()

    assert lights.set_brake_input(0.049) is False
    assert not (lights.to_carla_state(LightFlags) & LightFlags.Brake)
    assert lights.set_brake_input(0.05) is True
    assert lights.to_carla_state(LightFlags) & LightFlags.Brake
    assert lights.set_brake_input(0.0) is True
    assert not (lights.to_carla_state(LightFlags) & LightFlags.Brake)


def test_headlight_cycle_is_off_low_high_off():
    lights = EgoLightState()

    assert lights.headlights is HeadlightMode.OFF
    assert lights.cycle_headlights() is HeadlightMode.LOW
    assert lights.cycle_headlights() is HeadlightMode.HIGH
    assert lights.cycle_headlights() is HeadlightMode.OFF


def test_indicator_toggles_are_exclusive_and_repeat_press_turns_off():
    lights = EgoLightState()

    assert lights.toggle_indicator("left") is True
    assert lights.left_indicator and not lights.right_indicator
    assert lights.toggle_indicator("left") is False
    assert not lights.left_indicator and not lights.right_indicator
    assert lights.toggle_indicator("right") is True
    assert lights.toggle_indicator("left") is True
    assert lights.left_indicator and not lights.right_indicator


def test_composed_vehicle_lights_preserve_independent_states_and_cache_value():
    lights = EgoLightState()
    lights.cycle_headlights()
    lights.toggle_indicator("right")
    lights.set_brake_input(0.7)
    lights.set_reverse(True)

    state = lights.to_carla_state(LightFlags)
    assert state == (LightFlags.LowBeam | LightFlags.RightBlinker | LightFlags.Brake | LightFlags.Reverse)
    assert lights.to_carla_state(LightFlags) is state

    lights.cycle_headlights()
    assert lights.to_carla_state(LightFlags) == (
        LightFlags.HighBeam | LightFlags.RightBlinker | LightFlags.Brake | LightFlags.Reverse
    )
