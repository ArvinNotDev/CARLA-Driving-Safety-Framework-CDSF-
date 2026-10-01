"""Lightweight time-based rear parking beep feedback."""

from __future__ import annotations

import logging
import time

import numpy as np
import pygame

from carla_drive.config import RearParkingConfig
from carla_drive.sensors.parking import beep_interval_ms

LOG = logging.getLogger(__name__)


class ParkingBeep:
    def __init__(self, config: RearParkingConfig):
        self.config = config
        self.sound: pygame.mixer.Sound | None = None
        self.last_beep_at = 0.0
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22_050, size=-16, channels=1, buffer=256)
            rate, _, channels = pygame.mixer.get_init()
            duration = 0.065
            sample_count = int(rate * duration)
            sample_times = np.arange(sample_count, dtype=np.float32) / rate
            envelope = np.minimum(1.0, np.arange(sample_count) / max(1, rate * 0.004))
            envelope *= np.minimum(1.0, (sample_count - np.arange(sample_count)) / max(1, rate * 0.008))
            mono_samples = (np.sin(sample_times * 2.0 * np.pi * 880.0) * envelope * 0.24 * 32767).astype(np.int16)
            samples = mono_samples if channels == 1 else np.repeat(mono_samples[:, None], channels, axis=1)
            self.sound = pygame.sndarray.make_sound(samples)
        except (pygame.error, ValueError) as exc:
            LOG.warning("Parking beep audio is unavailable: %s", exc)

    def update(self, reversing: bool, distance_m: float | None) -> None:
        now = time.monotonic()
        interval = beep_interval_ms(
            distance_m if reversing else None,
            self.config.warning_distance_m,
            self.config.critical_distance_m,
            self.config.slowest_beep_ms,
            self.config.fastest_beep_ms,
        )
        if interval is None:
            self.last_beep_at = 0.0
            return
        if self.sound and (not self.last_beep_at or now - self.last_beep_at >= interval / 1000.0):
            self.sound.play()
            self.last_beep_at = now

    def close(self) -> None:
        if self.sound:
            self.sound.stop()
            self.sound = None
