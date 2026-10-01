import threading
from types import SimpleNamespace

from carla_drive.config import AppConfig
from carla_drive.sensors.monitor import MonitorSensors


def test_reset_discards_obstacle_events_from_old_location():
    sensor = MonitorSensors.__new__(MonitorSensors)
    sensor.config = AppConfig()
    sensor.session = SimpleNamespace(world=SimpleNamespace(get_snapshot=lambda: SimpleNamespace(frame=20)))
    sensor._rear_lock = threading.Lock()
    sensor._rear_distances = {}
    sensor._rear_minimum_frame = 0

    sensor._on_obstacle("left", SimpleNamespace(frame=19, distance=0.5))
    assert sensor.rear_distance().left_m == 0.5
    sensor.clear_rear()
    sensor._on_obstacle("left", SimpleNamespace(frame=20, distance=0.5))
    assert sensor.rear_distance().closest_m is None
    sensor._on_obstacle("right", SimpleNamespace(frame=21, distance=2.0))
    assert sensor.rear_distance().right_m == 2.0
