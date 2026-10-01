"""Runtime configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class CarlaConfig:
    host: str = "127.0.0.1"
    port: int = 2000
    traffic_manager_port: int = 8000
    timeout_seconds: float = 10.0
    synchronous_mode: bool = True
    fixed_delta_seconds: float = 0.05


@dataclass(frozen=True)
class WindowConfig:
    width: int = 1280
    height: int = 720
    render_fps: int = 60


@dataclass(frozen=True)
class SessionConfig:
    map_name: str | None = None
    weather_preset: str = "ClearNoon"
    vehicle_blueprint: str | None = None
    traffic_vehicles: int = 0
    pedestrians: int = 0
    random_seed: int = 7


@dataclass(frozen=True)
class CameraConfig:
    width: int = 1280
    height: int = 720
    mirror_width: int = 640
    mirror_height: int = 180
    fov: float = 100.0
    cockpit_x: float = 1.15
    cockpit_y: float = 0.0
    cockpit_z: float = 1.35
    cockpit_pitch: float = -3.0
    chase_x: float = -5.2
    chase_y: float = 0.0
    chase_z: float = 2.5
    chase_pitch: float = -12.0
    overhead_x: float = -3.0
    overhead_y: float = 0.0
    overhead_z: float = 12.0
    overhead_pitch: float = -68.0
    mirror_x: float = -1.1
    mirror_y: float = 0.0
    mirror_z: float = 1.65
    mirror_yaw: float = 180.0


@dataclass(frozen=True)
class LidarConfig:
    enabled: bool = True
    channels: int = 32
    range_m: float = 45.0
    display_range_m: float = 32.0
    points_per_second: int = 120_000
    rotation_frequency_hz: float = 20.0
    display_points: int = 3_000
    upper_fov: float = 10.0
    lower_fov: float = -30.0


@dataclass(frozen=True)
class RearParkingConfig:
    enabled: bool = True
    distance_m: float = 6.0
    hit_radius_m: float = 0.35
    warning_distance_m: float = 2.0
    critical_distance_m: float = 0.6
    stale_after_seconds: float = 0.6
    sensor_x: float = -1.4
    sensor_height_m: float = 0.65
    left_offset_m: float = -0.65
    right_offset_m: float = 0.65
    slowest_beep_ms: int = 900
    fastest_beep_ms: int = 120


@dataclass(frozen=True)
class ControllerConfig:
    joystick_index: int = 0
    steering_axis: int = 0
    steering_axis_inverted: bool = False
    throttle_axis: int = 5
    brake_axis: int = 4
    steering_deadzone: float = 0.06
    trigger_deadzone: float = 0.04
    steering_response: float = 1.35
    throttle_response: float = 1.0
    brake_response: float = 1.0
    steering_smoothing: float = 0.10
    trigger_rest_value: float = -1.0
    trigger_full_value: float = 1.0
    reverse_button: int = 1
    camera_next_button: int = 0
    camera_previous_button: int = 2
    handbrake_button: int = 4
    reset_button: int = 3
    pause_button: int = 7
    require_stop_for_reverse: bool = True
    reverse_stop_speed_mps: float = 0.8


@dataclass(frozen=True)
class AppConfig:
    carla: CarlaConfig = field(default_factory=CarlaConfig)
    window: WindowConfig = field(default_factory=WindowConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    lidar: LidarConfig = field(default_factory=LidarConfig)
    rear_parking: RearParkingConfig = field(default_factory=RearParkingConfig)
    controller: ControllerConfig = field(default_factory=ControllerConfig)


def _section(data: dict[str, Any], key: str, allowed: set[str]) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"Configuration section '{key}' must be a mapping.")
    unknown = set(value) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"Unknown setting(s) in '{key}': {names}")
    return value


def load_config(path: str | Path) -> AppConfig:
    """Load YAML settings, using dataclass defaults for omitted values."""
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ValueError(f"Cannot read configuration '{config_path}': {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in '{config_path}': {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("The configuration root must be a mapping.")

    sections = {
        "carla": (CarlaConfig, {item.name for item in fields(CarlaConfig)}),
        "window": (WindowConfig, {item.name for item in fields(WindowConfig)}),
        "session": (SessionConfig, {item.name for item in fields(SessionConfig)}),
        "camera": (CameraConfig, {item.name for item in fields(CameraConfig)}),
        "lidar": (LidarConfig, {item.name for item in fields(LidarConfig)}),
        "rear_parking": (RearParkingConfig, {item.name for item in fields(RearParkingConfig)}),
        "controller": (ControllerConfig, {item.name for item in fields(ControllerConfig)}),
    }
    values: dict[str, Any] = {}
    for key, (model, allowed) in sections.items():
        values[key] = model(**_section(raw, key, allowed))
    unknown_sections = set(raw) - set(sections)
    if unknown_sections:
        raise ValueError(f"Unknown configuration section(s): {', '.join(sorted(unknown_sections))}")
    config = AppConfig(**values)
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    """Reject invalid ranges before connecting to CARLA."""
    if not config.carla.host.strip():
        raise ValueError("CARLA host cannot be empty.")
    for name, value in (("CARLA port", config.carla.port), ("Traffic Manager port", config.carla.traffic_manager_port)):
        if not 1 <= value <= 65535:
            raise ValueError(f"{name} must be between 1 and 65535.")
    if config.carla.timeout_seconds <= 0:
        raise ValueError("CARLA timeout_seconds must be positive.")
    if config.carla.synchronous_mode and not 0 < config.carla.fixed_delta_seconds <= 0.1:
        raise ValueError("Synchronous fixed_delta_seconds must be greater than 0 and at most 0.1.")
    if config.window.width < 1024 or config.window.height < 700 or config.window.render_fps <= 0:
        raise ValueError("The dashboard requires at least a 1024x700 window and a positive render_fps.")
    if min(config.camera.width, config.camera.height, config.camera.mirror_width, config.camera.mirror_height) <= 0:
        raise ValueError("Camera resolutions must be positive.")
    if not 30.0 <= config.camera.fov <= 150.0:
        raise ValueError("Camera fov must be between 30 and 150 degrees.")
    if min(config.session.traffic_vehicles, config.session.pedestrians) < 0:
        raise ValueError("Traffic and pedestrian counts cannot be negative.")
    if max(config.session.traffic_vehicles, config.session.pedestrians) > 200:
        raise ValueError("Traffic and pedestrian counts cannot exceed 200 in the launcher.")
    controller = config.controller
    if not 0 <= controller.steering_deadzone < 1 or not 0 <= controller.trigger_deadzone < 1:
        raise ValueError("Controller deadzones must be in the range [0, 1).")
    if min(controller.steering_response, controller.throttle_response, controller.brake_response) <= 0:
        raise ValueError("Controller response curves must be positive.")
    if not 0 <= controller.steering_smoothing <= 1:
        raise ValueError("steering_smoothing must be in the range [0, 1].")
    if controller.trigger_full_value == controller.trigger_rest_value:
        raise ValueError("trigger_full_value and trigger_rest_value must differ.")
    if not -1 <= controller.trigger_rest_value <= 1 or not -1 <= controller.trigger_full_value <= 1:
        raise ValueError("Trigger rest/full values must be between -1 and 1.")
    if min(controller.steering_axis, controller.throttle_axis, controller.brake_axis) < 0:
        raise ValueError("Controller axis indices cannot be negative.")
    if min(controller.reverse_button, controller.camera_next_button, controller.camera_previous_button, controller.handbrake_button, controller.reset_button, controller.pause_button) < 0:
        raise ValueError("Controller button indices cannot be negative.")
    if controller.reverse_stop_speed_mps < 0:
        raise ValueError("reverse_stop_speed_mps cannot be negative.")
    parking = config.rear_parking
    if parking.distance_m <= 0 or parking.hit_radius_m <= 0:
        raise ValueError("Rear parking distance and hit radius must be positive.")
    if parking.stale_after_seconds <= 0:
        raise ValueError("Rear sensor stale_after_seconds must be positive.")
    if not 0 <= parking.critical_distance_m < parking.warning_distance_m <= parking.distance_m:
        raise ValueError("Rear parking thresholds must satisfy 0 <= critical < warning <= sensor range.")
    if parking.fastest_beep_ms <= 0 or parking.slowest_beep_ms < parking.fastest_beep_ms:
        raise ValueError("Parking beep intervals must be positive and slowest >= fastest.")
    if config.lidar.enabled and min(config.lidar.channels, config.lidar.points_per_second, config.lidar.display_points) <= 0:
        raise ValueError("Enabled LiDAR must use positive channels and point counts.")
    if config.lidar.enabled and config.lidar.range_m <= 0:
        raise ValueError("Enabled LiDAR range_m must be positive.")
    if config.lidar.enabled and not 0 < config.lidar.display_range_m <= config.lidar.range_m:
        raise ValueError("Enabled LiDAR display_range_m must be positive and no greater than range_m.")
