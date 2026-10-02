import threading
from types import SimpleNamespace

import numpy as np

from carla_drive.sensors.monitor import MonitorSensors


def test_empty_lidar_measurement_keeps_the_last_nonempty_cloud_visible():
    sensors = MonitorSensors.__new__(MonitorSensors)
    sensors.config = SimpleNamespace(lidar=SimpleNamespace(display_points=10))
    sensors._lidar_lock = threading.Lock()
    sensors._lidar_points = None
    sensors._lidar_received_at = 0.0

    measurement = SimpleNamespace(raw_data=np.array([[5, 0, 1, 0.5]], dtype=np.float32).tobytes())
    sensors._on_lidar(measurement)
    points, received_at = sensors.latest_lidar()
    sensors._on_lidar(SimpleNamespace(raw_data=b""))

    latest_points, latest_received_at = sensors.latest_lidar()
    assert np.array_equal(latest_points, points)
    assert latest_received_at == received_at
