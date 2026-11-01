"""Pygame driving view, mirror, LiDAR mini-panel, and telemetry."""

from __future__ import annotations

import time

import numpy as np
import pygame

from carla_drive.config import AppConfig
from carla_drive.domain import CameraMode, DrivingSnapshot
from carla_drive.perception import PerceptionFrame
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
        self._mirror_scaled_key: tuple[float, tuple[int, int]] | None = None
        self._mirror_scaled: pygame.Surface | None = None
        self._lidar_key: float | None = None
        self._lidar_surface: pygame.Surface | None = None
        self._perception_key: float | None = None
        self._perception_surface: pygame.Surface | None = None
        self._perception_scaled_key: tuple[float, tuple[int, int]] | None = None
        self._perception_scaled: pygame.Surface | None = None
        self._edge_shade_size: tuple[int, int] | None = None
        self._edge_shade: pygame.Surface | None = None

    def render(
        self,
        snapshot: DrivingSnapshot,
        main_frame: tuple[np.ndarray | None, float],
        mirror_frame: tuple[np.ndarray | None, float],
        lidar_frame: tuple[np.ndarray | None, float],
        controller_name: str,
        paused: bool,
        status: str,
        perception_state: tuple[PerceptionFrame | None, str] = (None, "DISABLED"),
        perception_view: bool = False,
    ) -> None:
        width, height = self.screen.get_size()
        if perception_view:
            self._draw_perception_view(width, height, perception_state, lidar_frame, paused)
        else:
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

    def _draw_perception_view(self, width: int, height: int, state, lidar_frame, paused: bool) -> None:
        result, status = state
        self.screen.fill((0, 0, 0))
        self._text("YOLOPv2  /  PERCEPTION OUTPUT", (20, 18), self.font, (228, 241, 244))
        camera = self.config.perception
        self._text(
            f"FRONT ROOF  /  {camera.camera_width}×{camera.camera_height}  /  INPUT {camera.input_size}  /  {1.0 / camera.inference_interval_seconds:.0f} FPS  /  {camera.camera_fov:.0f}° FOV",
            (20, 44), self.small, (128, 157, 169),
        )

        status_color = (89, 220, 167) if status == "LIVE" else (242, 184, 111)
        status_label = "HOLD" if paused and status == "LIVE" else status
        self._text(status_label[:34], (20, 68), self.small, status_color)
        self._text("V  CAMERA VIEW", (width - 368, 18), self.small, (155, 183, 193))

        viewport = pygame.Rect(18, 92, width - 370, height - 116)
        pygame.draw.rect(self.screen, (4, 7, 9), viewport)
        pygame.draw.rect(self.screen, (38, 55, 63), viewport, width=1)
        if result is not None:
            self._draw_masks_and_boxes(result, viewport)
            self._text(
                f"{len(result.detections)} OBJECTS  /  {result.inference_ms:.0f} ms",
                (viewport.x + 12, viewport.bottom - 24), self.small, (197, 218, 221),
            )
        else:
            self._text("WAITING FOR MODEL OUTPUT", viewport.center, self.small, (124, 151, 160), centered=True)

        self._draw_lidar(width, lidar_frame, paused)
        self._draw_perception_summary(width, height, result)

    def _draw_masks_and_boxes(self, result: PerceptionFrame, viewport: pygame.Rect) -> None:
        source_size = (result.source_width, result.source_height)
        scale = min(viewport.width / source_size[0], viewport.height / source_size[1])
        draw_width = max(1, int(source_size[0] * scale))
        draw_height = max(1, int(source_size[1] * scale))
        draw_rect = pygame.Rect(0, 0, draw_width, draw_height)
        draw_rect.center = viewport.center

        if result.received_at != self._perception_key:
            road = result.driving_area >= 0.5
            lanes = result.lane_lines >= 0.45
            pixels = np.zeros((result.source_height, result.source_width, 3), dtype=np.uint8)
            pixels[road] = (0, 78, 64)
            pixels[lanes] = (250, 215, 93)
            self._perception_surface = pygame.surfarray.make_surface(np.swapaxes(pixels, 0, 1))
            self._perception_key = result.received_at
            self._perception_scaled_key = None
        scale_key = (result.received_at, draw_rect.size)
        if self._perception_surface is not None and scale_key != self._perception_scaled_key:
            self._perception_scaled = pygame.transform.smoothscale(self._perception_surface, draw_rect.size)
            self._perception_scaled_key = scale_key
        if self._perception_scaled is not None:
            self.screen.blit(self._perception_scaled, draw_rect)

        palette = (
            (80, 220, 255), (255, 180, 68), (255, 91, 86), (100, 236, 149),
            (189, 139, 255), (255, 220, 92), (85, 171, 255), (255, 119, 190),
        )
        scale_x = draw_width / result.source_width
        scale_y = draw_height / result.source_height
        for detection in result.detections:
            x1, y1, x2, y2 = detection.box
            box = pygame.Rect(
                draw_rect.x + int(x1 * scale_x),
                draw_rect.y + int(y1 * scale_y),
                max(1, int((x2 - x1) * scale_x)),
                max(1, int((y2 - y1) * scale_y)),
            )
            color = palette[detection.class_id % len(palette)]
            pygame.draw.rect(self.screen, color, box, width=2)
            label = f"{detection.class_name} {detection.confidence:.2f}"
            text = self.small.render(label, True, (245, 249, 250))
            label_y = max(draw_rect.y, box.y - text.get_height() - 3)
            label_x = min(box.x, draw_rect.right - text.get_width() - 8)
            label_rect = pygame.Rect(label_x, label_y, text.get_width() + 8, text.get_height() + 4)
            pygame.draw.rect(self.screen, (7, 14, 17), label_rect)
            self.screen.blit(text, (label_rect.x + 4, label_rect.y + 2))

    def _draw_perception_summary(self, width: int, height: int, result: PerceptionFrame | None) -> None:
        x = width - 328
        y = 344
        panel = pygame.Rect(x, y, 306, height - y - 18)
        pygame.draw.rect(self.screen, (5, 12, 16), panel, border_radius=10)
        pygame.draw.rect(self.screen, (42, 67, 76), panel, width=1, border_radius=10)
        self._text("MODEL OUTPUTS", (x + 14, y + 12), self.font, (213, 230, 234))
        self._text("770  OBJECT DETECTIONS", (x + 14, y + 48), self.small, (96, 218, 182))
        self._text("677  DRIVING-AREA MASK", (x + 14, y + 76), self.small, (96, 218, 182))
        self._text("769  LANE-LINE MASK", (x + 14, y + 104), self.small, (246, 212, 99))
        if result is not None:
            road_percent = float(np.count_nonzero(result.driving_area >= 0.5)) * 100.0 / result.driving_area.size
            lane_percent = float(np.count_nonzero(result.lane_lines >= 0.45)) * 100.0 / result.lane_lines.size
            self._text(f"DETECTIONS  {len(result.detections)}", (x + 14, y + 150), self.small, (219, 231, 233))
            self._text(f"ROAD PIXELS  {road_percent:.1f}%", (x + 14, y + 177), self.small, (219, 231, 233))
            self._text(f"LANE PIXELS  {lane_percent:.1f}%", (x + 14, y + 204), self.small, (219, 231, 233))
            self._text("ROAD AREA", (x + 14, y + 244), self.lidar_small, (0, 155, 127))
            self._text("LANE LINES", (x + 128, y + 244), self.lidar_small, (246, 212, 99))

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
        size = (width, height)
        if self._edge_shade_size != size:
            self._edge_shade = pygame.Surface(size, pygame.SRCALPHA)
            pygame.draw.rect(self._edge_shade, (2, 8, 15, 26), (0, 0, width, 104))
            pygame.draw.rect(self._edge_shade, (2, 8, 15, 42), (0, height - 176, width, 176))
            self._edge_shade_size = size
        self.screen.blit(self._edge_shade, (0, 0))

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
            cache_key = (frame[1], inner.size)
            if cache_key != self._mirror_scaled_key:
                self._mirror_scaled = pygame.transform.scale(surface, inner.size)
                self._mirror_scaled_key = cache_key
            self.screen.blit(self._mirror_scaled, inner)
        else:
            pygame.draw.rect(self.screen, (16, 28, 37), inner, border_radius=5)
            self._text("REAR VIEW", inner.center, self.small, (117, 145, 157), centered=True)
        self._text("REAR VIEW", (outer.x + 8, outer.bottom + 3), self.small, (178, 197, 205))

    def _draw_lidar(self, width: int, frame, paused: bool) -> None:
        points, timestamp = frame
        if timestamp <= 0.0:
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
        elif time.monotonic() - timestamp > 1.5:
            state, state_color = "STALE", (237, 168, 112)
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
            forward = points[:, 0]
            lateral = points[:, 1]
            height = points[:, 2]
            age = np.maximum(0.0, points[:, 3]) if points.shape[1] > 3 else np.zeros(len(points))
            distance = np.hypot(forward, lateral)
            px = np.rint(center[0] + lateral * scale).astype(np.int32)
            py = np.rint(center[1] - forward * scale).astype(np.int32)
            visible = (
                np.isfinite(points).all(axis=1)
                & (distance <= view_range)
                & (px >= 1)
                & (px < size[0] - 1)
                & (py >= 1)
                & (py < size[1] - 1)
            )
            px, py, distance, height, age = px[visible], py[visible], distance[visible], height[visible], age[visible]
            base_colors = np.where(
                (height < -1.2)[:, None],
                (90, 166, 255),
                np.where((height < 0.4)[:, None], (76, 227, 191), (255, 174, 90)),
            )
            distance_brightness = 0.72 + 0.28 * (1.0 - distance / view_range)
            age_brightness = 0.15 + 0.85 * np.clip(1.0 - age / self.config.lidar.persistence_seconds, 0.0, 1.0)
            brightness = (distance_brightness * age_brightness)[:, None]
            colors = np.clip(base_colors * brightness, 0, 255).astype(np.uint8)
            radii = np.where(distance < 7.0, 3, np.where(distance < 17.0, 2, 1))
            radii = np.where(age > self.config.lidar.persistence_seconds * 0.6, np.maximum(1, radii - 1), radii)
            pixels = pygame.surfarray.pixels3d(surface)
            pixels[px, py] = colors
            larger = radii >= 2
            for offset_x, offset_y in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                pixels[px[larger] + offset_x, py[larger] + offset_y] = colors[larger]
            largest = radii >= 3
            for offset_x, offset_y in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                pixels[px[largest] + offset_x, py[largest] + offset_y] = colors[largest]
            del pixels

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
