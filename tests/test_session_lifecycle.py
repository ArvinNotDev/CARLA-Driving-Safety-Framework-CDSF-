"""Checks that switching maps preserves the destination world's settings."""

from types import SimpleNamespace

from carla_drive.carla.session import CarlaSession
from carla_drive.config import AppConfig


class World:
    def __init__(self, name, weather, synchronous, fixed_delta):
        self.name = name
        self.weather = weather
        self.settings = SimpleNamespace(synchronous_mode=synchronous, fixed_delta_seconds=fixed_delta)
        self.restored = None

    def get_map(self):
        return SimpleNamespace(name=self.name)

    def get_settings(self):
        return SimpleNamespace(**vars(self.settings))

    def apply_settings(self, settings):
        self.settings = settings
        self.restored = SimpleNamespace(**vars(settings))

    def get_weather(self):
        return self.weather

    def set_weather(self, value):
        self.weather = value


def test_map_switch_restores_destination_world_settings_and_weather():
    previous = World("Town01", "old weather", True, 0.025)
    selected = World("Town02", "selected weather", False, None)
    session = CarlaSession.__new__(CarlaSession)
    session.config = AppConfig()
    session.world = previous
    session.original_settings = previous.get_settings()
    session.original_weather = previous.get_weather()
    session.original_tm_sync = False
    session.traffic_manager = SimpleNamespace(set_synchronous_mode=lambda mode: None, set_random_device_seed=lambda seed: None)
    session.client = SimpleNamespace(load_world=lambda name: selected)
    session.actors = []
    session.sensors = []
    session.walker_controllers = []
    session._traffic_manager_touched = False
    session._closed = False

    session.prepare("Town02", "ClearNoon", 7)
    assert selected.settings.synchronous_mode is True
    session.close()

    assert selected.settings.synchronous_mode is False
    assert selected.settings.fixed_delta_seconds is None
    assert selected.weather == "selected weather"
    assert previous.settings.synchronous_mode is True
