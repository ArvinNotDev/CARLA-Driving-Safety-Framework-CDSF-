"""Rear mirror, LiDAR, and parking-distance dashboard sensors."""

from __future__ import annotations

import math
import threading
import time

import carla
import numpy as np

from carla_drive.camera.rig import LatestImage
from carla_drive.config import AppConfig
from carla_drive.domain import RearDistanceState

class MonitorSensors:
    """Owns dashboard-only sensors; none of these callbacks affect vehicle control."""

    def __init__(self, session, config: AppConfig):
        if session.ego_vehicle is None:
            raise RuntimeError("Spawn the ego vehicle before creating dashboard sensors.")
        self.session = session
        self.config = config
        self.mirror = LatestImage()
        self._lidar_lock = threading.Lock()
        self._lidar_points: np.ndarray | None = None
        self._lidar_received_at = 0.0
        self._rear_lock = threading.Lock()
        self._rear_distances: dict[str, tuple[float, float]] = {}
        self._rear_minimum_frame = 0
        self._create_mirror()
        if config.lidar.enabled:
            self._create_lidar()
        if config.rear_parking.enabled:
            self._create_rear_obstacles()

    def _spawn_sensor(self, blueprint_id: str, transform: carla.Transform) -> carla.Sensor:
        blueprint = self.session.world.get_blueprint_library().find(blueprint_id)
        sensor = self.session.world.spawn_actor(
            blueprint,
            transform,
            attach_to=self.session.ego_vehicle,
            attachment_type=carla.AttachmentType.Rigid,
        )
        self.session.track_sensor(sensor)
        return sensor

    def _create_mirror(self) -> None:
        blueprint = self.session.world.get_blueprint_library().find("sensor.camera.rgb")
        blueprint.set_attribute("image_size_x", str(self.config.camera.mirror_width))
        blueprint.set_attribute("image_size_y", str(self.config.camera.mirror_height))
        blueprint.set_attribute("fov", str(self.config.camera.fov))
        sensor = self.session.world.spawn_actor(
            blueprint,
            carla.Transform(
                carla.Location(x=self.config.camera.mirror_x, y=self.config.camera.mirror_y, z=self.config.camera.mirror_z),
                carla.Rotation(yaw=self.config.camera.mirror_yaw),
            ),
            attach_to=self.session.ego_vehicle,
            attachment_type=carla.AttachmentType.Rigid,
        )
        self.session.track_sensor(sensor)
        sensor.listen(self.mirror.callback)

    def _create_lidar(self) -> None:
        config = self.config.lidar
        blueprint = self.session.world.get_blueprint_library().find("sensor.lidar.ray_cast")
        attributes = {
            "channels": config.channels,
            "range": config.range_m,
            "points_per_second": config.points_per_second,
            "rotation_frequency": config.rotation_frequency_hz,
            "upper_fov": config.upper_fov,
            "lower_fov": config.lower_fov,
        }
        for name, value in attributes.items():
            blueprint.set_attribute(name, str(value))
        sensor = self.session.world.spawn_actor(
            blueprint,
            carla.Transform(carla.Location(x=0.0, z=2.0)),
            attach_to=self.session.ego_vehicle,
            attachment_type=carla.AttachmentType.Rigid,
        )
        self.session.track_sensor(sensor)
        sensor.listen(self._on_lidar)

    def _on_lidar(self, measurement: carla.LidarMeasurement) -> None:
        points = np.frombuffer(measurement.raw_data, dtype=np.float32).reshape(-1, 4)
        if len(points) > self.config.lidar.display_points:
            stride = math.ceil(len(points) / self.config.lidar.display_points)
            points = points[::stride]
        display_points = points[:, :3].copy()
        with self._lidar_lock:
            self._lidar_points = display_points
            self._lidar_received_at = time.monotonic()

    def _create_rear_obstacles(self) -> None:
        config = self.config.rear_parking
        blueprint = self.session.world.get_blueprint_library().find("sensor.other.obstacle")
        blueprint.set_attribute("distance", str(config.distance_m))
        blueprint.set_attribute("hit_radius", str(config.hit_radius_m))
        blueprint.set_attribute("only_dynamics", "false")
        blueprint.set_attribute("debug_linetrace", "false")
        for name, lateral in (
            ("left", config.left_offset_m),
            ("center", 0.0),
            ("right", config.right_offset_m),
        ):
            sensor = self.session.world.spawn_actor(
                blueprint,
                carla.Transform(carla.Location(x=config.sensor_x, y=lateral, z=config.sensor_height_m), carla.Rotation(yaw=180.0)),
                attach_to=self.session.ego_vehicle,
                attachment_type=carla.AttachmentType.Rigid,
            )
            self.session.track_sensor(sensor)
            sensor.listen(lambda event, zone=name: self._on_obstacle(zone, event))

    def _on_obstacle(self, zone: str, event: carla.ObstacleDetectionEvent) -> None:
        distance = max(0.0, float(event.distance))
        if distance > self.config.rear_parking.distance_m:
            return
        with self._rear_lock:
            if event.frame < self._rear_minimum_frame:
                return
            self._rear_distances[zone] = (distance, time.monotonic())

    def clear_rear(self) -> None:
        """Forget obstacles at the previous vehicle position after a reset."""
        frame = self.session.world.get_snapshot().frame + 1
        with self._rear_lock:
            self._rear_minimum_frame = frame
            self._rear_distances.clear()

    def latest_mirror(self) -> tuple[np.ndarray | None, float]:
        return self.mirror.read()

    def latest_lidar(self) -> tuple[np.ndarray | None, float]:
        with self._lidar_lock:
            return self._lidar_points, self._lidar_received_at

    def rear_distance(self, now: float | None = None) -> RearDistanceState:
        current = time.monotonic() if now is None else now
        with self._rear_lock:
            distances = dict(self._rear_distances)
        def fresh(zone: str) -> float | None:
            value = distances.get(zone)
            if value is None or current - value[1] > self.config.rear_parking.stale_after_seconds:
                return None
            return value[0]
        timestamps = [value[1] for value in distances.values()]
        sampled_at = max(timestamps) if timestamps else 0.0
        return RearDistanceState(fresh("left"), fresh("center"), fresh("right"), sampled_at)
