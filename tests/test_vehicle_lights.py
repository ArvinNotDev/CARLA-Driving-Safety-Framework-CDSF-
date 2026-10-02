from types import SimpleNamespace
from enum import IntFlag

import carla

from carla_drive.carla.lights import EgoLightState, HeadlightMode
from carla_drive.carla.session import CarlaSession


class LightFlags(IntFlag):
    NONE = 0
    Position = 1
    LowBeam = 2
    HighBeam = 4
    Brake = 8
    RightBlinker = 16
    LeftBlinker = 32
    Reverse = 64


def test_brake_lights_use_a_small_analog_threshold_and_release_cleanly():
    lights = EgoLightState()

    assert lights.set_brake_input(0.049) is False
    assert not (lights.to_carla_state(LightFlags) & LightFlags.Brake)
    assert lights.set_brake_input(0.05) is True
    assert lights.to_carla_state(LightFlags) & LightFlags.Brake
    assert lights.set_brake_input(0.0) is True
    assert not (lights.to_carla_state(LightFlags) & LightFlags.Brake)


def test_headlights_start_on_low_beam_and_cycle_high_off_low():
    lights = EgoLightState()

    assert lights.headlights is HeadlightMode.LOW
    assert lights.cycle_headlights() is HeadlightMode.HIGH
    assert lights.cycle_headlights() is HeadlightMode.OFF
    assert lights.cycle_headlights() is HeadlightMode.LOW


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
    lights.toggle_indicator("right")
    lights.set_brake_input(0.7)
    lights.set_reverse(True)

    state = lights.to_carla_state(LightFlags)
    assert state == (
        LightFlags.Position | LightFlags.LowBeam | LightFlags.RightBlinker | LightFlags.Brake | LightFlags.Reverse
    )
    assert lights.to_carla_state(LightFlags) is state

    lights.cycle_headlights()
    assert lights.to_carla_state(LightFlags) == (
        LightFlags.Position | LightFlags.HighBeam | LightFlags.RightBlinker | LightFlags.Brake | LightFlags.Reverse
    )


def test_session_passes_native_carla_vehicle_light_state_to_vehicle():
    observed = []
    session = CarlaSession.__new__(CarlaSession)
    session.ego_vehicle = SimpleNamespace(
        apply_control=lambda control: None,
        set_light_state=lambda state: observed.append(state),
    )
    session._last_ego_light_state = None
    lights = EgoLightState()

    session.apply_control(0.0, 0.0, 0.0, False, False, lights)

    assert len(observed) == 1
    assert isinstance(observed[0], carla.VehicleLightState)
    assert int(observed[0]) == int(carla.VehicleLightState.Position | carla.VehicleLightState.LowBeam)
