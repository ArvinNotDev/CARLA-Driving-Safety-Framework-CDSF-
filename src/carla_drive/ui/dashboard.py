"""Pygame driving view, mirror, LiDAR mini-panel, and telemetry."""

from __future__ import annotations

import math
import time

import numpy as np
import pygame

from carla_drive.config import AppConfig
from carla_drive.domain import CameraMode, DrivingSnapshot
from carla_drive.sensors.parking import parking_side_fills


class Dashboard:
    def __init__(self, screen: pygame.Surface, config: AppConfig):
        self.screen = screen
        self.config = config
        self.font = pygame.font.Font(None, 22)
        self.small = pygame.font.Font(None, 18)
        self.lidar_small = pygame.font.Font(None, 14)
        self.speed_font = pygame.font.Font(None, 62)
        self.gear_font = pygame.font.Font(None, 40)
        self._main_key: float | None = None
        self._main_surface: pygame.Surface | None = None
        self._main_scaled_key: tuple[float, tuple[int, int]] | None = None
        self._main_scaled: pygame.Surface | None = None
        self._mirror_key: float | None = None
        self._mirror_surface: pygame.Surface | None = None
        self._lidar_key: float | None = None
        self._lidar_surface: pygame.Surface | None = None

    def render(
        self,
        snapshot: DrivingSnapshot,
        main_frame: tuple[np.ndarray | None, float],
        mirror_frame: tuple[np.ndarray | None, float],
        lidar_frame: tuple[np.ndarray | None, float],
        controller_name: str,
        paused: bool,
        status: str,
    ) -> None:
        width, height = self.screen.get_size()
        self.screen.fill((5, 10, 16))
        main_surface = self._camera_surface(main_frame, mirror=False, allow_stale=paused)
        if main_surface is not None:
            cache_key = (main_frame[1], (width, height))
            if cache_key != self._main_scaled_key:
                self._main_scaled = pygame.transform.scale(main_surface, (width, height))
                self._main_scaled_key = cache_key
            self.screen.blit(self._main_scaled, (0, 0))
        else:
            self._text("WAITING FOR CARLA CAMERA", (width // 2, height // 2), self.font, (202, 220, 228), centered=True)
        self._draw_edge_shade(width, height)
        self._draw_status(width, status, paused)
        self._draw_mirror(width, mirror_frame, paused)
        self._draw_lidar(width, lidar_frame, paused)
        self._draw_parking_bar(width, snapshot)
        self._draw_telemetry(width, height, snapshot, controller_name)

    def _camera_surface(self, frame, mirror: bool, allow_stale: bool = False) -> pygame.Surface | None:
        image, timestamp = frame
        if image is None or timestamp <= 0.0 or (not allow_stale and time.monotonic() - timestamp > 2.0):
            return None
        if mirror:
            if timestamp != self._mirror_key:
                surface = pygame.surfarray.make_surface(np.swapaxes(image, 0, 1))
                self._mirror_surface = pygame.transform.flip(surface, True, False)
                self._mirror_key = timestamp
            return self._mirror_surface
        if timestamp != self._main_key:
            self._main_surface = pygame.surfarray.make_surface(np.swapaxes(image, 0, 1))
            self._main_key = timestamp
        return self._main_surface

    def _draw_edge_shade(self, width: int, height: int) -> None:
        shade = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(shade, (2, 8, 15, 26), (0, 0, width, 104))
        pygame.draw.rect(shade, (2, 8, 15, 42), (0, height - 176, width, 176))
        self.screen.blit(shade, (0, 0))

    def _draw_status(self, width: int, status: str, paused: bool) -> None:
        badge = pygame.Rect(20, 18, 182, 38)
        pygame.draw.rect(self.screen, (7, 20, 31, 225), badge, border_radius=10)
        label = "PAUSED" if paused else "CARLA DRIVE  /  MANUAL"
        color = (255, 194, 105) if paused else (156, 226, 217)
        self._text(label, (badge.x + 12, badge.y + 11), self.small, color)
        if status:
            self._text(status, (20, 64), self.small, (250, 201, 139))
        self._text("1 Cockpit    2 Chase    3 Overhead", (20, 92), self.small, (198, 212, 220))

    def _draw_mirror(self, width: int, frame, paused: bool) -> None:
        target_width = min(int(width * 0.29), 380)
        target_height = int(target_width * 0.285)
        x = (width - target_width) // 2
        y = 16
        outer = pygame.Rect(x - 8, y - 8, target_width + 16, target_height + 16)
        pygame.draw.rect(self.screen, (8, 14, 21), outer, border_radius=12)
        pygame.draw.rect(self.screen, (144, 169, 179), outer, width=2, border_radius=12)
        surface = self._camera_surface(frame, mirror=True, allow_stale=paused)
        inner = pygame.Rect(x, y, target_width, target_height)
        if surface is not None:
            self.screen.blit(pygame.transform.scale(surface, inner.size), inner)
        else:
            pygame.draw.rect(self.screen, (16, 28, 37), inner, border_radius=5)
            self._text("REAR VIEW", inner.center, self.small, (117, 145, 157), centered=True)
        self._text("REAR VIEW", (outer.x + 8, outer.bottom + 3), self.small, (178, 197, 205))

    def _draw_lidar(self, width: int, frame, paused: bool) -> None:
        points, timestamp = frame
        if timestamp <= 0.0 or (not paused and time.monotonic() - timestamp > 1.5):
            points = None
        panel_width, panel_height = 320, 310
        x, y = width - panel_width - 20, 20
        panel = pygame.Rect(x, y, panel_width, panel_height)
        pygame.draw.rect(self.screen, (7, 17, 27), panel, border_radius=12)
        pygame.draw.rect(self.screen, (64, 91, 108), panel, width=1, border_radius=12)
        self._text("360°  LIDAR", (x + 14, y + 9), self.font, (225, 239, 243))
        self._text(
            f"HEIGHT COLOR  /  TOP VIEW  /  {self.config.lidar.display_range_m:.0f} M",
            (x + 14, y + 31),
            self.lidar_small,
            (132, 163, 177),
        )
        if not self.config.lidar.enabled:
            state, state_color = "OFF", (145, 159, 167)
        elif points is None:
            state, state_color = "NO DATA", (237, 168, 112)
        elif paused:
            state, state_color = "HOLD", (246, 194, 107)
        else:
            state, state_color = "LIVE", (87, 214, 163)
        state_rect = pygame.Rect(panel.right - 77, y + 10, 63, 23)
        pygame.draw.rect(self.screen, (22, 49, 48), state_rect, border_radius=8)
        self._text(state, state_rect.center, self.lidar_small, state_color, centered=True)

        canvas_rect = pygame.Rect(x + 12, y + 54, panel_width - 24, 220)
        if self._lidar_key != (timestamp if points is not None else 0.0):
            self._lidar_surface = self._build_lidar_surface(canvas_rect.size, points)
            self._lidar_key = timestamp if points is not None else 0.0
        if self._lidar_surface:
            self.screen.blit(self._lidar_surface, canvas_rect)
        if points is None:
            message = "SENSOR DISABLED" if not self.config.lidar.enabled else "WAITING FOR RETURNS"
            self._text(message, canvas_rect.center, self.lidar_small, (145, 168, 178), centered=True)

        legend_y = y + 288
        legend = (("LOW", (90, 166, 255)), ("MID", (76, 227, 191)), ("HIGH", (255, 174, 90)))
        for index, (label, color) in enumerate(legend):
            legend_x = x + 16 + index * 89
            pygame.draw.circle(self.screen, color, (legend_x + 4, legend_y + 6), 3)
            self._text(label, (legend_x + 12, legend_y), self.lidar_small, (157, 181, 191))

    def _build_lidar_surface(self, size: tuple[int, int], points: np.ndarray | None) -> pygame.Surface:
        surface = pygame.Surface(size, pygame.SRCALPHA)
        surface.fill((5, 13, 21, 235))
        center = (size[0] // 2, size[1] // 2)
        radius = int(min(size) * 0.45)
        view_range = self.config.lidar.display_range_m
        for fraction in (0.25, 0.5, 0.75, 1.0):
            ring_radius = int(radius * fraction)
            pygame.draw.circle(surface, (40, 67, 82), center, ring_radius, 1)
            if fraction < 1.0:
                distance_label = f"{view_range * fraction:.0f}m"
                label = self.lidar_small.render(distance_label, True, (108, 137, 151))
                label_x = center[0] + int(ring_radius * 0.62) + 2
                label_y = center[1] - int(ring_radius * 0.72) - label.get_height() // 2
                label_back = pygame.Rect(label_x - 2, label_y - 1, label.get_width() + 4, label.get_height() + 2)
                pygame.draw.rect(surface, (5, 13, 21), label_back, border_radius=3)
                surface.blit(label, (label_x, label_y))
        pygame.draw.line(surface, (45, 71, 87), (center[0], center[1] - radius), (center[0], center[1] + radius), 1)
        pygame.draw.line(surface, (45, 71, 87), (center[0] - radius, center[1]), (center[0] + radius, center[1]), 1)
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            start = (center[0] + int(dx * radius * 0.93), center[1] + int(dy * radius * 0.93))
            end = (center[0] + int(dx * radius), center[1] + int(dy * radius))
            pygame.draw.line(surface, (89, 126, 142), start, end, 2)

        if points is not None and len(points):
            scale = radius / view_range
            for point in points:
                forward, lateral = float(point[0]), float(point[1])
                distance = math.hypot(forward, lateral)
                if distance > view_range:
                    continue
                px = int(center[0] + lateral * scale)
                py = int(center[1] - forward * scale)
                if not (1 <= px < size[0] - 1 and 1 <= py < size[1] - 1):
                    continue

                height = float(point[2])
                if height < -1.2:
                    base_color = (90, 166, 255)
                elif height < 0.4:
                    base_color = (76, 227, 191)
                else:
                    base_color = (255, 174, 90)
                brightness = 0.72 + 0.28 * (1.0 - distance / view_range)
                color = tuple(int(channel * brightness) for channel in base_color)
                point_radius = 3 if distance < 7.0 else 2 if distance < 17.0 else 1
                pygame.draw.circle(surface, color, (px, py), point_radius)

        for label, position in (
            ("F", (center[0] - 3, 1)),
            ("B", (center[0] - 3, size[1] - self.lidar_small.get_height() - 1)),
            ("L", (1, center[1] - self.lidar_small.get_height() // 2)),
            ("R", (size[0] - self.lidar_small.size("R")[0] - 1, center[1] - self.lidar_small.get_height() // 2)),
        ):
            surface.blit(self.lidar_small.render(label, True, (124, 153, 167)), position)

        vehicle = [
            (center[0], center[1] - 9),
            (center[0] + 5, center[1] - 3),
            (center[0] + 5, center[1] + 8),
            (center[0] - 5, center[1] + 8),
            (center[0] - 5, center[1] - 3),
        ]
        pygame.draw.polygon(surface, (6, 20, 29), vehicle)
        pygame.draw.polygon(surface, (221, 242, 240), vehicle, 1)
        pygame.draw.line(surface, (221, 242, 240), (center[0] - 2, center[1] + 1), (center[0] + 2, center[1] + 1), 1)
        return surface

    def _draw_parking_bar(self, width: int, snapshot: DrivingSnapshot) -> None:
        if not snapshot.vehicle.reverse:
            return
        center_x = width // 2
        y = 156
        bar_width = min(340, int(width * 0.30))
        half = bar_width // 2
        distance = snapshot.rear_distance.closest_m
        left_fill, right_fill = parking_side_fills(snapshot.rear_distance, self.config.rear_parking.distance_m)
        panel = pygame.Rect(center_x - half - 12, y - 8, bar_width + 24, 42)
        pygame.draw.rect(self.screen, (7, 16, 24), panel, border_radius=11)
        pygame.draw.rect(self.screen, (63, 83, 96), panel, width=1, border_radius=11)
        track_y = y + 15
        pygame.draw.line(self.screen, (56, 77, 89), (center_x - half, track_y), (center_x + half, track_y), 8)
        if distance is not None:
            danger = max(0.0, min(1.0, 1.0 - distance / self.config.rear_parking.warning_distance_m))
            color = (int(70 + 185 * danger), int(205 - 165 * danger), int(85 - 40 * danger))
            if left_fill:
                amount = max(3, int(half * left_fill))
                pygame.draw.line(self.screen, color, (center_x - amount, track_y), (center_x, track_y), 8)
            if right_fill:
                amount = max(3, int(half * right_fill))
                pygame.draw.line(self.screen, color, (center_x, track_y), (center_x + amount, track_y), 8)
        pygame.draw.line(self.screen, (218, 231, 235), (center_x, track_y - 12), (center_x, track_y + 12), 2)
        label = "NO TARGET" if distance is None else f"{distance:.1f} m"
        self._text(label, (center_x, panel.bottom + 5), self.small, (220, 231, 234), centered=True)

    def _draw_telemetry(self, width: int, height: int, snapshot: DrivingSnapshot, controller_name: str) -> None:
        vehicle = snapshot.vehicle
        speed_box = pygame.Rect(22, height - 142, 260, 116)
        self._panel(speed_box)
        self._text(f"{vehicle.speed_kmh:05.1f}", (speed_box.x + 18, speed_box.y + 15), self.speed_font, (245, 250, 252))
        self._text("km/h", (speed_box.x + 154, speed_box.y + 42), self.font, (142, 176, 190))
        gear_color = (251, 180, 96) if vehicle.reverse else (108, 222, 196)
        self._text(vehicle.gear, (speed_box.right - 47, speed_box.y + 29), self.gear_font, gear_color)
        self._text(f"CAMERA  {snapshot.camera_mode.value.upper()}", (speed_box.x + 18, speed_box.bottom - 22), self.small, (167, 190, 200))

        panel = pygame.Rect(width - 328, height - 142, 306, 116)
        self._panel(panel)
        self._text(f"CONTROLS  /  {controller_name[:18]}", (panel.x + 14, panel.y + 11), self.small, (175, 201, 211))
        self._bar(panel.x + 14, panel.y + 42, "THR", vehicle.throttle, (75, 202, 166), panel.w - 28)
        self._bar(panel.x + 14, panel.y + 66, "BRK", vehicle.brake, (231, 114, 105), panel.w - 28)
        steer_x = panel.x + 14
        steer_y = panel.y + 94
        track = pygame.Rect(steer_x + 47, steer_y, panel.w - 65, 6)
        pygame.draw.rect(self.screen, (42, 61, 73), track, border_radius=3)
        marker = track.centerx + int(vehicle.steering * (track.w // 2))
        pygame.draw.circle(self.screen, (100, 206, 219), (marker, track.centery), 5)
        self._text("STEER", (steer_x, steer_y - 6), self.small, (158, 181, 191))

    def _panel(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.screen, (7, 18, 28), rect, border_radius=14)
        pygame.draw.rect(self.screen, (49, 71, 85), rect, width=1, border_radius=14)

    def _bar(self, x: int, y: int, label: str, value: float, color: tuple[int, int, int], width: int) -> None:
        self._text(label, (x, y - 2), self.small, (153, 179, 190))
        track = pygame.Rect(x + 47, y, width - 47, 8)
        pygame.draw.rect(self.screen, (40, 58, 70), track, border_radius=4)
        amount = max(0, min(track.w, int(track.w * value)))
        if amount:
            pygame.draw.rect(self.screen, color, (track.x, track.y, amount, track.h), border_radius=4)

    def _text(self, value: str, position: tuple[int, int], font: pygame.font.Font, color, centered: bool = False) -> None:
        rendered = font.render(value, True, color)
        rect = rendered.get_rect(center=position) if centered else rendered.get_rect(topleft=position)
        self.screen.blit(rendered, rect)
