"""Synthesized driving and feedback audio routed through dedicated channels."""

from __future__ import annotations

import logging
from pathlib import Path
import time

import numpy as np
import pygame

from carla_drive.config import RearParkingConfig
from carla_drive.sensors.parking import beep_interval_ms

LOG = logging.getLogger(__name__)


class DrivingAudio:
    """Owns engine, horn, indicator, parking, collision, and shift sounds."""

    _CHANNEL_COUNT = 5
    _ENGINE_FREQUENCIES = (82, 105, 132, 164, 205, 256)

    def __init__(self, config: RearParkingConfig):
        self.config = config
        self.muted = False
        self.available = False
        self.last_beep_at = 0.0
        self._horn_pressed = False
        self._indicator_side: str | None = None
        self._last_indicator_at = 0.0
        self._engine_band = -1
        self._engine_volume = 0.0
        self._channels: list[pygame.mixer.Channel] = []
        self.sound: pygame.mixer.Sound | None = None
        self.horn_sound: pygame.mixer.Sound | None = None
        self.engine_sounds: list[pygame.mixer.Sound] = []
        self.effect_channel: pygame.mixer.Channel | None = None
        self.signal_channel: pygame.mixer.Channel | None = None
        self.engine_channel: pygame.mixer.Channel | None = None
        self.horn_channel: pygame.mixer.Channel | None = None
        self.parking_channel: pygame.mixer.Channel | None = None

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44_100, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(max(pygame.mixer.get_num_channels(), self._CHANNEL_COUNT))
            pygame.mixer.set_reserved(self._CHANNEL_COUNT)
            self._channels = [pygame.mixer.Channel(index) for index in range(self._CHANNEL_COUNT)]
            self.effect_channel, self.signal_channel, self.engine_channel, self.horn_channel, self.parking_channel = self._channels
            rate, _, channels = pygame.mixer.get_init()
            self.sound = self._make_tone(rate, channels, (880,), 0.065, 0.24)
            self.engine_sounds = [
                self._make_engine_tone(rate, channels, frequency)
                for frequency in self._ENGINE_FREQUENCIES
            ]
            self._chirp_sound = self._make_tone(rate, channels, (1250,), 0.045, 0.18)
            self._left_tick_sound = self._make_tone(rate, channels, (980,), 0.055, 0.20)
            self._right_tick_sound = self._make_tone(rate, channels, (1180,), 0.055, 0.20)
            self._ui_sound = self._make_tone(rate, channels, (1450,), 0.045, 0.16)
            self._shift_sound = self._make_tone(rate, channels, (520, 780), 0.22, 0.22)
            self._collision_sound = self._make_tone(rate, channels, (620, 920, 620, 920), 0.72, 0.28)
            self.available = True
            self.set_muted(False)
            try:
                horn_path = Path(__file__).resolve().parents[1] / "assets" / "car_horn.wav"
                self.horn_sound = pygame.mixer.Sound(str(horn_path))
            except (pygame.error, OSError) as exc:
                LOG.warning("Vehicle horn audio is unavailable: %s", exc)
        except (pygame.error, OSError, ValueError) as exc:
            LOG.warning("Driving audio is unavailable: %s", exc)

    @staticmethod
    def _make_tone(rate: int, channels: int, frequencies: tuple[int, ...], duration: float, volume: float) -> pygame.mixer.Sound:
        gap = 0.055
        segment_samples = max(1, int(rate * duration / len(frequencies)))
        parts = []
        for frequency in frequencies:
            samples = np.arange(segment_samples, dtype=np.float32)
            envelope = np.minimum(1.0, samples / max(1.0, rate * 0.008))
            envelope *= np.minimum(1.0, (segment_samples - samples) / max(1.0, rate * 0.018))
            parts.append(np.sin(samples * (2.0 * np.pi * frequency / rate)) * envelope * volume)
            parts.append(np.zeros(int(rate * gap), dtype=np.float32))
        mono = np.concatenate(parts)
        audio = np.asarray(mono * 32767, dtype=np.int16)
        if channels > 1:
            audio = np.repeat(audio[:, None], channels, axis=1)
        return pygame.sndarray.make_sound(audio)

    @staticmethod
    def _make_engine_tone(rate: int, channels: int, frequency: int) -> pygame.mixer.Sound:
        samples = np.arange(rate, dtype=np.float32)
        phase = samples * (2.0 * np.pi * frequency / rate)
        modulation = 0.84 + 0.16 * np.sin(samples * (2.0 * np.pi * 4.0 / rate))
        mono = (np.sin(phase) + 0.36 * np.sin(2.0 * phase) + 0.12 * np.sin(3.0 * phase)) * modulation * 0.28
        audio = np.asarray(mono * 32767, dtype=np.int16)
        if channels > 1:
            audio = np.repeat(audio[:, None], channels, axis=1)
        return pygame.sndarray.make_sound(audio)

    def _set_channel_volume(self, channel: pygame.mixer.Channel | None, volume: float) -> None:
        if channel:
            try:
                channel.set_volume(0.0 if self.muted else max(0.0, min(1.0, volume)))
            except pygame.error as exc:
                LOG.debug("Could not update audio channel volume: %s", exc)

    def _play(
        self,
        channel: pygame.mixer.Channel | None,
        sound: pygame.mixer.Sound | None,
        *,
        loops: int = 0,
        volume: float,
    ) -> bool:
        if not self.available or self.muted or channel is None or sound is None:
            return False
        try:
            channel.play(sound, loops=loops)
        except pygame.error as exc:
            LOG.warning("Could not play driving audio: %s", exc)
            return False
        self._set_channel_volume(channel, volume)
        return True

    def set_muted(self, muted: bool) -> bool:
        self.muted = bool(muted)
        volumes = (0.75, 0.55, self._engine_volume, 0.85, 0.65)
        for channel, volume in zip(self._channels, volumes):
            self._set_channel_volume(channel, volume)
        return self.muted

    def toggle_muted(self) -> bool:
        return self.set_muted(not self.muted)

    def pause_vehicle_audio(self) -> None:
        for channel in (self.engine_channel, self.signal_channel, self.horn_channel, self.parking_channel):
            if channel is not None:
                try:
                    channel.stop()
                except pygame.error as exc:
                    LOG.debug("Could not pause a driving audio channel: %s", exc)
        self._horn_pressed = False
        self._indicator_side = None
        self._last_indicator_at = 0.0
        self.last_beep_at = 0.0
        self._engine_band = -1

    def set_horn(self, pressed: bool) -> None:
        pressed = bool(pressed)
        if pressed == self._horn_pressed:
            return
        self._horn_pressed = pressed
        if not self.available or self.horn_channel is None:
            return
        if pressed and not self.muted and self.horn_sound:
            self._play(self.horn_channel, self.horn_sound, loops=-1, volume=0.85)
        else:
            try:
                self.horn_channel.stop()
            except pygame.error as exc:
                LOG.debug("Vehicle horn channel could not stop: %s", exc)

    def update_engine(self, throttle: float, speed_kmh: float) -> None:
        if not self.available or self.engine_channel is None or self.muted:
            return
        load = max(0.0, min(1.0, float(throttle)))
        speed = max(0.0, float(speed_kmh))
        band = min(len(self.engine_sounds) - 1, int(speed / 45.0 + load * 2.0))
        volume = min(0.62, 0.20 + load * 0.32 + min(speed / 220.0, 0.12))
        try:
            needs_sound = band != self._engine_band or not self.engine_channel.get_busy()
        except pygame.error as exc:
            LOG.warning("Engine audio is unavailable: %s", exc)
            return
        if needs_sound and self._play(self.engine_channel, self.engine_sounds[band], loops=-1, volume=volume):
            self._engine_band = band
        self._engine_volume = volume
        self._set_channel_volume(self.engine_channel, volume)

    def update_indicators(self, side: str | None) -> None:
        if side not in ("left", "right"):
            self._indicator_side = None
            self._last_indicator_at = 0.0
            return
        now = time.monotonic()
        if side != self._indicator_side:
            self._last_indicator_at = 0.0
            self._indicator_side = side
        if self.available and now - self._last_indicator_at >= 0.5:
            sound = self._left_tick_sound if side == "left" else self._right_tick_sound
            self._play(self.signal_channel, sound, volume=0.55)
            self._last_indicator_at = now

    def play_shift(self) -> None:
        self._play(self.effect_channel, getattr(self, "_shift_sound", None), volume=0.75)

    def play_ui(self) -> None:
        self._play(self.effect_channel, getattr(self, "_ui_sound", None), volume=0.65)

    def play_collision_alert(self) -> None:
        self._play(self.effect_channel, getattr(self, "_collision_sound", None), volume=0.95)

    def play_startup(self) -> None:
        self._play(self.effect_channel, getattr(self, "_chirp_sound", None), volume=0.65)

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
        if self.sound and self.parking_channel and (not self.last_beep_at or now - self.last_beep_at >= interval / 1000.0):
            self._play(self.parking_channel, self.sound, volume=0.75)
            self.last_beep_at = now

    def close(self) -> None:
        self._horn_pressed = False
        for channel in self._channels:
            try:
                channel.stop()
            except pygame.error as exc:
                LOG.debug("Audio channel was already unavailable during shutdown: %s", exc)
        self._channels.clear()
        self._indicator_side = None
        self.engine_sounds.clear()


ParkingBeep = DrivingAudio
