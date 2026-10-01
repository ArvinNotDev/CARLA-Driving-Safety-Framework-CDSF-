"""CARLA connection, world setup, actor spawning, and deterministic cleanup."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any

import carla

from carla_drive.config import AppConfig

LOG = logging.getLogger(__name__)

WEATHER_LABELS = {
    "ClearNoon": "Clear",
    "CloudyNoon": "Cloudy",
    "WetNoon": "Wet",
    "WetCloudyNoon": "Wet Cloudy",
    "SoftRainNoon": "Soft Rain",
    "MidRainyNoon": "Rain",
    "HardRainNoon": "Heavy Rain",
    "ClearSunset": "Clear Sunset",
    "WetSunset": "Wet Sunset",
    "DustStorm": "Dust Storm",
}


@dataclass(frozen=True)
class VehicleOption:
    blueprint_id: str
    label: str


def discover_weather_presets() -> list[tuple[str, str]]:
    available = []
    for name, label in WEATHER_LABELS.items():
        if hasattr(carla.WeatherParameters, name):
            available.append((name, label))
    return available


def _attribute(blueprint: Any, name: str) -> str | None:
    if blueprint.has_attribute(name):
        return str(blueprint.get_attribute(name))
    return None


def vehicle_options(world: carla.World) -> list[VehicleOption]:
    options: list[VehicleOption] = []
    for blueprint in world.get_blueprint_library().filter("vehicle.*"):
        if not blueprint.has_attribute("number_of_wheels"):
            continue
        try:
            if int(blueprint.get_attribute("number_of_wheels")) != 4:
                continue
        except (TypeError, ValueError):
            continue
        make = _attribute(blueprint, "make")
        model = _attribute(blueprint, "model")
        label = " ".join(part for part in (make, model) if part) or blueprint.id.rsplit(".", 1)[-1].replace("_", " ")
        options.append(VehicleOption(blueprint.id, label))
    return sorted(options, key=lambda option: (option.label.casefold(), option.blueprint_id))


def friendly_map_name(map_name: str) -> str:
    return map_name.rsplit("/", 1)[-1]


class CarlaSession:
    """Owns CARLA actors created by this application and restores runtime settings."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.client = carla.Client(config.carla.host, config.carla.port)
        self.client.set_timeout(config.carla.timeout_seconds)
        try:
            self.world = self.client.get_world()
        except RuntimeError as exc:
            raise RuntimeError(
                f"Could not connect to CARLA at {config.carla.host}:{config.carla.port}. "
                "Start the CARLA 0.9.16 server and check the configured host and port."
            ) from exc
        self.initial_world_name = self.world.get_map().name
        self.original_settings = self.world.get_settings()
        self.original_weather = self.world.get_weather()
        self.original_tm_sync = self._get_traffic_manager_sync()
        if self.original_tm_sync is None:
            # CARLA 0.9.16 exposes a setter but no getter; paired world/TM sync is its documented setup.
            self.original_tm_sync = bool(self.original_settings.synchronous_mode)
        self.traffic_manager = self.client.get_trafficmanager(config.carla.traffic_manager_port)
        self.actors: list[carla.Actor] = []
        self.sensors: list[carla.Sensor] = []
        self.walker_controllers: list[carla.Actor] = []
        self.ego_vehicle: carla.Vehicle | None = None
        self.initial_ego_transform: carla.Transform | None = None
        self._traffic_manager_touched = False
        self._closed = False
        LOG.info("Connected to CARLA %s; current map: %s", self.client.get_client_version(), friendly_map_name(self.initial_world_name))

    def available_maps(self) -> list[str]:
        try:
            return sorted(self.client.get_available_maps(), key=friendly_map_name)
        except RuntimeError as exc:
            LOG.warning("CARLA map discovery failed: %s", exc)
            return [self.world.get_map().name]

    def available_vehicles(self) -> list[VehicleOption]:
        return vehicle_options(self.world)

    def prepare(self, map_name: str | None, weather_name: str, random_seed: int) -> None:
        if not hasattr(carla.WeatherParameters, weather_name):
            raise ValueError(f"CARLA weather preset '{weather_name}' is unavailable in this installation.")
        if map_name and friendly_map_name(map_name) != friendly_map_name(self.world.get_map().name):
            LOG.info("Loading map %s", friendly_map_name(map_name))
            self.world = self.client.load_world(map_name)
            # Loading a map creates a new world with its own settings and weather.
            self.original_settings = self.world.get_settings()
            self.original_weather = self.world.get_weather()

        settings = self.world.get_settings()
        settings.synchronous_mode = self.config.carla.synchronous_mode
        settings.fixed_delta_seconds = self.config.carla.fixed_delta_seconds if settings.synchronous_mode else None
        self.world.apply_settings(settings)
        self.traffic_manager.set_synchronous_mode(settings.synchronous_mode)
        self._traffic_manager_touched = True
        self.traffic_manager.set_random_device_seed(random_seed)

        self.world.set_weather(getattr(carla.WeatherParameters, weather_name))

    def spawn_ego(self, blueprint_id: str | None, random_seed: int) -> carla.Vehicle:
        options = self.available_vehicles()
        if not options:
            raise RuntimeError("CARLA exposes no four-wheel vehicle blueprints.")
        selected = blueprint_id or options[0].blueprint_id
        library = self.world.get_blueprint_library()
        try:
            blueprint = library.find(selected)
        except RuntimeError as exc:
            raise ValueError(f"Vehicle blueprint '{selected}' is not available on this CARLA server.") from exc
        if blueprint.has_attribute("role_name"):
            blueprint.set_attribute("role_name", "hero")

        spawn_points = list(self.world.get_map().get_spawn_points())
        if not spawn_points:
            raise RuntimeError("The selected map has no vehicle spawn points.")
        random.Random(random_seed).shuffle(spawn_points)
        for transform in spawn_points:
            vehicle = self.world.try_spawn_actor(blueprint, transform)
            if vehicle is not None:
                self.ego_vehicle = vehicle
                self.initial_ego_transform = transform
                self.track_actor(vehicle)
                LOG.info("Spawned ego vehicle %s", selected)
                return vehicle
        raise RuntimeError("Could not spawn the selected vehicle. Try another vehicle or map spawn point.")

    def spawn_traffic(self, requested: int, random_seed: int) -> int:
        if requested <= 0:
            return 0
        library = self.world.get_blueprint_library()
        blueprints = [
            blueprint
            for blueprint in library.filter("vehicle.*")
            if blueprint.has_attribute("number_of_wheels") and int(blueprint.get_attribute("number_of_wheels")) == 4
        ]
        spawn_points = list(self.world.get_map().get_spawn_points())
        random.Random(random_seed + 1).shuffle(spawn_points)
        spawned = 0
        rng = random.Random(random_seed + 2)
        for transform in spawn_points:
            if spawned >= requested:
                break
            if self.ego_vehicle and transform.location.distance(self.ego_vehicle.get_location()) < 8.0:
                continue
            blueprint = rng.choice(blueprints)
            if blueprint.has_attribute("role_name"):
                blueprint.set_attribute("role_name", "autopilot")
            actor = self.world.try_spawn_actor(blueprint, transform)
            if actor is None:
                continue
            self.track_actor(actor)
            actor.set_autopilot(True, self.config.carla.traffic_manager_port)
            spawned += 1
        LOG.info("Spawned %d of %d requested traffic vehicles", spawned, requested)
        return spawned

    def spawn_pedestrians(self, requested: int, random_seed: int) -> int:
        if requested <= 0:
            return 0
        library = self.world.get_blueprint_library()
        walkers = list(library.filter("walker.pedestrian.*"))
        if not walkers:
            LOG.warning("This CARLA map exposes no pedestrian blueprints.")
            return 0
        rng = random.Random(random_seed + 3)
        spawned = 0
        for _ in range(requested * 8):
            if spawned >= requested:
                break
            location = self.world.get_random_location_from_navigation()
            if location is None:
                continue
            blueprint = rng.choice(walkers)
            if blueprint.has_attribute("is_invincible"):
                blueprint.set_attribute("is_invincible", "false")
            walker = self.world.try_spawn_actor(blueprint, carla.Transform(location))
            if walker is None:
                continue
            self.track_actor(walker)
            controller_blueprint = library.find("controller.ai.walker")
            controller = self.world.try_spawn_actor(controller_blueprint, carla.Transform(), attach_to=walker)
            if controller is None:
                LOG.warning("Could not create AI controller for pedestrian %s", walker.id)
                continue
            self.track_actor(controller, walker_controller=True)
            controller.start()
            destination = self.world.get_random_location_from_navigation()
            if destination is not None:
                controller.go_to_location(destination)
            controller.set_max_speed(rng.uniform(1.0, 1.8))
            spawned += 1
        LOG.info("Spawned %d of %d requested pedestrians", spawned, requested)
        return spawned

    def track_actor(self, actor: carla.Actor, walker_controller: bool = False, sensor: bool = False) -> None:
        if actor not in self.actors:
            self.actors.append(actor)
        if walker_controller and actor not in self.walker_controllers:
            self.walker_controllers.append(actor)
        if sensor:
            self.track_sensor(actor)

    def track_sensor(self, sensor: carla.Sensor) -> None:
        if sensor not in self.sensors:
            self.sensors.append(sensor)
        if sensor not in self.actors:
            self.actors.append(sensor)

    def tick(self) -> int:
        """Advance one synchronous simulation step; called only by the driving loop."""
        return self.world.tick()

    def set_paused(self, paused: bool) -> None:
        """Freeze an asynchronous server by entering sync mode without ticking."""
        settings = self.world.get_settings()
        settings.synchronous_mode = True if paused else self.config.carla.synchronous_mode
        settings.fixed_delta_seconds = self.config.carla.fixed_delta_seconds if settings.synchronous_mode else None
        self.world.apply_settings(settings)
        self.traffic_manager.set_synchronous_mode(settings.synchronous_mode)
        self._traffic_manager_touched = True

    def apply_control(self, steering: float, throttle: float, brake: float, reverse: bool, handbrake: bool) -> None:
        if self.ego_vehicle is None:
            return
        control = carla.VehicleControl(
            steer=max(-1.0, min(1.0, steering)),
            throttle=max(0.0, min(1.0, throttle)),
            brake=max(0.0, min(1.0, brake)),
            reverse=reverse,
            hand_brake=handbrake,
        )
        self.ego_vehicle.apply_control(control)

    def vehicle_speed_mps(self) -> float:
        if self.ego_vehicle is None:
            return 0.0
        velocity = self.ego_vehicle.get_velocity()
        return (velocity.x**2 + velocity.y**2 + velocity.z**2) ** 0.5

    def reset_ego(self) -> None:
        if self.ego_vehicle is None or self.initial_ego_transform is None:
            return
        self.ego_vehicle.set_transform(self.initial_ego_transform)
        self.ego_vehicle.set_target_velocity(carla.Vector3D())
        self.ego_vehicle.apply_control(carla.VehicleControl(brake=1.0, hand_brake=True))

    def snapshot(self, steering: float, throttle: float, brake: float, reverse: bool):
        from carla_drive.domain import VehicleSnapshot

        return VehicleSnapshot(
            speed_kmh=self.vehicle_speed_mps() * 3.6,
            gear="R" if reverse else "D",
            reverse=reverse,
            steering=steering,
            throttle=throttle,
            brake=brake,
        )

    def _get_traffic_manager_sync(self) -> bool | None:
        try:
            manager = self.client.get_trafficmanager(self.config.carla.traffic_manager_port)
            getter = getattr(manager, "get_synchronous_mode", None)
            return bool(getter()) if getter else None
        except RuntimeError:
            return None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for sensor in reversed(self.sensors):
            try:
                sensor.stop()
            except RuntimeError:
                pass
        for controller in reversed(self.walker_controllers):
            try:
                controller.stop()
            except RuntimeError as exc:
                LOG.debug("Walker controller %s was already stopped: %s", controller.id, exc)
        if self.actors:
            try:
                commands = [carla.command.DestroyActor(actor.id) for actor in reversed(self.actors)]
                responses = self.client.apply_batch_sync(commands, False)
                for actor, response in zip(reversed(self.actors), responses):
                    if response.error:
                        LOG.warning("Could not destroy CARLA actor %s in batch: %s", actor.id, response.error)
                        try:
                            if actor.is_alive:
                                actor.destroy()
                        except RuntimeError as exc:
                            LOG.warning("Individual destruction also failed for actor %s: %s", actor.id, exc)
            except RuntimeError as exc:
                LOG.warning("Batch actor cleanup failed; trying individual destruction: %s", exc)
                for actor in reversed(self.actors):
                    try:
                        if actor.is_alive:
                            actor.destroy()
                    except RuntimeError as error:
                        LOG.warning("Could not destroy actor %s: %s", actor.id, error)
        if self._traffic_manager_touched and self.original_tm_sync is not None:
            try:
                self.traffic_manager.set_synchronous_mode(self.original_tm_sync)
            except RuntimeError as exc:
                LOG.warning("Could not restore Traffic Manager mode: %s", exc)
        elif self._traffic_manager_touched:
            try:
                self.traffic_manager.set_synchronous_mode(False)
                LOG.info("Traffic Manager has no sync-state getter; restored its documented default (asynchronous).")
            except RuntimeError as exc:
                LOG.warning("Could not reset Traffic Manager mode: %s", exc)
        try:
            self.world.apply_settings(self.original_settings)
        except RuntimeError as exc:
            LOG.warning("Could not restore original CARLA world settings: %s", exc)
        try:
            self.world.set_weather(self.original_weather)
        except RuntimeError as exc:
            LOG.warning("Could not restore original CARLA weather: %s", exc)
        LOG.info("CARLA session cleaned up")

    def __enter__(self) -> CarlaSession:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()
