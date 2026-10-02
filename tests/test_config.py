from pathlib import Path
from importlib import import_module

import pytest

from carla_drive.config import load_config


def test_default_configuration_loads_and_validates():
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config" / "defaults.example.yaml")
    assert config.carla.fixed_delta_seconds == 0.05
    assert config.session.traffic_vehicles == 0
    assert config.controller.trigger_full_value == 1.0
    assert config.controller.horn_button == 9
    assert config.controller.dpad_hat == 0


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
