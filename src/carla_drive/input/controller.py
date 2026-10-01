"""Xbox-style gamepad sampling and a keyboard fallback."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable

import pygame

from carla_drive.config import ControllerConfig
from carla_drive.domain import ControlInput

LOG = logging.getLogger(__name__)


def normalize_steering(raw: float, deadzone: float, response: float) -> float:
    """Apply a centered deadzone and response curve while preserving sign."""
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
    value = max(0.0, min(1.0, (float(raw) - rest) / (full - rest)))
    if value <= deadzone:
        return 0.0
    return ((value - deadzone) / (1.0 - deadzone)) ** response


class ControllerReader:
    """Samples one configured joystick and returns normalized manual controls."""

    ACTION_BUTTONS = {
        "reverse": "reverse_button",
        "camera_next": "camera_next_button",
        "camera_previous": "camera_previous_button",
        "handbrake": "handbrake_button",
        "reset": "reset_button",
        "pause": "pause_button",
    }

    def __init__(self, config: ControllerConfig):
        self.config = config
        self.joystick: pygame.joystick.JoystickType | None = None
        self._previous_buttons: dict[str, bool] = {}
        self._previous_steering = 0.0
        self.keyboard_fallback = True
        pygame.joystick.init()
        if pygame.joystick.get_count() > config.joystick_index:
            joystick = pygame.joystick.Joystick(config.joystick_index)
            joystick.init()
            self.joystick = joystick
            self.keyboard_fallback = False
            LOG.info("Controller connected: %s (%d axes, %d buttons)", joystick.get_name(), joystick.get_numaxes(), joystick.get_numbuttons())
        else:
            LOG.warning("No configured gamepad detected; using keyboard controls.")

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

    def sample(self, events: Iterable[pygame.event.Event]) -> ControlInput:
        events = tuple(events)
        if self.joystick:
            try:
                if self.joystick.get_init():
                    return self._sample_joystick()
            except pygame.error:
                self._disconnect()
        return self._sample_keyboard(events)

    def _disconnect(self) -> None:
        if self.joystick:
            LOG.warning("Controller disconnected; switching to keyboard controls.")
            try:
                self.joystick.quit()
            except pygame.error:
                pass
            self.joystick = None
            self.keyboard_fallback = True

    def _sample_joystick(self) -> ControlInput:
        assert self.joystick is not None
        axes = self.raw_axes()
        steering_raw = self._axis(axes, self.config.steering_axis)
        if self.config.steering_axis_inverted:
            steering_raw = -steering_raw
        steering = normalize_steering(steering_raw, self.config.steering_deadzone, self.config.steering_response)
        smoothing = self.config.steering_smoothing
        steering = self._previous_steering + (steering - self._previous_steering) * (1.0 - smoothing)
        self._previous_steering = steering

        kwargs = dict(rest=self.config.trigger_rest_value, full=self.config.trigger_full_value, deadzone=self.config.trigger_deadzone)
        throttle_raw = self._axis(axes, self.config.throttle_axis, self.config.trigger_rest_value)
        brake_raw = self._axis(axes, self.config.brake_axis, self.config.trigger_rest_value)
        throttle = normalize_trigger(throttle_raw, response=self.config.throttle_response, **kwargs)
        brake = normalize_trigger(brake_raw, response=self.config.brake_response, **kwargs)
        current = {action: self._button(getattr(self.config, field)) for action, field in self.ACTION_BUTTONS.items()}
        pressed = frozenset(action for action, down in current.items() if down and not self._previous_buttons.get(action, False))
        self._previous_buttons = current
        return ControlInput(steering, throttle, brake, current["handbrake"], pressed)

    @staticmethod
    def _axis(axes: list[float], index: int, default: float = 0.0) -> float:
        return axes[index] if 0 <= index < len(axes) else default

    def _button(self, index: int) -> bool:
        return 0 <= index < self.joystick.get_numbuttons() and bool(self.joystick.get_button(index))

    def _sample_keyboard(self, events: Iterable[pygame.event.Event]) -> ControlInput:
        keys = pygame.key.get_pressed()
        steering = float(keys[pygame.K_d]) - float(keys[pygame.K_a])
        throttle = float(keys[pygame.K_w] or keys[pygame.K_UP])
        brake = float(keys[pygame.K_s] or keys[pygame.K_DOWN])
        keys_for_actions = {
            "reverse": pygame.K_r,
            "camera_next": pygame.K_c,
            "camera_previous": pygame.K_q,
            "handbrake": pygame.K_SPACE,
            "reset": pygame.K_BACKSPACE,
            "pause": pygame.K_p,
        }
        pressed = frozenset(
            action
            for action, key in keys_for_actions.items()
            if any(event.type == pygame.KEYDOWN and event.key == key for event in events)
        )
        return ControlInput(steering, throttle, brake, bool(keys[pygame.K_SPACE]), pressed)

    def close(self) -> None:
        if self.joystick:
            try:
                self.joystick.quit()
            except pygame.error:
                pass
            self.joystick = None
