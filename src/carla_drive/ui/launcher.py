"""CARLA session setup screen."""

from __future__ import annotations

from dataclasses import replace

import pygame

from carla_drive.config import SessionConfig
from carla_drive.carla.session import VehicleOption, friendly_map_name


class Launcher:
    """Small keyboard- and mouse-operable setup screen."""

    def __init__(self, screen: pygame.Surface, maps: list[str], weather: list[tuple[str, str]], vehicles: list[VehicleOption], defaults: SessionConfig):
        self.screen = screen
        self.maps = maps or ["Town01"]
        self.weather = weather
        self.vehicles = vehicles
        self.defaults = defaults
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 28)
        self.small = pygame.font.Font(None, 21)
        self.title = pygame.font.Font(None, 45)
        self.selected = {
            "map": self._find_index(self.maps, defaults.map_name, lambda value: friendly_map_name(value)),
            "weather": self._find_index(weather, defaults.weather_preset, lambda value: value[0]),
            "vehicle": self._find_index(vehicles, defaults.vehicle_blueprint, lambda value: value.blueprint_id),
        }
        self.traffic = defaults.traffic_vehicles
        self.pedestrians = defaults.pedestrians
        self.focus = 0
        self.status = "Choose a map, weather, vehicle, and traffic level."
        self.start_rect = pygame.Rect(0, 0, 230, 58)
        self.row_rects: list[pygame.Rect] = []

    @staticmethod
    def _find_index(items, selected, key):
        if selected is not None:
            for index, item in enumerate(items):
                if key(item) == selected or key(item) == friendly_map_name(selected):
                    return index
        return 0

    def run(self) -> SessionConfig | None:
        pygame.display.set_caption("CARLA Drive | Session Setup")
        while True:
            self.clock.tick(60)
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        return self._session_config()
                    if event.key == pygame.K_ESCAPE:
                        return None
                    self._key_action(event.key)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.start_rect.collidepoint(event.pos):
                        return self._session_config()
                    for index, rect in enumerate(self.row_rects):
                        if rect.collidepoint(event.pos):
                            self.focus = index
                            if event.pos[0] > rect.right - 100:
                                self._change(1, 5)
                            elif event.pos[0] < rect.left + 100:
                                self._change(-1, 5)
            self._draw()
            pygame.display.flip()

    def _key_action(self, key: int) -> None:
        if key in (pygame.K_UP, pygame.K_w):
            self.focus = (self.focus - 1) % 5
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.focus = (self.focus + 1) % 5
        elif key in (pygame.K_LEFT, pygame.K_a):
            self._change(-1)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._change(1)

    def _change(self, direction: int, count_step: int = 1) -> None:
        if self.focus == 0:
            self.selected["map"] = (self.selected["map"] + direction) % len(self.maps)
        elif self.focus == 1:
            self.selected["weather"] = (self.selected["weather"] + direction) % len(self.weather)
        elif self.focus == 2 and self.vehicles:
            self.selected["vehicle"] = (self.selected["vehicle"] + direction) % len(self.vehicles)
        elif self.focus == 3:
            self.traffic = max(0, min(200, self.traffic + direction * count_step))
        elif self.focus == 4:
            self.pedestrians = max(0, min(200, self.pedestrians + direction * count_step))

    def _session_config(self) -> SessionConfig:
        vehicle = self.vehicles[self.selected["vehicle"]].blueprint_id if self.vehicles else None
        weather = self.weather[self.selected["weather"]][0] if self.weather else "ClearNoon"
        return replace(
            self.defaults,
            map_name=self.maps[self.selected["map"]],
            weather_preset=weather,
            vehicle_blueprint=vehicle,
            traffic_vehicles=self.traffic,
            pedestrians=self.pedestrians,
        )

    def _draw(self) -> None:
        width, height = self.screen.get_size()
        self.screen.fill((8, 15, 25))
        pygame.draw.rect(self.screen, (12, 25, 39), (0, 0, width, height // 2))
        self._text("CARLA DRIVE", (56, 48), self.title, (241, 247, 250))
        self._text("SESSION SETUP", (59, 99), self.small, (101, 190, 205))
        self._text("Select your environment", (56, 145), self.font, (194, 210, 220))

        panel = pygame.Rect(48, 192, min(770, width - 96), 400)
        pygame.draw.rect(self.screen, (15, 27, 41), panel, border_radius=18)
        pygame.draw.rect(self.screen, (36, 58, 75), panel, width=1, border_radius=18)
        values = [
            friendly_map_name(self.maps[self.selected["map"]]),
            self.weather[self.selected["weather"]][1] if self.weather else "Clear",
            self.vehicles[self.selected["vehicle"]].label if self.vehicles else "No four-wheel vehicles found",
            f"{self.traffic} vehicles",
            f"{self.pedestrians} pedestrians",
        ]
        labels = ["MAP", "WEATHER", "EGO VEHICLE", "VEHICLE TRAFFIC", "PEDESTRIANS"]
        self.row_rects = []
        for index, (label, value) in enumerate(zip(labels, values)):
            row = pygame.Rect(panel.x + 18, panel.y + 18 + index * 72, panel.w - 36, 58)
            self.row_rects.append(row)
            active = index == self.focus
            pygame.draw.rect(self.screen, (24, 46, 62) if active else (19, 35, 50), row, border_radius=10)
            if active:
                pygame.draw.rect(self.screen, (66, 180, 193), row, width=2, border_radius=10)
            self._text(label, (row.x + 17, row.y + 7), self.small, (133, 163, 177))
            self._text(value, (row.x + 17, row.y + 29), self.font, (235, 243, 247))
            self._text("‹", (row.right - 54, row.y + 19), self.font, (101, 190, 205))
            self._text("›", (row.right - 27, row.y + 19), self.font, (101, 190, 205))

        right_x = panel.right + 36
        self._text("READY TO DRIVE", (right_x, 219), self.font, (224, 237, 241))
        self._text("CARLA connection established", (right_x, 263), self.small, (105, 207, 167))
        self._text("Xbox controller is preferred.", (right_x, 315), self.small, (163, 181, 191))
        self._text("Keyboard fallback:", (right_x, 344), self.small, (163, 181, 191))
        self._text("W / S  accelerate / brake", (right_x, 371), self.small, (163, 181, 191))
        self._text("A / D  steer     R  reverse", (right_x, 398), self.small, (163, 181, 191))
        self._text("C / Q  camera     P  pause", (right_x, 425), self.small, (163, 181, 191))
        self._text("Space  handbrake     Esc  quit", (right_x, 452), self.small, (163, 181, 191))
        self._text("Use Up / Down to select and Left / Right to adjust.", (56, 618), self.small, (121, 145, 158))
        self._text(self.status, (56, 649), self.small, (105, 190, 205))
        self.start_rect = pygame.Rect(width - 294, height - 102, 238, 58)
        pygame.draw.rect(self.screen, (25, 164, 160), self.start_rect, border_radius=14)
        self._text("START DRIVING", (self.start_rect.x + 31, self.start_rect.y + 17), self.font, (7, 23, 32))

    def _text(self, value: str, position: tuple[int, int], font: pygame.font.Font, color: tuple[int, int, int]) -> None:
        self.screen.blit(font.render(value, True, color), position)
