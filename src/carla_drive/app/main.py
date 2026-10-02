"""Application entry point and single-owner CARLA driving loop."""

from __future__ import annotations

import argparse
import logging
import queue
import sys
import threading
import time
from pathlib import Path

import pygame

from carla_drive.camera.rig import CameraRig
from carla_drive.carla.lights import EgoLightState
from carla_drive.carla.session import CarlaSession, discover_weather_presets
from carla_drive.config import AppConfig, load_config
from carla_drive.domain import CameraMode, DrivingSnapshot
from carla_drive.input.controller import ControllerReader
from carla_drive.sensors.monitor import MonitorSensors
from carla_drive.safety.kinematic_collision import KinematicCollisionDetector
from carla_drive.ui.audio import ParkingBeep
from carla_drive.ui.dashboard import Dashboard
from carla_drive.ui.launcher import Launcher

LOG = logging.getLogger("carla_drive")
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual driving simulator for CARLA 0.9.16")
    parser.add_argument("--config", type=Path, help="Optional YAML runtime configuration")
    parser.add_argument("--controller-debug", action="store_true", help="Show live raw gamepad axes and buttons")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        config = load_config(args.config) if args.config else AppConfig()
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
        session = _connect_with_retry(screen, config)
        if session is None:
            return 0
        _show_startup_status(
            screen,
            "CHECKING AVAILABLE CONTENT",
            "Discovering installed Town maps, weather, and vehicles.",
        )
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


def _show_startup_status(screen: pygame.Surface, title: str, detail: str) -> None:
    width, height = screen.get_size()
    screen.fill((7, 15, 25))
    pygame.draw.rect(screen, (77, 208, 190), (0, 0, width, 3))
    title_font = pygame.font.SysFont("Segoe UI", 27, bold=True)
    detail_font = pygame.font.SysFont("Segoe UI", 16)
    title_surface = title_font.render(title, True, (237, 245, 248))
    detail_surface = detail_font.render(detail, True, (136, 160, 173))
    screen.blit(title_surface, title_surface.get_rect(center=(width // 2, height // 2 - 15)))
    screen.blit(detail_surface, detail_surface.get_rect(center=(width // 2, height // 2 + 23)))
    pygame.display.flip()


def _connect_with_retry(screen: pygame.Surface, config: AppConfig) -> CarlaSession | None:
    result: queue.Queue[tuple[CarlaSession | None, Exception | None]] = queue.Queue()
    state_lock = threading.Lock()
    cancelled = False
    clock = pygame.time.Clock()
    retry_rect = pygame.Rect(0, 0, 240, 52)
    error: Exception | None = None
    connecting = False

    def start_attempt() -> None:
        nonlocal connecting
        connecting = True

        def connect() -> None:
            try:
                connected_session = CarlaSession(config)
            except Exception as exc:
                result.put((None, exc))
                return
            with state_lock:
                if cancelled:
                    connected_session.close()
                else:
                    result.put((connected_session, None))

        threading.Thread(target=connect, name="carla-connect", daemon=True).start()

    start_attempt()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                with state_lock:
                    cancelled = True
                try:
                    connected_session, _ = result.get_nowait()
                    if connected_session is not None:
                        connected_session.close()
                except queue.Empty:
                    pass
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                with state_lock:
                    cancelled = True
                try:
                    connected_session, _ = result.get_nowait()
                    if connected_session is not None:
                        connected_session.close()
                except queue.Empty:
                    pass
                return None
            if (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and not connecting
                and retry_rect.collidepoint(event.pos)
            ):
                start_attempt()

        try:
            connected_session, error = result.get_nowait()
        except queue.Empty:
            pass
        else:
            if connected_session is not None:
                return connected_session
            connecting = False
            LOG.warning("Could not connect to CARLA: %s", error)

        width, height = screen.get_size()
        screen.fill((7, 15, 25))
        pygame.draw.rect(screen, (77, 208, 190), (0, 0, width, 3))
        title_font = pygame.font.SysFont("Segoe UI", 28, bold=True)
        detail_font = pygame.font.SysFont("Segoe UI", 17)
        title = "CONNECTING TO CARLA" if connecting else "CARLA CONNECTION FAILED"
        detail = (
            f"{config.carla.host}:{config.carla.port}  /  CARLA 0.9.16"
            if connecting
            else str(error or "Check that the CARLA server is running, then try again.")
        )
        title_surface = title_font.render(title, True, (237, 245, 248))
        screen.blit(title_surface, title_surface.get_rect(center=(width // 2, height // 2 - 45)))
        while detail and detail_font.size(detail)[0] > width - 80:
            detail = detail[:-1]
        detail_surface = detail_font.render(detail, True, (164, 184, 194))
        screen.blit(detail_surface, detail_surface.get_rect(center=(width // 2, height // 2 + 2)))
        if not connecting:
            retry_rect.center = (width // 2, height // 2 + 78)
            pygame.draw.rect(screen, (29, 112, 105), retry_rect, border_radius=10)
            pygame.draw.rect(screen, (77, 208, 190), retry_rect, width=1, border_radius=10)
            retry_surface = detail_font.render("Retry connection", True, (237, 245, 248))
            screen.blit(retry_surface, retry_surface.get_rect(center=retry_rect.center))
            hint_surface = detail_font.render("Click Retry or press Esc to quit", True, (136, 160, 173))
            screen.blit(hint_surface, hint_surface.get_rect(center=(width // 2, height // 2 + 126)))
        pygame.display.flip()
        clock.tick(30)


def run_driving_loop(session, controller, camera, sensors, dashboard, audio, screen, config) -> None:
    clock = pygame.time.Clock()
    reverse = False
    lights = EgoLightState()
    collision_detector = KinematicCollisionDetector(config.safety)
    detector_vehicle_id = session.ego_vehicle.id if session.ego_vehicle else None
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
        if "controller_disconnected" in control.pressed:
            lights.clear_indicators()
            status = "Controller disconnected; indicators off"
            status_until = time.monotonic() + 2.0
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
            sensors.clear_rear()
            collision_detector.reset()
            reverse = False
            lights.clear_indicators()
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

        for side, action in (("left", "indicator_left"), ("right", "indicator_right")):
            if action in control.pressed:
                enabled = lights.toggle_indicator(side)
                status = f"{side.title()} indicator {'on' if enabled else 'off'}"
                status_until = time.monotonic() + 1.5
        if "headlight_cycle" in control.pressed:
            mode = lights.cycle_headlights()
            status = f"Headlights: {mode.value}"
            status_until = time.monotonic() + 1.5
        lights.set_reverse(reverse)

        now = time.monotonic()
        if now > status_until:
            status = ""
        if paused:
            lights.set_brake_input(1.0)
            session.apply_control(0.0, 0.0, 1.0, reverse, True, lights)
            applied_steering, applied_throttle, applied_brake = 0.0, 0.0, 1.0
        else:
            lights.set_brake_input(control.brake)
            session.apply_control(control.steering, control.throttle, control.brake, reverse, control.handbrake, lights)
            applied_steering, applied_throttle, applied_brake = control.steering, control.throttle, control.brake
            if config.carla.synchronous_mode and now >= next_tick_at:
                session.tick()
                next_tick_at = time.monotonic() + step_seconds

        rear = sensors.rear_distance(now)
        current_vehicle_id = session.ego_vehicle.id if session.ego_vehicle else None
        if current_vehicle_id != detector_vehicle_id:
            collision_detector.reset()
            detector_vehicle_id = current_vehicle_id
        vehicle = session.snapshot(applied_steering, applied_throttle, applied_brake, reverse)
        snapshot = DrivingSnapshot(vehicle=vehicle, rear_distance=rear, camera_mode=camera.mode)
        if vehicle.kinematic_state_available:
            collision_event = collision_detector.update(
                timestamp_s=vehicle.simulation_time_s,
                longitudinal_velocity_mps=vehicle.longitudinal_velocity_mps,
                brake_input=applied_brake,
                throttle_input=applied_throttle,
                reverse=reverse,
            )
        else:
            collision_detector.reset()
            collision_event = None
        if collision_event:
            speed_drop_kmh = max(
                0.0,
                (collision_event.pre_impact_speed_mps - collision_event.post_impact_speed_mps) * 3.6,
            )
            LOG.warning(
                "Kinematic impact candidate at t=%.3fs: speed %.1f -> %.1f km/h, "
                "peak deceleration %.1f m/s^2, peak jerk %.1f m/s^3, brake=%.2f, "
                "throttle=%.2f, impact_score=%.2f (%s)",
                collision_event.timestamp_s,
                collision_event.pre_impact_speed_mps * 3.6,
                collision_event.post_impact_speed_mps * 3.6,
                collision_event.peak_deceleration_mps2,
                collision_event.peak_jerk_mps3,
                collision_event.brake_input,
                collision_event.throttle_input,
                collision_event.impact_score,
                collision_event.reason,
            )
            status = f"IMPACT CANDIDATE | drop {speed_drop_kmh:.0f} km/h | score {collision_event.impact_score:.2f}"
            status_until = time.monotonic() + 3.0
        audio.set_horn(control.horn and not paused)
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
            hats = controller.raw_hats()
            if not axes:
                screen.blit(font.render("No gamepad found. Connect it and restart this screen.", True, (250, 188, 126)), (24, 106))
            for index, value in enumerate(axes):
                y = 95 + index * 30
                screen.blit(small.render(f"Axis {index:02d}   {value:+.3f}", True, (196, 217, 224)), (28, y))
                pygame.draw.rect(screen, (36, 59, 72), (180, y + 3, 340, 14), border_radius=6)
                center = 350
                pygame.draw.line(screen, (93, 121, 135), (center, y + 1), (center, y + 19), 1)
                marker = center + int(value * 165)
                pygame.draw.circle(screen, (76, 207, 191), (marker, y + 10), 6)
            button_y = 95 + len(axes) * 30
            screen.blit(small.render("Buttons: " + ("  ".join(f"{i}:{value}" for i, value in enumerate(buttons)) or "none"), True, (196, 217, 224)), (28, min(button_y, 330)))
            screen.blit(small.render("D-pad: " + ("  ".join(f"{i}:{value}" for i, value in enumerate(hats)) or "none"), True, (196, 217, 224)), (28, min(button_y + 25, 356)))
            screen.blit(small.render("Esc closes diagnostics", True, (111, 140, 154)), (24, 386))
            pygame.display.flip()
            clock.tick(30)
    finally:
        controller.close()
        pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
