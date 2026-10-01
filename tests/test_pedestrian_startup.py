from types import SimpleNamespace

import carla

from carla_drive.carla.session import CarlaSession
from carla_drive.config import AppConfig


def test_pedestrian_controller_starts_after_initial_world_tick():
    state = {"ticked": False, "started": False}

    class Controller:
        id = 2

        def start(self):
            assert state["ticked"]
            state["started"] = True

        def go_to_location(self, location):
            pass

        def set_max_speed(self, speed):
            pass

    controller = Controller()
    walker = SimpleNamespace(id=1)
    blueprint = SimpleNamespace(has_attribute=lambda name: False)
    library = SimpleNamespace(filter=lambda pattern: [blueprint], find=lambda name: blueprint)

    class World:
        def get_blueprint_library(self):
            return library

        def get_random_location_from_navigation(self):
            return carla.Location()

        def try_spawn_actor(self, blueprint, transform, attach_to=None):
            return controller if attach_to is walker else walker

        def tick(self):
            state["ticked"] = True
            return 1

    session = CarlaSession.__new__(CarlaSession)
    session.config = AppConfig()
    session.world = World()
    session.actors = []
    session.walker_controllers = []

    assert session.spawn_pedestrians(1, 7) == 1
    assert state == {"ticked": True, "started": True}
    assert session.actors == [walker, controller]
