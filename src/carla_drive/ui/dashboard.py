"""Pygame driving view, mirror, LiDAR mini-panel, and telemetry."""

from __future__ import annotations

import time

import numpy as np
import pygame

from carla_drive.config import AppConfig
from carla_drive.domain import CameraMode, DrivingSnapshot
from carla_drive.perception import PerceptionFrame


class Dashboard:
    def __init__(self, screen: pygame.Surface, config: AppConfig):
        self.screen = screen
        self.config = config
        self.font = pygame.font.Font(None, 22)
        self.small = pygame.font.Font(None, 18)
        self.lidar_small = pygame.font.Font(None, 14)
        self.tiny = pygame.font.Font(None, 15)
        self.title = pygame.font.Font(None, 28)
        self.speed_font = pygame.font.Font(None, 62)
        self._main_key: float | None = None
        self._main_surface: pygame.Surface | None = None
        self._main_scaled_key: tuple[float, tuple[int, int]] | None = None
        self._main_scaled: pygame.Surface | None = None
        self._mirror_key: float | None = None
        self._mirror_surface: pygame.Surface | None = None
        self._mirror_scaled_key: tuple[float, tuple[int, int]] | None = None
        self._mirror_scaled: pygame.Surface | None = None
        self._lidar_key: tuple[float, tuple[int, int]] | None = None
        self._lidar_surface: pygame.Surface | None = None
        self._perception_key: float | None = None
        self._perception_surface: pygame.Surface | None = None
        self._perception_scaled_key: tuple[float, tuple[int, int]] | None = None
        self._perception_scaled: pygame.Surface | None = None

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
    ) -> None:
        width, height = self.screen.get_size()
        self.screen.fill((4, 9, 16))

        margin, gap = 16, 12
        left_width = max(170, int(width * 0.155))
        right_width = max(194, int(width * 0.19))
        center_width = width - 2 * margin - left_width - right_width - 2 * gap
        content_y = 58
        footer_y = height - 70
        content_height = footer_y - content_y - 10
        left_panel = pygame.Rect(margin, content_y, left_width, content_height)
        center_panel = pygame.Rect(left_panel.right + gap, content_y, center_width, content_height)
        right_panel = pygame.Rect(center_panel.right + gap, content_y, right_width, content_height)

        result, perception_status = perception_state
        self._draw_header(width, snapshot, paused, perception_status)
        self._draw_lidar_sidebar(left_panel, lidar_frame, mirror_frame, snapshot, paused)
        self._draw_camera_panel(center_panel, main_frame, snapshot, paused)
        self._draw_ai_sidebar(right_panel, result, perception_status)
        self._draw_footer(width, height, snapshot, controller_name, status, paused)

    def _draw_header(self, width: int, snapshot: DrivingSnapshot, paused: bool, perception_status: str) -> None:
        pygame.draw.rect(self.screen, (7, 16, 26), (0, 0, width, 51))
        pygame.draw.line(self.screen, (52, 194, 177), (0, 0), (width, 0), 3)
        self._text("CARLA DRIVE", (16, 8), self.title, (235, 245, 247))
        self._text("DRIVER ASSIST  /  LIVE VEHICLE TELEMETRY", (18, 34), self.tiny, (119, 150, 164))

        mode = snapshot.camera_mode.value.upper()
        self._status_pill(width - 354, 13, "PAUSED" if paused else "SIMULATION LIVE", (244, 187, 102) if paused else (75, 215, 164))
        model_state = (
            "LIVE" if perception_status == "LIVE" else
            "OFF" if perception_status == "DISABLED" else
            "STALE" if perception_status.startswith("STALE") else
            "ERROR" if "ERROR" in perception_status or "UNAVAILABLE" in perception_status else
            "LOAD"
        )
        model_color = (78, 216, 165) if model_state == "LIVE" else (145, 162, 171) if model_state == "OFF" else (243, 146, 120) if model_state == "ERROR" else (243, 181, 103)
        self._status_pill(width - 174, 13, f"YOLO {model_state}", model_color)
        self._text(f"CAMERA  {mode}", (width - 354, 33), self.tiny, (150, 177, 187))
        self._text(f"INFERENCE  {1.0 / self.config.perception.inference_interval_seconds:.0f} HZ", (width - 174, 33), self.tiny, (150, 177, 187))

    def _status_pill(self, x: int, y: int, label: str, color: tuple[int, int, int]) -> None:
        text_width = self.tiny.size(label)[0]
        rect = pygame.Rect(x, y, text_width + 24, 22)
        pygame.draw.rect(self.screen, (17, 37, 44), rect, border_radius=9)
        pygame.draw.circle(self.screen, color, (x + 10, y + 11), 3)
        self._text(label, (x + 18, y + 4), self.tiny, color)

    def _draw_camera_panel(self, panel: pygame.Rect, frame, snapshot: DrivingSnapshot, paused: bool) -> None:
        self._panel(panel)
        self._text("DRIVING CAMERA", (panel.x + 14, panel.y + 10), self.font, (223, 238, 242))
        self._text("FRONT VIEW  /  LIVE SENSOR FEED", (panel.x + 14, panel.y + 31), self.tiny, (123, 153, 166))
        mode = snapshot.camera_mode.value.upper()
        mode_rect = pygame.Rect(panel.right - 117, panel.y + 10, 103, 24)
        pygame.draw.rect(self.screen, (18, 43, 51), mode_rect, border_radius=8)
        self._text(mode, mode_rect.center, self.tiny, (104, 218, 199), centered=True)

        view_rect = pygame.Rect(panel.x + 10, panel.y + 54, panel.w - 20, panel.h - 92)
        pygame.draw.rect(self.screen, (2, 6, 10), view_rect, border_radius=7)
        surface = self._camera_surface(frame, mirror=False, allow_stale=paused)
        if surface is None:
            self._text("WAITING FOR FRONT CAMERA", view_rect.center, self.small, (133, 163, 176), centered=True)
        else:
            scale = min(view_rect.w / surface.get_width(), view_rect.h / surface.get_height())
            size = (max(1, int(surface.get_width() * scale)), max(1, int(surface.get_height() * scale)))
            cache_key = (frame[1], size)
            if cache_key != self._main_scaled_key:
                self._main_scaled = pygame.transform.scale(surface, size)
                self._main_scaled_key = cache_key
            destination = self._main_scaled.get_rect(center=view_rect.center)
            self.screen.blit(self._main_scaled, destination)
            age = max(0.0, time.monotonic() - frame[1])
            live = age < 1.0 or paused
            dot = (76, 218, 162) if live else (238, 171, 99)
            pygame.draw.circle(self.screen, dot, (view_rect.x + 15, view_rect.y + 15), 4)
            self._text("LIVE" if live else "STALE", (view_rect.x + 25, view_rect.y + 8), self.tiny, dot)
        pygame.draw.rect(self.screen, (45, 68, 80), view_rect, width=1, border_radius=7)
        self._text("WASD DRIVE   ·   1 / 2 / 3 CAMERA   ·   ESC PAUSE", (panel.x + 14, panel.bottom - 26), self.tiny, (129, 157, 169))

    def _draw_lidar_sidebar(self, panel: pygame.Rect, lidar_frame, mirror_frame, snapshot: DrivingSnapshot, paused: bool) -> None:
        self._panel(panel)
        self._text("360° LiDAR", (panel.x + 12, panel.y + 10), self.font, (223, 238, 242))
        points, timestamp = lidar_frame
        cloud_available = (
            self.config.lidar.enabled
            and points is not None
            and timestamp > 0.0
        )
        lidar_fresh = cloud_available and time.monotonic() - timestamp <= 1.5
        lidar_live = lidar_fresh or (paused and cloud_available)
        state = (
            "OFF" if not self.config.lidar.enabled else
            "LIVE" if lidar_fresh else
            "HOLD" if paused and cloud_available else
            "STALE" if cloud_available else
            "NO DATA"
        )
        state_color = (145, 162, 171) if state in {"OFF", "NO DATA"} else (245, 190, 106) if state in {"HOLD", "STALE"} else (78, 216, 165)
        badge = pygame.Rect(panel.right - 70, panel.y + 10, 58, 21)
        pygame.draw.rect(self.screen, (18, 43, 47), badge, border_radius=8)
        self._text(state, badge.center, self.tiny, state_color, centered=True)
        self._text(f"TOP VIEW  /  {self.config.lidar.display_range_m:.0f} M", (panel.x + 12, panel.y + 32), self.tiny, (123, 153, 166))

        radar_size = min(panel.w - 24, 176)
        radar_rect = pygame.Rect(0, 0, radar_size, radar_size)
        radar_rect.centerx = panel.centerx
        radar_rect.y = panel.y + 52
        lidar_key = (timestamp if cloud_available else 0.0, radar_rect.size)
        if lidar_key != self._lidar_key:
            self._lidar_surface = self._build_lidar_surface(radar_rect.size, points if cloud_available else None)
            self._lidar_key = lidar_key
        if self._lidar_surface is not None:
            self.screen.blit(self._lidar_surface, radar_rect)

        legend_y = radar_rect.bottom + 2
        for index, (label, color) in enumerate((("LOW", (90, 166, 255)), ("MID", (76, 227, 191)), ("HIGH", (255, 174, 90)))):
            legend_x = panel.x + 16 + index * max(53, (panel.w - 32) // 3)
            pygame.draw.circle(self.screen, color, (legend_x + 3, legend_y + 7), 3)
            self._text(label, (legend_x + 10, legend_y), self.tiny, (151, 177, 187))

        mirror_y = legend_y + 20
        self._text("REAR CAMERA", (panel.x + 12, mirror_y), self.tiny, (185, 205, 212))
        mirror_rect = pygame.Rect(panel.x + 12, mirror_y + 18, panel.w - 24, 48)
        pygame.draw.rect(self.screen, (3, 8, 12), mirror_rect, border_radius=5)
        mirror = self._camera_surface(mirror_frame, mirror=True, allow_stale=paused)
        if mirror is not None:
            mirror_key = (mirror_frame[1], mirror_rect.size)
            if mirror_key != self._mirror_scaled_key:
                self._mirror_scaled = pygame.transform.scale(mirror, mirror_rect.size)
                self._mirror_scaled_key = mirror_key
            self.screen.blit(self._mirror_scaled, mirror_rect)
        else:
            self._text("NO REAR SIGNAL", mirror_rect.center, self.tiny, (128, 153, 162), centered=True)
        pygame.draw.rect(self.screen, (43, 64, 75), mirror_rect, width=1, border_radius=5)

        range_y = mirror_rect.bottom + 16
        self._text("PROXIMITY", (panel.x + 12, range_y), self.small, (207, 224, 229))
        self._text("FWD  ·  REAR  ·  LEFT  ·  RIGHT", (panel.x + 12, range_y + 19), self.tiny, (115, 146, 160))
        distances, sources = self._directional_ranges(lidar_frame, snapshot.rear_distance, lidar_live)
        for index, label in enumerate(("FRONT", "REAR", "LEFT", "RIGHT")):
            y = range_y + 42 + index * 39
            self._draw_range_row(pygame.Rect(panel.x + 10, y, panel.w - 20, 33), label, distances[label], sources[label])

    def _directional_ranges(self, lidar_frame, rear_distance, lidar_live: bool):
        points, _ = lidar_frame
        values: dict[str, float | None] = {"FRONT": None, "REAR": None, "LEFT": None, "RIGHT": None}
        sources = {label: lidar_live for label in values}
        if lidar_live and points is not None and len(points):
            finite = np.isfinite(points[:, :3]).all(axis=1)
            distance = np.hypot(points[:, 0], points[:, 1])
            useful = finite & (distance > 0.8) & (distance <= self.config.lidar.display_range_m) & (points[:, 2] > -1.2) & (points[:, 2] < 2.8)
            if points.shape[1] > 3:
                useful &= points[:, 3] <= self.config.lidar.persistence_seconds
            x, y = points[:, 0], points[:, 1]
            sectors = {
                "FRONT": useful & (x > 0.0) & (x >= np.abs(y)),
                "REAR": useful & (x < 0.0) & (-x >= np.abs(y)),
                "LEFT": useful & (y < 0.0) & (-y > np.abs(x)),
                "RIGHT": useful & (y > 0.0) & (y >= np.abs(x)),
            }
            for label, mask in sectors.items():
                if np.any(mask):
                    values[label] = float(np.min(distance[mask]))
        rear = rear_distance.closest_m
        if rear is not None:
            values["REAR"] = rear
            sources["REAR"] = True
        return values, sources

    def _draw_range_row(self, rect: pygame.Rect, label: str, distance: float | None, has_signal: bool) -> None:
        self._panel(rect)
        label_font = self.tiny
        self._text(label, (rect.x + 7, rect.y + 10), label_font, (157, 182, 192))
        if distance is None:
            value = "CLEAR" if has_signal else "NO DATA"
            color = (78, 204, 155) if has_signal else (111, 137, 148)
            fill = 0.0
        else:
            value = f"{distance:.1f}m"
            color = (245, 111, 104) if distance < 2.0 else (246, 184, 100) if distance < 6.0 else (82, 216, 163)
            fill = max(0.0, min(1.0, 1.0 - distance / self.config.lidar.display_range_m))
        value_surface = self.tiny.render(value, True, color)
        self.screen.blit(value_surface, value_surface.get_rect(right=rect.right - 7, centery=rect.centery - 3))
        track = pygame.Rect(rect.x + 7, rect.bottom - 7, rect.w - 14, 3)
        pygame.draw.rect(self.screen, (33, 51, 62), track, border_radius=2)
        if fill > 0.0:
            pygame.draw.rect(self.screen, color, (track.x, track.y, max(2, int(track.w * fill)), track.h), border_radius=2)

    def _draw_ai_sidebar(self, panel: pygame.Rect, result: PerceptionFrame | None, status: str) -> None:
        self._panel(panel)
        self._text("YOLOPv2 OUTPUT", (panel.x + 12, panel.y + 10), self.font, (223, 238, 242))
        if status == "LIVE":
            state_label, status_color = "LIVE", (78, 216, 165)
        elif status == "DISABLED" or status.startswith("MODEL UNAVAILABLE"):
            state_label, status_color = ("OFF", (145, 162, 171)) if status == "DISABLED" else ("ERROR", (243, 146, 120))
        elif status.startswith("INFERENCE ERROR"):
            state_label, status_color = "ERROR", (243, 146, 120)
        elif status.startswith("STALE"):
            state_label, status_color = "STALE", (243, 181, 103)
        else:
            state_label, status_color = "LOAD", (243, 181, 103)
        state_rect = pygame.Rect(panel.right - 61, panel.y + 10, 49, 21)
        pygame.draw.rect(self.screen, (18, 43, 47), state_rect, border_radius=8)
        self._text(state_label, state_rect.center, self.tiny, status_color, centered=True)
        inference_hz = 1.0 / self.config.perception.inference_interval_seconds
        self._text(f"ROOF CAMERA  ·  {self.config.perception.input_size} PX  ·  {inference_hz:.0f} HZ", (panel.x + 12, panel.y + 32), self.tiny, (123, 153, 166))

        preview = pygame.Rect(panel.x + 11, panel.y + 53, panel.w - 22, int((panel.w - 22) * 9 / 16))
        pygame.draw.rect(self.screen, (2, 6, 9), preview, border_radius=5)
        if result is not None:
            previous_clip = self.screen.get_clip()
            self.screen.set_clip(preview)
            self._draw_masks_and_boxes(result, preview, draw_labels=False)
            self.screen.set_clip(previous_clip)
        else:
            self._text("WAITING FOR MODEL", preview.center, self.tiny, (127, 154, 164), centered=True)
        pygame.draw.rect(self.screen, (43, 64, 75), preview, width=1, border_radius=5)

        metrics_y = preview.bottom + 9
        metric_width = (panel.w - 34) // 3
        metrics = (("OBJECTS", str(len(result.detections)) if result else "--", (91, 218, 183)),
                   ("ROAD", self._mask_percent(result.driving_area, 0.5) if result else "--", (82, 200, 167)),
                   ("LANES", self._mask_percent(result.lane_lines, 0.45) if result else "--", (246, 207, 93)))
        for index, (label, value, color) in enumerate(metrics):
            card = pygame.Rect(panel.x + 11 + index * (metric_width + 6), metrics_y, metric_width, 43)
            self._panel(card)
            self._text(label, (card.x + 5, card.y + 6), self.tiny, (123, 152, 164))
            self._text(value, (card.x + 5, card.y + 22), self.small, color)

        output_y = metrics_y + 52
        self._text("MODEL OUTPUTS", (panel.x + 12, output_y), self.tiny, (157, 184, 193))
        self._text("OBJECT DETECTION", (panel.x + 12, output_y + 17), self.tiny, (91, 198, 205))
        self._text("DRIVING-AREA MASK", (panel.x + 12, output_y + 33), self.tiny, (82, 200, 167))
        self._text("LANE-LINE MASK", (panel.x + 12, output_y + 49), self.tiny, (246, 207, 93))
        detections_y = output_y + 64
        pygame.draw.line(self.screen, (40, 63, 75), (panel.x + 12, detections_y), (panel.right - 12, detections_y), 1)
        detections_y += 9
        count = len(result.detections) if result else 0
        self._text(f"OBJECT DETECTIONS  ·  {count}", (panel.x + 12, detections_y), self.tiny, (204, 222, 227))
        detections_y += 21
        available_rows = max(0, (panel.bottom - 34 - detections_y) // 18)
        if result is None:
            self._text("No inference frame yet", (panel.x + 12, detections_y), self.tiny, (114, 141, 153))
        elif not result.detections:
            self._text("No objects detected", (panel.x + 12, detections_y), self.tiny, (114, 141, 153))
        else:
            shown = min(count, max(0, available_rows - 1))
            for index, detection in enumerate(result.detections[:shown]):
                y = detections_y + index * 18
                color = self._detection_color(detection.class_id)
                pygame.draw.circle(self.screen, color, (panel.x + 16, y + 7), 3)
                self._text(detection.class_name[:18], (panel.x + 25, y), self.tiny, (192, 211, 217))
                confidence = f"{detection.confidence:.2f}"
                confidence_surface = self.tiny.render(confidence, True, color)
                self.screen.blit(confidence_surface, confidence_surface.get_rect(right=panel.right - 12, top=y))
            remaining = count - shown
            if remaining > 0 and available_rows > 0:
                self._text(f"+ {remaining} more · boxes shown above", (panel.x + 12, detections_y + shown * 18), self.tiny, (133, 161, 171))
        if result is not None:
            timing_y = panel.bottom - 21
            self._text(f"INFERENCE  {result.inference_ms:.0f} MS", (panel.x + 12, timing_y), self.tiny, (115, 149, 161))

    @staticmethod
    def _mask_percent(mask: np.ndarray, threshold: float) -> str:
        percent = float(np.count_nonzero(mask >= threshold)) * 100.0 / mask.size
        return f"{percent:.0f}%"

    @staticmethod
    def _detection_color(class_id: int) -> tuple[int, int, int]:
        palette = ((80, 220, 255), (255, 180, 68), (255, 91, 86), (100, 236, 149), (189, 139, 255), (255, 220, 92), (85, 171, 255), (255, 119, 190))
        return palette[class_id % len(palette)]

    def _draw_footer(self, width: int, height: int, snapshot: DrivingSnapshot, controller_name: str, status: str, paused: bool) -> None:
        panel = pygame.Rect(16, height - 65, width - 32, 52)
        self._panel(panel)
        vehicle = snapshot.vehicle
        self._text(f"{vehicle.speed_kmh:05.1f}", (panel.x + 12, panel.y + 6), self.speed_font, (242, 249, 250))
        self._text("km/h", (panel.x + 119, panel.y + 23), self.tiny, (135, 169, 181))
        gear_rect = pygame.Rect(panel.x + 158, panel.y + 11, 34, 30)
        pygame.draw.rect(self.screen, (17, 48, 53), gear_rect, border_radius=8)
        self._text(vehicle.gear, gear_rect.center, self.font, (98, 221, 190) if not vehicle.reverse else (246, 177, 101), centered=True)

        controls_x = panel.x + 211
        bar_width = min(138, max(80, int(width * 0.108)))
        self._bar(controls_x, panel.y + 16, "THR", vehicle.throttle, (75, 202, 166), bar_width)
        self._bar(controls_x, panel.y + 36, "BRK", vehicle.brake, (231, 114, 105), bar_width)
        steering_x = controls_x + bar_width + 22
        track = pygame.Rect(steering_x + 43, panel.y + 24, 74, 6)
        pygame.draw.rect(self.screen, (39, 59, 70), track, border_radius=3)
        pygame.draw.line(self.screen, (86, 113, 125), (track.centerx, track.y - 3), (track.centerx, track.bottom + 3), 1)
        marker = track.centerx + int(max(-1.0, min(1.0, vehicle.steering)) * (track.w // 2))
        pygame.draw.circle(self.screen, (93, 211, 210), (marker, track.centery), 5)
        self._text("STEER", (steering_x, panel.y + 18), self.tiny, (143, 171, 182))

        right_x = panel.right - 320
        label = status[:32] if status else ""
        self._text(label or ("PAUSED" if paused else f"INPUT  {controller_name[:16].upper()}"), (right_x, panel.y + 10), self.tiny, (245, 187, 104) if status or paused else (114, 200, 178))
        self._text("WASD DRIVE  ·  C / Q CAMERA  ·  ESC MENU", (right_x, panel.y + 30), self.tiny, (129, 157, 168))

    def _draw_masks_and_boxes(self, result: PerceptionFrame, viewport: pygame.Rect, draw_labels: bool = True) -> None:
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
            color = self._detection_color(detection.class_id)
            pygame.draw.rect(self.screen, color, box, width=2 if draw_labels else 1)
            if not draw_labels:
                continue
            label = f"{detection.class_name} {detection.confidence:.2f}"
            text = self.small.render(label, True, (245, 249, 250))
            label_y = max(draw_rect.y, box.y - text.get_height() - 3)
            label_x = min(box.x, draw_rect.right - text.get_width() - 8)
            label_rect = pygame.Rect(label_x, label_y, text.get_width() + 8, text.get_height() + 4)
            pygame.draw.rect(self.screen, (7, 14, 17), label_rect)
            self.screen.blit(text, (label_rect.x + 4, label_rect.y + 2))

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
