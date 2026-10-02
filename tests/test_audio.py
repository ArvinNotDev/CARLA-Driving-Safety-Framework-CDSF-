import os

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from carla_drive.config import RearParkingConfig
from carla_drive.ui.audio import DrivingAudio


def test_driving_audio_provides_multiple_cues_and_mutes_all_owned_channels():
    pygame.mixer.quit()
    audio = DrivingAudio(RearParkingConfig())
    try:
        assert audio.available
        assert len(audio.engine_sounds) >= 4

        audio.update_engine(0.8, 70.0)
        audio.update_indicators("left")
        audio.play_shift()
        audio.play_collision_alert()
        audio.update(True, 1.0)
        assert all(channel.get_busy() for channel in (audio.engine_channel, audio.signal_channel))

        assert audio.toggle_muted()
        assert all(channel.get_volume() == 0.0 for channel in audio._channels)
        assert not audio.toggle_muted()
        audio.set_horn(True)
        assert audio.horn_channel.get_busy()
        audio.pause_vehicle_audio()
        assert not audio.horn_channel.get_busy()
    finally:
        audio.close()
        pygame.mixer.set_reserved(0)
        pygame.mixer.quit()
