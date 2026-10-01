from pathlib import Path

import pytest

from carla_drive.config import load_config


def test_default_configuration_loads_and_validates():
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config" / "defaults.example.yaml")
    assert config.carla.fixed_delta_seconds == 0.05
    assert config.session.traffic_vehicles == 0
    assert config.controller.trigger_full_value == 1.0


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
