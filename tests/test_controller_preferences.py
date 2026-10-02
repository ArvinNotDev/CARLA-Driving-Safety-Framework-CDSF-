import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from carla_drive.config import ControllerConfig
from carla_drive.input.preferences import load_controller_preferences, save_controller_preferences
from carla_drive.ui.controller_settings import ControllerSettings


def test_controller_preferences_round_trip(tmp_path):
    path = tmp_path / "controller.json"
    saved = ControllerConfig(steering_sensitivity=1.4, steering_deadzone=0.12, dpad_mode="buttons")

    save_controller_preferences(saved, path)

    assert load_controller_preferences(ControllerConfig(), path) == saved


def test_invalid_controller_preferences_fall_back_to_defaults(tmp_path):
    path = tmp_path / "controller.json"
    path.write_text('{"steering_deadzone": 1.5}', encoding="utf-8")

    assert load_controller_preferences(ControllerConfig(), path) == ControllerConfig()


def test_dpad_hat_binding_can_be_captured():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    settings = ControllerSettings(screen, ControllerConfig())
    settings.capture_target = "dpad_hat"
    settings._capture_event(pygame.event.Event(pygame.JOYHATMOTION, hat=2, value=(0, 1)))

    assert settings.values["dpad_hat"] == 2
    assert settings.values["dpad_mode"] == "hat"
    assert settings.capture_target is None
    pygame.display.quit()


def test_axis_binding_and_settings_layout_pages_render():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    settings = ControllerSettings(screen, ControllerConfig())
    settings.capture_target = "steering_axis"
    settings._capture_event(pygame.event.Event(pygame.JOYAXISMOTION, axis=2, value=0.7))

    assert settings.values["steering_axis"] == 2
    for page in settings.PAGES:
        settings.page = page
        settings._draw()
    assert settings.save_rect.left > settings.reset_rect.right
    pygame.display.quit()
