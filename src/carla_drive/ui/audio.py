"""Lightweight time-based rear parking beep feedback."""

from __future__ import annotations

import logging
from pathlib import Path
import time

import numpy as np
import pygame

from carla_drive.config import RearParkingConfig
from carla_drive.sensors.parking import beep_interval_ms

LOG = logging.getLogger(__name__)


class ParkingBeep:
    """Plays rear-distance beeps and a held vehicle horn through pygame audio."""

    def __init__(self, config: RearParkingConfig):
        self.config = config
        self.sound: pygame.mixer.Sound | None = None
        self.horn_sound: pygame.mixer.Sound | None = None
        self.horn_channel: pygame.mixer.Channel | None = None
        self._horn_pressed = False
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
        try:
            horn_path = Path(__file__).resolve().parents[1] / "assets" / "car_horn.wav"
            self.horn_sound = pygame.mixer.Sound(str(horn_path))
        except (pygame.error, OSError) as exc:
            LOG.warning("Vehicle horn audio is unavailable: %s", exc)

    def set_horn(self, pressed: bool) -> None:
        pressed = bool(pressed)
        if pressed == self._horn_pressed:
            return
        self._horn_pressed = pressed
        if pressed:
            if self.horn_sound:
                try:
                    self.horn_channel = self.horn_sound.play(loops=-1)
                    if self.horn_channel is None:
                        LOG.warning("Vehicle horn could not start because no audio channel is available.")
                except pygame.error as exc:
                    LOG.warning("Vehicle horn could not start: %s", exc)
        elif self.horn_channel:
            try:
                self.horn_channel.stop()
            except pygame.error as exc:
                LOG.warning("Vehicle horn could not stop cleanly: %s", exc)
            self.horn_channel = None

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
        self._horn_pressed = False
        if self.horn_channel:
            try:
                self.horn_channel.stop()
            except pygame.error as exc:
                LOG.debug("Vehicle horn channel was already unavailable during shutdown: %s", exc)
            self.horn_channel = None
        if self.horn_sound:
            try:
                self.horn_sound.stop()
            except pygame.error as exc:
                LOG.debug("Vehicle horn sound was already unavailable during shutdown: %s", exc)
            self.horn_sound = None
        if self.sound:
            try:
                self.sound.stop()
            except pygame.error as exc:
                LOG.debug("Parking beep was already unavailable during shutdown: %s", exc)
            self.sound = None
