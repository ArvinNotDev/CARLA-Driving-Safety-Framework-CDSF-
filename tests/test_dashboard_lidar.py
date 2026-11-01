import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame

from carla_drive.config import AppConfig
from carla_drive.domain import DrivingSnapshot
from carla_drive.ui.dashboard import Dashboard


def test_lidar_render_is_vectorized_and_keeps_stale_cloud_visible():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    dashboard = Dashboard(screen, AppConfig())
    points = np.array([[5.0, 0.0, 1.0]], dtype=np.float32)
    timestamp = time.monotonic() - 2.0

    dashboard._draw_lidar_sidebar(
        pygame.Rect(10, 10, 320, 560),
        (points, timestamp),
        (None, 0.0),
        DrivingSnapshot(),
        paused=False,
    )

    assert dashboard._lidar_surface is not None
    assert dashboard._lidar_key == (timestamp, dashboard._lidar_surface.get_size())
    red, green, blue, _ = dashboard._lidar_surface.get_at((88, 76))
    assert red > green > blue
    pygame.quit()


def test_driving_camera_stays_central_when_model_outputs_are_live():
    from carla_drive.domain import CameraMode
    from carla_drive.perception import Detection, PerceptionFrame

    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    dashboard = Dashboard(screen, AppConfig())
    now = time.monotonic()
    image = np.empty((720, 1280, 3), dtype=np.uint8)
    image[:] = (220, 10, 10)
    result = PerceptionFrame(
        detections=(Detection((10, 10, 100, 80), 0.95, 2, "car"),),
        driving_area=np.ones((360, 640), dtype=np.float32),
        lane_lines=np.zeros((360, 640), dtype=np.float32),
        source_width=640,
        source_height=360,
        inference_ms=320.0,
        received_at=now,
    )
    snapshot = DrivingSnapshot(camera_mode=CameraMode.COCKPIT)

    dashboard.render(
        snapshot,
        (image, now),
        (None, 0.0),
        (np.empty((0, 4), dtype=np.float32), now),
        "Keyboard",
        False,
        "",
        perception_state=(result, "LIVE"),
    )

    assert screen.get_at((640, 360))[:3] == (220, 10, 10)
    pygame.quit()
