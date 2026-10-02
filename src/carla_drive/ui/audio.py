"""Rear-only proximity beep for reverse parking assistance."""

from __future__ import annotations

import logging
import time

import numpy as np
import pygame

from carla_drive.config import RearParkingConfig
from carla_drive.sensors.parking import beep_interval_ms

LOG = logging.getLogger(__name__)


class ReverseBeep:
    """Plays the sole application sound: the rear parking warning beep."""

    def __init__(self, config: RearParkingConfig):
        self.config = config
        self.muted = False
        self.available = False
        self.last_beep_at = 0.0
        self.sound: pygame.mixer.Sound | None = None
        self.channel: pygame.mixer.Channel | None = None

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44_100, size=-16, channels=2, buffer=512)
            rate, _, channels = pygame.mixer.get_init()
            samples = np.arange(max(1, int(rate * 0.065)), dtype=np.float32)
            envelope = np.minimum(1.0, samples / max(1.0, rate * 0.008))
            envelope *= np.minimum(1.0, (len(samples) - samples) / max(1.0, rate * 0.018))
            mono = np.sin(samples * (2.0 * np.pi * 880 / rate)) * envelope * 0.24
            audio = np.asarray(mono * 32767, dtype=np.int16)
            if channels > 1:
                audio = np.repeat(audio[:, None], channels, axis=1)
            self.sound = pygame.sndarray.make_sound(audio)
            self.channel = pygame.mixer.find_channel(force=True)
            self.available = self.channel is not None
        except (pygame.error, OSError, ValueError) as exc:
            LOG.warning("Reverse parking beep is unavailable: %s", exc)

    def set_muted(self, muted: bool) -> bool:
        self.muted = bool(muted)
        if self.muted and self.channel is not None:
            self.channel.stop()
        return self.muted

    def toggle_muted(self) -> bool:
        return self.set_muted(not self.muted)

    def pause(self) -> None:
        self.last_beep_at = 0.0
        if self.channel is not None:
            self.channel.stop()

    def update(self, reversing: bool, distance_m: float | None) -> None:
        now = time.monotonic()
        interval = beep_interval_ms(
            distance_m if reversing else None,
            self.config.warning_distance_m,
            self.config.critical_distance_m,
            self.config.slowest_beep_ms,
            self.config.fastest_beep_ms,
        )
        if interval is None or self.muted:
            self.last_beep_at = 0.0
            return
        if self.available and self.sound is not None and self.channel is not None:
            if not self.last_beep_at or now - self.last_beep_at >= interval / 1000.0:
                try:
                    self.channel.play(self.sound)
                    self.channel.set_volume(0.75)
                    self.last_beep_at = now
                except pygame.error as exc:
                    LOG.warning("Could not play reverse parking beep: %s", exc)

    def close(self) -> None:
        self.pause()
        self.sound = None


ParkingBeep = ReverseBeep
