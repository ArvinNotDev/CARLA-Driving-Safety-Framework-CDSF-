import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from carla_drive.carla.session import VehicleOption
from carla_drive.config import SessionConfig
from carla_drive.ui.launcher import Launcher
from carla_drive.ui.pause_menu import PauseMenu


class AudioState:
    def __init__(self):
        self.muted = False

    def toggle_muted(self):
        self.muted = not self.muted
        return self.muted

    def play_ui(self):
        return None


def test_pause_menu_audio_toggle_and_actions():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 700))
    audio = AudioState()
    menu = PauseMenu(screen, audio)

    assert menu._activate("audio") is None
    assert audio.muted
    assert menu._activate("menu") == "menu"
    assert menu._activate("resume") == "resume"
    menu._draw()
    assert len(menu.buttons) == 3


def test_launcher_includes_time_of_day_in_session_config():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    launcher = Launcher(
        screen,
        ["Town01"],
        [("ClearNoon", "Clear")],
        [VehicleOption("vehicle.test.sedan", "Test Sedan")],
        SessionConfig(),
    )
    launcher.selected["time_of_day"] = 5

    assert launcher._session_config().time_of_day == "Night"
    launcher._draw()
    assert len(launcher.row_rects) == 6
    launcher._open_dropdown(3)
    assert launcher.dropdown_rect.top >= 0
    assert launcher.dropdown_rect.bottom <= screen.get_height()
