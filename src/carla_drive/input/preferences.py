"""Persistent user preferences for gamepad tuning and button mappings."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import fields, replace
from pathlib import Path

from carla_drive.config import AppConfig, ControllerConfig, validate_config

LOG = logging.getLogger(__name__)


def controller_preferences_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "CARLA Drive" / "controller-settings.json"


def load_controller_preferences(
    defaults: ControllerConfig,
    path: str | Path | None = None,
) -> ControllerConfig:
    target = Path(path) if path is not None else controller_preferences_path()
    try:
        values = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(values, dict):
            raise ValueError("Controller preferences must be a JSON object.")
        allowed = {setting.name for setting in fields(ControllerConfig)}
        settings = replace(defaults, **{name: value for name, value in values.items() if name in allowed})
        validate_config(replace(AppConfig(), controller=settings))
        return settings
    except FileNotFoundError:
        return defaults
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        LOG.warning("Ignoring invalid controller preferences at %s: %s", target, exc)
        return defaults


def save_controller_preferences(settings: ControllerConfig, path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else controller_preferences_path()
    validate_config(replace(AppConfig(), controller=settings))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    values = {setting.name: getattr(settings, setting.name) for setting in fields(ControllerConfig)}
    temporary.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target
