"""Xbox-style gamepad sampling and a keyboard fallback."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import replace

import pygame

try:
    from pygame._sdl2 import controller as sdl_controller
except ImportError:
    sdl_controller = None

GAMEPAD_ERRORS = (pygame.error, sdl_controller.error) if sdl_controller is not None else (pygame.error,)

from carla_drive.config import ControllerConfig
from carla_drive.domain import ControlInput

LOG = logging.getLogger(__name__)


def normalize_steering(raw: float, deadzone: float, response: float) -> float:
    """Apply a centered deadzone and response curve while preserving sign."""
    if not math.isfinite(raw):
        return 0.0
    value = max(-1.0, min(1.0, float(raw)))
    magnitude = abs(value)
    if magnitude <= deadzone:
        return 0.0
    normalized = (magnitude - deadzone) / (1.0 - deadzone)
    return math.copysign(normalized**response, value)


def normalize_trigger(raw: float, rest: float, full: float, deadzone: float, response: float = 1.0) -> float:
    """Normalize trigger travel from a calibrated resting value to full press."""
    if full == rest:
        raise ValueError("Trigger full and resting values must differ.")
    if not math.isfinite(raw):
        return 0.0
    value = max(0.0, min(1.0, (float(raw) - rest) / (full - rest)))
    if value <= deadzone:
        return 0.0
    return ((value - deadzone) / (1.0 - deadzone)) ** response


def dpad_pressed(previous: tuple[int, int], current: tuple[int, int]) -> frozenset[str]:
    """Return D-pad actions only for axes that have just moved into a direction."""
    previous_x, previous_y = previous
    current_x, current_y = current
    pressed = set()
    if current_x == -1 and previous_x != -1:
        pressed.add("indicator_left")
    if current_x == 1 and previous_x != 1:
        pressed.add("indicator_right")
    if current_y == 1 and previous_y != 1:
        pressed.add("headlight_cycle")
    if current_y == -1 and previous_y != -1:
        pressed.add("indicator_cancel")
    return frozenset(pressed)


def dpad_button_pressed(previous: dict[str, bool], current: dict[str, bool]) -> frozenset[str]:
    actions = {
        "left": "indicator_left",
        "right": "indicator_right",
        "up": "headlight_cycle",
        "down": "indicator_cancel",
    }
    return frozenset(
        action for direction, action in actions.items() if current[direction] and not previous.get(direction, False)
    )


KEYBOARD_ACTION_KEYS = {
    pygame.K_r: "reverse",
    pygame.K_c: "camera_next",
    pygame.K_q: "camera_previous",
    pygame.K_BACKSPACE: "reset",
    pygame.K_p: "pause",
    pygame.K_z: "indicator_left",
    pygame.K_x: "indicator_right",
    pygame.K_h: "headlight_cycle",
    pygame.K_o: "open_settings",
}


def keyboard_action_edges(
    previous_down: set[int], events: Iterable[pygame.event.Event]
) -> tuple[frozenset[str], set[int]]:
    """Translate keyboard action presses into one-shot actions, ignoring repeats."""
    down = set(previous_down)
    pressed = set()
    focus_lost = getattr(pygame, "WINDOWFOCUSLOST", None)
    for event in events:
        if focus_lost is not None and event.type == focus_lost:
            down.clear()
        elif event.type == pygame.KEYUP:
            down.discard(event.key)
        elif event.type == pygame.KEYDOWN:
            if event.key not in down:
                action = KEYBOARD_ACTION_KEYS.get(event.key)
                if action:
                    pressed.add(action)
                down.add(event.key)
    return frozenset(pressed), down


class ControllerReader:
    """Samples one configured joystick and returns normalized manual controls."""

    ACTION_BUTTONS = {
        "reverse": "reverse_button",
        "camera_next": "camera_next_button",
        "camera_previous": "camera_previous_button",
        "handbrake": "handbrake_button",
        "reset": "reset_button",
        "pause": "pause_button",
        "open_settings": "settings_button",
    }

    def __init__(self, config: ControllerConfig):
        self.config = config
        self.joystick: pygame.joystick.JoystickType | None = None
        self.gamepad = None
        self._previous_buttons: dict[str, bool] = {}
        self._previous_hat = (0, 0)
        self._previous_dpad_buttons = {direction: False for direction in ("left", "right", "up", "down")}
        self._previous_steering = 0.0
        self._keyboard_keys_down: set[int] = set()
        self._keyboard_pressed = frozenset()
        self._keyboard_focused = True
        self._mapping_warning = False
        self._input_baseline_pending = True
        self._disconnected_this_sample = False
        self.keyboard_fallback = True
        self._owns_gamepad_subsystem = False
        if sdl_controller is not None:
            try:
                if not sdl_controller.get_init():
                    sdl_controller.init()
                    self._owns_gamepad_subsystem = True
            except GAMEPAD_ERRORS:
                LOG.warning("SDL gamepad mappings are unavailable; using joystick button/hat inputs.")
        pygame.joystick.init()
        self._connect()
        if not self.joystick:
            LOG.warning("No configured gamepad detected; using keyboard controls.")

    def _connect(self) -> None:
        if self.joystick or pygame.joystick.get_count() <= self.config.joystick_index:
            return
        joystick = pygame.joystick.Joystick(self.config.joystick_index)
        joystick.init()
        self.joystick = joystick
        if sdl_controller is not None:
            try:
                if sdl_controller.is_controller(self.config.joystick_index):
                    self.gamepad = sdl_controller.Controller.from_joystick(joystick)
            except GAMEPAD_ERRORS:
                self.gamepad = None
        self._mapping_warning = False
        self._previous_buttons.clear()
        self._previous_hat = (0, 0)
        self._previous_dpad_buttons = {direction: False for direction in ("left", "right", "up", "down")}
        self._previous_steering = 0.0
        self._input_baseline_pending = True
        self.keyboard_fallback = False
        LOG.info("Controller connected: %s (%d axes, %d buttons)", joystick.get_name(), joystick.get_numaxes(), joystick.get_numbuttons())

    @property
    def name(self) -> str:
        return self.joystick.get_name() if self.joystick else "Keyboard"

    def raw_axes(self) -> list[float]:
        if not self.joystick:
            return []
        try:
            return [self.joystick.get_axis(index) for index in range(self.joystick.get_numaxes())]
        except pygame.error:
            self._disconnect()
            return []

    def raw_buttons(self) -> list[int]:
        if not self.joystick:
            return []
        try:
            return [self.joystick.get_button(index) for index in range(self.joystick.get_numbuttons())]
        except pygame.error:
            self._disconnect()
            return []

    def raw_hats(self) -> list[tuple[int, int]]:
        if not self.joystick:
            return []
        try:
            return [self.joystick.get_hat(index) for index in range(self.joystick.get_numhats())]
        except pygame.error:
            self._disconnect()
            return []

    def sample(self, events: Iterable[pygame.event.Event]) -> ControlInput:
        self._disconnected_this_sample = False
        events = tuple(events)
        self._keyboard_pressed, self._keyboard_keys_down = keyboard_action_edges(self._keyboard_keys_down, events)
        focus_lost = getattr(pygame, "WINDOWFOCUSLOST", None)
        focus_gained = getattr(pygame, "WINDOWFOCUSGAINED", None)
        for event in events:
            if focus_lost is not None and event.type == focus_lost:
                self._keyboard_focused = False
            elif focus_gained is not None and event.type == focus_gained:
                self._keyboard_focused = True
        for event in events:
            if event.type == pygame.JOYDEVICEREMOVED and self.joystick and event.instance_id == self.joystick.get_instance_id():
                self._disconnect()
            elif event.type == pygame.JOYDEVICEADDED:
                self._connect()
        if not self.joystick:
            self._connect()
        if self.joystick:
            try:
                if self.joystick.get_init():
                    required = max(self.config.steering_axis, self.config.throttle_axis, self.config.brake_axis)
                    if required >= self.joystick.get_numaxes():
                        if not self._mapping_warning:
                            LOG.warning("Controller has %d axes, but axis %d is configured. Using keyboard; inspect --controller-debug and edit the YAML mapping.", self.joystick.get_numaxes(), required)
                            self._mapping_warning = True
                        self.keyboard_fallback = True
                        return self._with_disconnect_marker(self._sample_keyboard())
                self.keyboard_fallback = False
                control = self._sample_joystick()
                if self._keyboard_focused and self._keyboard_pressed:
                    control = replace(control, pressed=control.pressed | self._keyboard_pressed)
                return self._with_disconnect_marker(control)
            except GAMEPAD_ERRORS:
                self._disconnect()
        if self.joystick:
            self._disconnect()
        return self._with_disconnect_marker(self._sample_keyboard())

    def _with_disconnect_marker(self, control: ControlInput) -> ControlInput:
        if self._disconnected_this_sample:
            return replace(control, pressed=control.pressed | {"controller_disconnected"})
        return control

    def _disconnect(self) -> None:
        if self.joystick:
            self._disconnected_this_sample = True
            LOG.warning("Controller disconnected; switching to keyboard controls.")
            if self.gamepad is not None:
                try:
                    self.gamepad.quit()
                except GAMEPAD_ERRORS:
                    pass
                self.gamepad = None
            try:
                self.joystick.quit()
            except pygame.error:
                pass
            self.joystick = None
            self.keyboard_fallback = True
            self._previous_buttons.clear()
            self._previous_hat = (0, 0)
            self._previous_steering = 0.0

    def _sample_joystick(self) -> ControlInput:
        assert self.joystick is not None
        axes = [self.joystick.get_axis(index) for index in range(self.joystick.get_numaxes())]
        steering_raw = axes[self.config.steering_axis]
        if self.config.steering_axis_inverted:
            steering_raw = -steering_raw
        steering = normalize_steering(steering_raw, self.config.steering_deadzone, self.config.steering_response)
        steering = max(-1.0, min(1.0, steering * self.config.steering_sensitivity))
        smoothing = self.config.steering_smoothing
        steering = self._previous_steering + (steering - self._previous_steering) * (1.0 - smoothing)
        self._previous_steering = steering

        kwargs = dict(rest=self.config.trigger_rest_value, full=self.config.trigger_full_value, deadzone=self.config.trigger_deadzone)
        throttle_raw = axes[self.config.throttle_axis]
        brake_raw = axes[self.config.brake_axis]
        throttle = normalize_trigger(throttle_raw, response=self.config.throttle_response, **kwargs)
        brake = normalize_trigger(brake_raw, response=self.config.brake_response, **kwargs)
        current = {}
        for action, field in self.ACTION_BUTTONS.items():
            if action == "open_settings":
                current[action] = self._settings_pressed()
            else:
                current[action] = self._button(getattr(self.config, field))
        gamepad = getattr(self, "gamepad", None)
        use_standard_dpad = self.config.dpad_mode == "auto" and gamepad is not None
        use_hat = not use_standard_dpad and self.config.dpad_mode != "buttons" and self.config.dpad_hat < self.joystick.get_numhats()
        hat = self.joystick.get_hat(self.config.dpad_hat) if use_hat else (0, 0)
        if use_standard_dpad:
            dpad_buttons = {
                "left": gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_LEFT),
                "right": gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_RIGHT),
                "up": gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_UP),
                "down": gamepad.get_button(pygame.CONTROLLER_BUTTON_DPAD_DOWN),
            }
        else:
            dpad_buttons = {
                "left": self._button(self.config.dpad_left_button),
                "right": self._button(self.config.dpad_right_button),
                "up": self._button(self.config.dpad_up_button),
                "down": self._button(self.config.dpad_down_button),
            }
        if self._input_baseline_pending:
            pressed = frozenset()
            self._input_baseline_pending = False
        else:
            pressed = frozenset(action for action, down in current.items() if down and not self._previous_buttons.get(action, False))
            if use_hat:
                pressed |= dpad_pressed(self._previous_hat, hat)
            else:
                previous_dpad = getattr(self, "_previous_dpad_buttons", {direction: False for direction in dpad_buttons})
                pressed |= dpad_button_pressed(previous_dpad, dpad_buttons)
        self._previous_buttons = current
        self._previous_hat = hat
        self._previous_dpad_buttons = dpad_buttons
        return ControlInput(steering, throttle, brake, current["handbrake"], pressed)

    def _settings_button_index(self) -> int:
        if self.config.settings_button >= 0:
            return self.config.settings_button
        get_name = getattr(self.joystick, "get_name", None) if self.joystick else None
        joystick_name = get_name().casefold() if get_name else ""
        if any(name in joystick_name for name in ("dualsense", "playstation 5", "ps5")):
            return 9
        return -1

    def _settings_pressed(self) -> bool:
        if self.config.settings_button >= 0:
            return self._button(self.config.settings_button)
        gamepad = getattr(self, "gamepad", None)
        if gamepad is not None:
            return gamepad.get_button(pygame.CONTROLLER_BUTTON_START)
        return self._button(self._settings_button_index())

    def apply_config(self, config: ControllerConfig) -> None:
        reconnect = config.joystick_index != self.config.joystick_index
        if reconnect and self.joystick:
            self._disconnect()
        self.config = config
        self._previous_buttons.clear()
        self._previous_hat = (0, 0)
        self._previous_dpad_buttons = {direction: False for direction in ("left", "right", "up", "down")}
        self._previous_steering = 0.0
        self._input_baseline_pending = True
        if reconnect:
            self._connect()

    def _button(self, index: int) -> bool:
        return 0 <= index < self.joystick.get_numbuttons() and bool(self.joystick.get_button(index))

    def _sample_keyboard(self) -> ControlInput:
        if not self._keyboard_focused:
            return ControlInput()
        keys = pygame.key.get_pressed()
        steering = float(keys[pygame.K_d]) - float(keys[pygame.K_a])
        throttle = float(keys[pygame.K_w] or keys[pygame.K_UP])
        brake = float(keys[pygame.K_s] or keys[pygame.K_DOWN])
        handbrake = bool(keys[pygame.K_SPACE])
        return ControlInput(steering, throttle, brake, handbrake, self._keyboard_pressed)

    def close(self) -> None:
        if self.gamepad is not None:
            try:
                self.gamepad.quit()
            except GAMEPAD_ERRORS:
                pass
            self.gamepad = None
        if self.joystick:
            try:
                self.joystick.quit()
            except pygame.error:
                pass
            self.joystick = None
        if self._owns_gamepad_subsystem and sdl_controller is not None:
            try:
                sdl_controller.quit()
            except GAMEPAD_ERRORS:
                pass
            self._owns_gamepad_subsystem = False
