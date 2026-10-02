from carla_drive.config import ControllerConfig
from carla_drive.input.controller import ControllerReader, dpad_pressed, normalize_steering, normalize_trigger
import math


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


def test_invalid_axis_samples_cannot_turn_or_accelerate():
    for value in (math.nan, math.inf, -math.inf):
        assert normalize_steering(value, 0.06, 1.35) == 0.0
        assert normalize_trigger(value, -1.0, 1.0, 0.04) == 0.0


def test_dpad_actions_are_edges_and_switch_sides_once():
    assert dpad_pressed((0, 0), (-1, 0)) == {"indicator_left"}
    assert dpad_pressed((-1, 0), (-1, 0)) == set()
    assert dpad_pressed((-1, 0), (1, 0)) == {"indicator_right"}


def test_dpad_up_only_cycles_when_pressed_and_diagonals_can_combine():
    assert dpad_pressed((0, 0), (0, 1)) == {"headlight_cycle"}
    assert dpad_pressed((0, 1), (0, 1)) == set()
    assert dpad_pressed((0, 0), (-1, 1)) == {"headlight_cycle", "indicator_left"}


def test_keyboard_actions_remain_available_with_a_connected_controller():
    import pygame

    controller = ControllerReader.__new__(ControllerReader)
    controller.config = ControllerConfig()
    controller.joystick = type(
        "Joystick",
        (),
        {
            "get_init": lambda self: True,
            "get_numaxes": lambda self: 6,
            "get_axis": lambda self, index: -1.0,
            "get_numbuttons": lambda self: 17,
            "get_button": lambda self, index: False,
            "get_numhats": lambda self: 0,
        },
    )()
    controller._keyboard_pressed = frozenset()
    controller._keyboard_focused = True
    controller._keyboard_keys_down = set()
    controller._previous_buttons = {}
    controller._previous_hat = (0, 0)
    controller._previous_steering = 0.0
    controller._input_baseline_pending = False
    controller._mapping_warning = False
    controller._disconnected_this_sample = False
    controller.keyboard_fallback = False

    key_press = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h, repeat=False)
    assert "headlight_cycle" in controller.sample([key_press]).pressed
