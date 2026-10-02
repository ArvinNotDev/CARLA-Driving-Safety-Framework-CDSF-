import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame

from carla_drive.config import AppConfig
from carla_drive.ui.dashboard import Dashboard


def test_lidar_render_is_vectorized_and_keeps_stale_cloud_visible():
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    dashboard = Dashboard(screen, AppConfig())
    points = np.array([[5.0, 0.0, 1.0]], dtype=np.float32)
    timestamp = time.monotonic() - 2.0

    dashboard._draw_lidar(1280, (points, timestamp), paused=False)

    assert dashboard._lidar_surface is not None
    assert dashboard._lidar_key == timestamp
    red, green, blue, _ = dashboard._lidar_surface.get_at((148, 95))
    assert red > green > blue
    pygame.quit()
