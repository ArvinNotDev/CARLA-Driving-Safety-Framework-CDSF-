from collections import deque
import threading
from types import SimpleNamespace

import numpy as np

from carla_drive.sensors.monitor import MonitorSensors


class Transform:
    def __init__(self, x=0.0):
        self.matrix = np.eye(4, dtype=np.float32)
        self.matrix[0, 3] = x

    def get_matrix(self):
        return self.matrix

    def get_inverse_matrix(self):
        inverse = self.matrix.copy()
        inverse[0, 3] *= -1
        return inverse


def _sensor_state(persistence=0.35, display_points=100):
    sensors = MonitorSensors.__new__(MonitorSensors)
    sensors.config = SimpleNamespace(lidar=SimpleNamespace(display_points=display_points, persistence_seconds=persistence))
    sensors._lidar_lock = threading.Lock()
    sensors._lidar_points = None
    sensors._lidar_received_at = 0.0
    sensors._lidar_scans = deque(maxlen=64)
    return sensors


def _measurement(timestamp, x=0.0, point=(5.0, 0.0, 1.0, 0.5)):
    raw_data = np.asarray([point], dtype=np.float32).tobytes() if point is not None else b""
    return SimpleNamespace(raw_data=raw_data, timestamp=timestamp, transform=Transform(x))


def test_lidar_scans_accumulate_in_current_sensor_frame_and_keep_ages():
    sensors = _sensor_state()
    sensors._on_lidar(_measurement(0.0))
    sensors._on_lidar(_measurement(0.1, x=1.0))

    points, _ = sensors.latest_lidar()
    assert points.shape == (2, 4)
    assert np.allclose(points[:, 0], [4.0, 5.0])
    assert np.allclose(points[:, 3], [0.1, 0.0])


def test_empty_lidar_frames_preserve_cloud_until_persistence_expires():
    sensors = _sensor_state(persistence=0.3)
    sensors._on_lidar(_measurement(0.0))
    sensors._on_lidar(_measurement(0.1, point=None))
    points, first_received_at = sensors.latest_lidar()

    sensors._on_lidar(_measurement(0.2, point=None))
    latest_points, latest_received_at = sensors.latest_lidar()
    assert latest_points.shape == (1, 4)
    assert latest_points[0, 3] == 0.2
    assert latest_received_at >= first_received_at

    sensors._on_lidar(_measurement(0.31, point=None))
    expired_points, _ = sensors.latest_lidar()
    assert expired_points.shape == (0, 4)
