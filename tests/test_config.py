from pathlib import Path
from importlib import import_module

import pytest

from carla_drive.config import load_config


def test_default_configuration_loads_and_validates():
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config" / "defaults.example.yaml")
    assert config.carla.fixed_delta_seconds == 0.0333333
    assert config.window.render_fps == 60
    assert config.lidar.points_per_second == 60000
    assert config.lidar.rotation_frequency_hz == 10.0
    assert config.lidar.display_points == 2500
    assert config.lidar.persistence_seconds == 0.35
    assert config.session.time_of_day == "Noon"
    assert config.session.traffic_vehicles == 0
    assert config.controller.trigger_full_value == 1.0
    assert config.controller.horn_button == 9
    assert config.controller.dpad_hat == 0
    assert config.controller.steering_sensitivity == 1.0
    assert config.controller.dpad_mode == "auto"


def test_configuration_rejects_unknown_settings(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("window:\n  widht: 1280\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown setting"):
        load_config(path)


def test_configuration_rejects_invalid_parking_thresholds(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("rear_parking:\n  critical_distance_m: 2.0\n  warning_distance_m: 1.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="thresholds"):
        load_config(path)


def test_configuration_rejects_long_kinematic_confirmation_window(tmp_path):
    path = tmp_path / "slow-impact.yaml"
    path.write_text("safety:\n  confirmation_window_seconds: 0.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="confirmation window"):
        load_config(path)


def test_configuration_rejects_invalid_collision_confidence_threshold(tmp_path):
    path = tmp_path / "confidence.yaml"
    path.write_text("safety:\n  minimum_impact_score: 1.1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="minimum_impact_score"):
        load_config(path)


def test_configuration_rejects_unknown_time_of_day(tmp_path):
    path = tmp_path / "time.yaml"
    path.write_text("session:\n  time_of_day: midnight\n", encoding="utf-8")
    with pytest.raises(ValueError, match="time_of_day"):
        load_config(path)


def test_entry_point_uses_builtin_defaults_without_repository_config(monkeypatch):
    app_main = import_module("carla_drive.app.main")
    observed = []
    monkeypatch.setattr(app_main, "run_application", lambda config: observed.append(config) or 0)
    assert app_main.main([]) == 0
    assert observed[0].carla.port == 2000


def test_launcher_rejects_window_that_cannot_fit_the_hud(tmp_path):
    path = tmp_path / "small.yaml"
    path.write_text("window:\n  width: 800\n  height: 600\n", encoding="utf-8")
    with pytest.raises(ValueError, match="1024x700"):
        load_config(path)
