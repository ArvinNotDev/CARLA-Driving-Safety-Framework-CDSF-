import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from carla_drive.config import RearParkingConfig
from carla_drive.ui.audio import ReverseBeep


def test_only_reverse_parking_beep_is_available_and_can_be_muted():
    pygame.mixer.quit()
    audio = ReverseBeep(RearParkingConfig())
    try:
        assert audio.available
        audio.update(True, 1.0)
        assert audio.channel.get_busy()

        assert audio.toggle_muted()
        assert not audio.channel.get_busy()
        assert not audio.toggle_muted()
        audio.pause()
        assert not audio.channel.get_busy()
    finally:
        audio.close()
        pygame.mixer.set_reserved(0)
        pygame.mixer.quit()
