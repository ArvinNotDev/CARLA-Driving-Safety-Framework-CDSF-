"""Application entry point and single-owner CARLA driving loop."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pygame

from carla_drive.camera.rig import CameraRig
from carla_drive.carla.session import CarlaSession, discover_weather_presets
from carla_drive.config import AppConfig, load_config
from carla_drive.domain import CameraMode, DrivingSnapshot
from carla_drive.input.controller import ControllerReader
from carla_drive.sensors.monitor import MonitorSensors
from carla_drive.ui.audio import ParkingBeep
from carla_drive.ui.dashboard import Dashboard
from carla_drive.ui.launcher import Launcher

LOG = logging.getLogger("carla_drive")
DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config" / "defaults.example.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual driving simulator for CARLA 0.9.16")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="YAML runtime configuration")
    parser.add_argument("--controller-debug", action="store_true", help="Show live raw gamepad axes and buttons")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        config = load_config(args.config)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    if args.controller_debug:
        return run_controller_diagnostic(config)
    return run_application(config)


def run_application(config: AppConfig) -> int:
    pygame.init()
    pygame.display.set_caption("CARLA Drive")
    screen = pygame.display.set_mode((config.window.width, config.window.height))
    session: CarlaSession | None = None
    controller: ControllerReader | None = None
    audio: ParkingBeep | None = None
    try:
        session = CarlaSession(config)
        maps = session.available_maps()
        vehicles = session.available_vehicles()
        weather = discover_weather_presets()
        if not weather:
            raise RuntimeError("This CARLA Python API exposes no supported weather presets.")
        if not vehicles:
            raise RuntimeError("No four-wheel vehicle blueprints are available in the current CARLA world.")
        selected = Launcher(screen, maps, weather, vehicles, config.session).run()
        if selected is None:
            return 0

        screen.fill((8, 15, 25))
        loading_font = pygame.font.Font(None, 34)
        loading_text = loading_font.render(f"Loading {selected.map_name.rsplit('/', 1)[-1]}…", True, (219, 236, 240))
        screen.blit(loading_text, loading_text.get_rect(center=screen.get_rect().center))
        pygame.display.flip()
        session.prepare(selected.map_name, selected.weather_preset, selected.random_seed)
        session.spawn_ego(selected.vehicle_blueprint, selected.random_seed)
        session.spawn_traffic(selected.traffic_vehicles, selected.random_seed)
        session.spawn_pedestrians(selected.pedestrians, selected.random_seed)

        controller = ControllerReader(config.controller)
        camera = CameraRig(session, config.camera)
        sensors = MonitorSensors(session, config)
        dashboard = Dashboard(screen, config)
        audio = ParkingBeep(config.rear_parking)
        pygame.display.set_caption("CARLA Drive | Manual Session")
        LOG.info(
            "Session started: map=%s, weather=%s, vehicle=%s, traffic=%d, pedestrians=%d",
            selected.map_name,
            selected.weather_preset,
            selected.vehicle_blueprint,
            selected.traffic_vehicles,
            selected.pedestrians,
        )
        run_driving_loop(session, controller, camera, sensors, dashboard, audio, screen, config)
        return 0
    except (RuntimeError, ValueError) as exc:
        LOG.error("CARLA Drive could not start: %s", exc)
        print(f"CARLA Drive stopped: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        LOG.info("Interrupted; cleaning up")
        return 130
    finally:
        if audio:
            audio.close()
        if controller:
            controller.close()
        if session:
            session.close()
        pygame.quit()


def run_driving_loop(session, controller, camera, sensors, dashboard, audio, screen, config) -> None:
    clock = pygame.time.Clock()
    reverse = False
    paused = False
    running = True
    status = ""
    status_until = 0.0
    control = None
    next_tick_at = time.monotonic()
    step_seconds = config.carla.fixed_delta_seconds

    while running:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_1:
                    camera.set_mode(CameraMode.COCKPIT)
                elif event.key == pygame.K_2:
                    camera.set_mode(CameraMode.CHASE)
                elif event.key == pygame.K_3:
                    camera.set_mode(CameraMode.OVERHEAD)

        if not running:
            break
        control = controller.sample(events)
        if "camera_next" in control.pressed:
            camera.next_mode(1)
        if "camera_previous" in control.pressed:
            camera.next_mode(-1)
        if "pause" in control.pressed:
            paused = not paused
            session.set_paused(paused)
            next_tick_at = time.monotonic() + step_seconds
        if "reset" in control.pressed:
            session.reset_ego()
            reverse = False
            status = "Vehicle reset to its starting position"
            status_until = time.monotonic() + 2.5
        if "reverse" in control.pressed:
            speed = session.vehicle_speed_mps()
            if not config.controller.require_stop_for_reverse or speed <= config.controller.reverse_stop_speed_mps:
                reverse = not reverse
                status = "Reverse" if reverse else "Drive"
            else:
                status = "Stop before changing direction"
            status_until = time.monotonic() + 2.0

        now = time.monotonic()
        if now > status_until:
            status = ""
        if paused:
            session.apply_control(0.0, 0.0, 1.0, reverse, True)
            applied_steering, applied_throttle, applied_brake = 0.0, 0.0, 1.0
        else:
            session.apply_control(control.steering, control.throttle, control.brake, reverse, control.handbrake)
            applied_steering, applied_throttle, applied_brake = control.steering, control.throttle, control.brake
            if config.carla.synchronous_mode and now >= next_tick_at:
                session.tick()
                next_tick_at = time.monotonic() + step_seconds

        rear = sensors.rear_distance(now)
        vehicle = session.snapshot(applied_steering, applied_throttle, applied_brake, reverse)
        snapshot = DrivingSnapshot(vehicle=vehicle, rear_distance=rear, camera_mode=camera.mode)
        audio.update(reverse and not paused, rear.closest_m)
        dashboard.render(
            snapshot,
            camera.latest_frame(),
            sensors.latest_mirror(),
            sensors.latest_lidar(),
            controller.name,
            paused,
            status,
        )
        pygame.display.flip()
        clock.tick(config.window.render_fps)


def run_controller_diagnostic(config: AppConfig) -> int:
    pygame.init()
    screen = pygame.display.set_mode((680, 420))
    pygame.display.set_caption("CARLA Drive | Controller Diagnostic")
    controller = ControllerReader(config.controller)
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 25)
    small = pygame.font.Font(None, 20)
    running = True
    try:
        while running:
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False
            controller.sample(events)
            screen.fill((9, 18, 29))
            screen.blit(font.render(f"Controller: {controller.name}", True, (232, 241, 245)), (24, 22))
            screen.blit(small.render("Move each stick and trigger; edit axis indices/rest values in your YAML.", True, (146, 173, 186)), (24, 56))
            axes = controller.raw_axes()
            buttons = controller.raw_buttons()
            if not axes:
                screen.blit(font.render("No gamepad found. Connect it and restart this screen.", True, (250, 188, 126)), (24, 106))
            for index, value in enumerate(axes):
                y = 103 + index * 36
                screen.blit(small.render(f"Axis {index:02d}   {value:+.3f}", True, (196, 217, 224)), (28, y))
                pygame.draw.rect(screen, (36, 59, 72), (180, y + 3, 340, 14), border_radius=6)
                center = 350
                pygame.draw.line(screen, (93, 121, 135), (center, y + 1), (center, y + 19), 1)
                marker = center + int(value * 165)
                pygame.draw.circle(screen, (76, 207, 191), (marker, y + 10), 6)
            button_y = 103 + len(axes) * 36
            screen.blit(small.render("Buttons: " + ("  ".join(f"{i}:{value}" for i, value in enumerate(buttons)) or "none"), True, (196, 217, 224)), (28, min(button_y, 354)))
            screen.blit(small.render("Esc closes diagnostics", True, (111, 140, 154)), (24, 386))
            pygame.display.flip()
            clock.tick(30)
    finally:
        controller.close()
        pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
