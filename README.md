# CARLA Drive — Phase 1

A human-oriented, game-like manual driving environment for CARLA.

## Run the application

Use Python 3.12 with the CARLA 0.9.16 Python API available to that interpreter. Start the CARLA server first, then install the app's lightweight Python dependencies and run it:

```powershell
python -m pip install -e .
python main.py
```

You can also use the installed `carla-drive` command. The root `main.py` wrapper runs directly from the checkout.

Install the test extra when developing: `python -m pip install -e ".[test]"`, then run `python -m pytest`.

The CARLA Python API is supplied by the matching CARLA installation and is intentionally not downloaded as a generic PyPI dependency. If the app cannot connect, check that the server is running and that `carla.host`, `carla.port`, and `carla.timeout_seconds` match it.

The setup screen scans installed Town maps and four-wheel vehicles before opening. It starts with zero NPCs and shows map, weather, vehicle, and time-of-day choices in dropdowns. Time of day adjusts the sun angle while preserving the selected weather preset. Click a dropdown to choose an item; for keyboard use, move with Up/Down, adjust with Left/Right, and press Space to open a dropdown. Press Enter or click **Start Driving** to begin. The GitHub button opens [@ArvinNotDev](https://github.com/ArvinNotDev/).

For an API/controller check without spawning vehicles:

```powershell
python tools/carla_smoke.py --config config/defaults.example.yaml
python main.py --config config/defaults.example.yaml --controller-debug
```

The setup screen lists installed `Town...` road maps and opens on the server's current Town map when available. Internal CARLA assets such as annotation maps are excluded because they are not driving environments. To tune the runtime, copy `config/defaults.example.yaml` to a local YAML file and launch with `python main.py --config path/to/your.yaml`.
The current fixed layout supports windows of at least 1024×700 pixels; invalid smaller sizes are rejected during configuration loading.

### Controls

| Action | Xbox mapping | Keyboard fallback |
| --- | --- | --- |
| Steer | Left stick X | A / D |
| Throttle | Right trigger | W / Up |
| Brake | Left trigger | S / Down |
| Toggle reverse | Configured button (default B) | R |
| Change camera | Configured next/previous buttons | C / Q or 1 / 2 / 3 |
| Handbrake | Configured button | Space |
| Reset vehicle | Configured button | Backspace |
| Pause | Configured button | P |
| Left / right indicator | D-pad left / right | Z / X |
| Headlight mode (low → high → off) | D-pad up | H |
| Horn (hold) | R3 / right stick click | Hold F |
| Pause menu | — | Esc |
| Exit | — | Window close |

Controller axis indices and trigger resting/full values vary by driver. Run `--controller-debug`, move each control, and tune the indices and `trigger_rest_value` / `trigger_full_value` in the YAML. The defaults are a starting mapping, not a claim that every Xbox driver reports identical axes.

The pause menu shows a speaker emoji for the current mute state and has controls to mute or unmute the generated engine idle/rev loop, horn, indicator ticks, rear parking beeps, collision alert, and gear-shift cues. It also returns to session setup or resumes the current drive. The synchronous simulation step defaults to 60 Hz and the render cap defaults to 90 FPS; lower these in YAML if the server or graphics hardware cannot keep up. Collision warnings are shown and sounded only at or above the configured `safety.minimum_impact_score` (default 0.80).

## What this project is

This project is the foundation for a long-lived CARLA driving application. Phase 1 is intentionally focused on **making CARLA feel like a proper driving game / simulator UI**, while keeping the architecture ready for later perception, assistance, and autonomous-driving features.

The Phase 1 target is:

> **Launch -> choose map/weather/traffic/vehicle -> spawn -> drive naturally with an Xbox controller -> switch cameras -> see a polished dashboard -> monitor rear parking distance, rear view mirror, LiDAR and vehicle telemetry.**

There is **no autonomous steering, collision avoidance, lane keeping, route following, or ML driving logic in Phase 1**. Sensors may observe and display the world, but they must not secretly change the driver's control input.

## CARLA target

This blueprint targets **CARLA 0.9.16** and its Python API. Keep the CARLA version isolated/configurable so a later upgrade does not require rewriting the whole application.

## Code map

- `src/carla_drive/app/main.py` coordinates setup, driving, and shutdown.
- `src/carla_drive/carla/session.py` owns the CARLA connection, world settings, vehicles, pedestrians, and cleanup.
- `src/carla_drive/input/controller.py` normalizes controller values and supplies keyboard fallback.
- `src/carla_drive/camera/rig.py` switches the main camera transform; `sensors/monitor.py` captures the mirror, LiDAR, and rear obstacle traces.
- `src/carla_drive/safety/kinematic_collision.py` detects strong impact-like events from short-term longitudinal motion and control history without spawning a collision sensor.
- `src/carla_drive/ui/` contains the setup screen, dashboard, pause menu, and driving audio cues.
- `src/carla_drive/config.py` validates the YAML runtime configuration; `domain.py` defines compact UI state.

CARLA's client/server model and synchronous mode are important to the runtime architecture. The application should have one clear owner of `world.tick()` and should restore the original world / Traffic Manager settings during shutdown.

## User experience

### Startup / session setup

The launcher should provide:

- CARLA connection status.
- Map selector populated from maps actually available to the connected CARLA server when practical.
- Weather preset selector plus a compact advanced/custom weather section.
- Traffic counts: vehicles and pedestrians, both allowed to be zero.
- Ego vehicle selector populated from CARLA vehicle blueprints, with human-readable names.
- Spawn selection with at least random/default spawn; explicit spawn point selection can be added without changing the runtime architecture.
- Start button and clear validation/error messages.

### Driving screen

The main window is the driving view. It should feel like a simulator rather than a debugging tool.

Required camera modes:

1. First-person / cockpit camera.
2. Third-person chase camera.
3. Top-down camera.

Camera switching should be handled by a `CameraRig` / `CameraManager`, not scattered across the main loop.

Required dashboard elements:

- Main camera image.
- **Center rear-view mirror at the top-center.**
- **Rear parking sensor directly underneath the mirror**, drawn as a two-sided bar that grows outward from the center.
- Audible parking beeps whose frequency increases as the measured distance decreases; continuous tone / critical state may be used for the closest configurable band.
- **LiDAR miniature panel pinned to the upper-right** with a 360-degree overview. It should remain readable without covering the driving view.
- Current speed in km/h.
- Gear / driving direction state.
- Steering input state.
- Throttle and brake state.
- Current camera mode.
- Optional small session indicators such as map / weather / traffic count.

### Xbox controller

The controller should feel analog and natural.

Do not implement driving as `left/right/throttle/brake = 0 or 1` keyboard-style actions.

Expected behavior:

- Left stick X -> progressive steering.
- RT -> progressive throttle.
- LT -> progressive brake.
- Configurable dead zones.
- Configurable response curves / sensitivity.
- Small steering inputs produce small steering; full stick produces full steering.
- Throttle and brake remain analog across their full travel.
- Short transient input jitter should not create visible steering noise.
- Camera switching, reset, handbrake/reverse and pause should be mapped to buttons without stealing analog controls.
- A small controller diagnostic / mapping layer should make the application resilient to different Xbox/XInput axis layouts.

Do not hide controller values behind arbitrary magic numbers. Keep tuning values in configuration.

## Architecture philosophy

The architecture should be **professional but deliberately boring**.

Prefer:

- one application entry point;
- one main simulation/render loop;
- explicit managers with small responsibilities;
- plain dataclasses / simple state objects;
- configuration outside the code;
- deterministic cleanup;
- clear names and short functions;
- small pure helpers that are easy for agents to test.

Avoid:

- dependency-injection frameworks;
- event-bus frameworks;
- ECS architecture;
- plugin systems for Phase 1;
- unnecessary multiprocessing;
- dozens of one-function classes;
- hidden global state;
- huge `main.py` files;
- mixing CARLA spawning, controller math, sensor processing and UI drawing in one module.

## Proposed ownership boundaries

`app/`

Owns application lifecycle and coordinates the other modules. It should know **what** happens, not implement every detail.

`carla/`

Connection/session/world/actor/traffic responsibilities. The CARLA session should own the runtime actors it created.

`input/`

Xbox/controller sampling and normalization. It should expose a clean normalized control state to the rest of the application.

`camera/`

Camera presets, camera switching and camera frame acquisition.

`sensors/`

LiDAR, rear parking distance, rear mirror camera, and sensor snapshots. Sensors are data providers, not autonomous controllers. Kinematic impact analysis belongs to the separate `safety` service.

`ui/`

Pygame window, dashboard layout and reusable visual widgets. UI should consume state and render it; it should not directly manipulate CARLA actors.

`domain/`

Small shared state models / enums: session state, drive state, camera mode, sensor snapshot, input state.

`utils/`

Logging, timing and cleanup helpers only where they make the code simpler.

## Runtime flow

```text
Launcher
  -> build SessionConfig
  -> connect to CARLA
  -> load selected world
  -> apply world settings
  -> configure Traffic Manager
  -> spawn ego vehicle
  -> spawn traffic
  -> create camera rig
  -> create sensors
  -> enter DrivingSession

DrivingSession loop
  -> read Xbox input
  -> normalize input
  -> update vehicle control
  -> tick/wait according to the selected runtime mode
  -> consume latest sensor data
  -> update lightweight UI state
  -> render dashboard

Shutdown
  -> stop sensor listeners
  -> stop walker controllers
  -> destroy spawned actors
  -> restore Traffic Manager settings
  -> restore original world settings
  -> close pygame/audio resources
  -> exit cleanly
```

## Sensor design

### Main camera

Use a dedicated primary RGB camera for the current view. Camera mode should change the transform rather than duplicating the entire rendering pipeline.

### Rear-view mirror

Use a separate rear-facing RGB camera attached to the ego vehicle. The mirror renderer should crop/scale it to a fixed UI region at the top-center.

### LiDAR

Use a dedicated 360-degree LiDAR sensor. The sensor module should convert the latest measurement into a lightweight renderable point representation. The UI owns only presentation, not sensor physics.

The LiDAR panel is a **visual monitor only in Phase 1**. It must not influence vehicle control.

### Rear parking sensor

Use a short-range rear-facing obstacle/distance setup. A practical Phase 1 implementation can use multiple narrow rear obstacle traces/sensors aimed at left/center/right zones and fuse the nearest distance into a simple rear-distance snapshot.

The renderer should map the closest relevant distance to a symmetric visual bar:

```text
          MIRROR
   +----------------------+
   |                      |
   +----------------------+
       <---  |  --->
       LEFT  |  RIGHT
             ^
           center
```

The visual fill should expand from the center toward both sides as the obstacle approaches. Keep the thresholds/configuration outside the widget itself.

The parking sensor may trigger a warning/beep, but **must not apply brake or steering in Phase 1**.

### Kinematic impact candidates

The passive detector estimates longitudinal acceleration and jerk from the ego vehicle's velocity history using CARLA simulation timestamps. It compares observed deceleration with a brake- and throttle-aware envelope and briefly confirms abnormal samples before reporting an impact candidate. It does not read collision sensors, obstacle sensors, LiDAR, cameras, or raycasts. Kinematic inference can identify strong impact-like motion but cannot perfectly distinguish every collision from every other abrupt maneuver; it is not CARLA ground truth. Thresholds are in the `safety` section of the YAML configuration. See [docs/kinematic_collision.md](docs/kinematic_collision.md) for the method and assumptions.

## State model

Keep state explicit and small. The driving loop should be able to work from a snapshot similar to:

- `VehicleState`: speed, gear/reverse, steering, throttle, brake.
- `CameraState`: current mode.
- `RearSensorState`: distance / left distance / right distance / beep phase.
- `LidarState`: latest points / age / availability.
- `SessionState`: map, weather, traffic counts, connection status.
- `InputState`: normalized analog values and buttons.

The UI should never have to query the CARLA world repeatedly just to draw a speedometer.

## Performance rules

The application should prioritize a stable, responsive driving experience.

- Avoid blocking the render loop on sensor callbacks.
- Keep only the latest frame where appropriate for visual sensors.
- Use bounded queues when a queue is actually needed.
- Never let an old camera frame grow without bound.
- Keep LiDAR rendering lightweight enough for the target GTX 1080 class hardware.
- Do not open extra debug windows in the normal driving experience.
- Debug views can exist behind a configuration flag.

## Testing philosophy

Tests should focus on logic that can run without a CARLA server:

- controller dead-zone and response-curve math;
- throttle/brake normalization;
- speed formatting;
- rear-distance-to-bar mapping;
- beep interval calculation;
- camera mode state transitions;
- session configuration validation.

Add a small CARLA smoke-test script for real runtime checks. Do not create fake visual tests merely to increase test count.

## Definition of done for Phase 1

Phase 1 is done when a user can:

1. Start the application while CARLA is running.
2. Choose a map, weather, vehicle, traffic counts and pedestrian count.
3. Start a session successfully or receive a clear error.
4. Drive the spawned vehicle continuously with an Xbox controller.
5. Use analog steering, throttle and brake naturally.
6. Switch between first-person, third-person and top-down views.
7. See a stable rear-view mirror at the top-center.
8. See the rear parking-distance indicator under the mirror.
9. Hear parking beeps that vary with distance.
10. See the LiDAR panel in the upper-right.
11. See speed, gear and primary control telemetry.
12. Exit cleanly without leaving synchronous mode, walker controllers or spawned actors behind.

## Future-ready, but explicitly deferred

The architecture should leave room for:

- collision avoidance;
- driver assistance;
- lane departure warnings;
- lane following;
- route planning;
- perception models;
- autonomous steering;
- adaptive cruise / speed control;
- parking assistance;
- recording and dataset generation;
- simulation scenarios.

None of these should leak into Phase 1 behavior unless they are purely passive displays.

## Reference material

CARLA 0.9.16 documentation:
- https://carla.readthedocs.io/en/0.9.16/
- https://carla.readthedocs.io/en/0.9.16/foundations/
- https://carla.readthedocs.io/en/0.9.16/core_sensors/
- https://carla.readthedocs.io/en/0.9.16/ref_sensors/

This blueprint intentionally stays compatible with the documented CARLA client/server + synchronous simulation model.
