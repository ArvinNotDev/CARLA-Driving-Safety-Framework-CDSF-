# Agent Build Prompt — CARLA Drive Phase 1

You are the implementation agent for a CARLA driving application named **CARLA Drive**.

Read this file and `README.md` before changing anything.

## Mission

Build a polished, maintainable, human-readable Phase 1 driving environment for **CARLA 0.9.16**.

The end product should feel like a small driving game / simulator, not like a research script or a debug window.

The Phase 1 user journey is:

```text
Launch
 -> choose CARLA map
 -> choose weather
 -> choose vehicle
 -> choose vehicle traffic count
 -> choose pedestrian count
 -> start
 -> drive with Xbox controller
 -> switch camera views
 -> use dashboard
 -> see rear mirror
 -> see rear parking sensor
 -> hear parking beeps
 -> see 360 LiDAR panel
 -> see speed / gear / controls
 -> exit cleanly
```

## Existing-project context

The user already has CARLA 0.9.x experience and several older scripts. Some older code contains useful patterns, but do **not** migrate an old monolithic application wholesale.

Useful concepts from the previous work include:

- a `CameraManager` abstraction;
- bounded/latest-frame handling for camera images;
- explicit CARLA connection / world management;
- a small route helper;
- an input manager concept;
- explicit synchronous-mode configuration;
- Traffic Manager setup;
- batched actor destruction during cleanup;
- restoring original world settings on shutdown;
- separating sensor code from the driving loop.

Use those ideas as design input. Do not carry over unrelated autonomous-driving, ML, parking-sequence or safety-controller behavior.

## Non-negotiable scope boundary

Phase 1 is **manual driving only**.

Do NOT implement:

- autonomous steering;
- lane following;
- obstacle avoidance that modifies controls;
- automatic emergency braking;
- ML inference;
- route-following control;
- automatic parking;
- hidden safety intervention;
- a second control loop that can fight the human driver.

The LiDAR and rear parking sensor are passive monitoring features for Phase 1.

A kinematic impact candidate can be displayed/logged, but it must not secretly change the driver's input.

## Technical direction

Prefer Python + CARLA Python API + Pygame for the application window/input/audio.
Use OpenCV/Numpy only where they directly simplify image/sensor conversion or visualization.
Do not add a heavy GUI framework unless Pygame proves technically insufficient for a specific, demonstrated requirement.

Target environment assumptions should be configurable rather than hard-coded where reasonable.

The user's known runtime is roughly:

- CARLA 0.9.16
- Python 3.12.x
- pygame available
- Windows host
- NVIDIA GTX 1080 class GPU

Do not assume every machine has the exact same CARLA install path.

## Architecture to implement

Keep the following modules small and obvious.

### Application

`app/`

- owns startup/shutdown;
- owns the top-level loop;
- coordinates state and managers;
- should not contain 800 lines of rendering or sensor code.

### CARLA session

`carla/`

Create a clear session object that owns:

- client connection;
- selected world/map;
- original world settings;
- synchronous/fixed-step configuration;
- Traffic Manager;
- ego vehicle;
- traffic actors created by the app;
- cleanup lifecycle.

Use one obvious location for CARLA actor ownership.

### Xbox input

`input/`

Create a controller abstraction that emits normalized data such as:

```text
steering: -1..1
throttle: 0..1
brake: 0..1
buttons: named digital states
```

Implement configurable:

- deadzone;
- steering sensitivity;
- response curve;
- optional smoothing;
- trigger normalization.

The exact axis indices can vary by device. Do not scatter raw pygame axis indices through the code. Put them in one mapping/config layer.

Provide a small controller diagnostic path so an unknown mapping can be inspected easily during development.

Default Xbox behavior should be intuitive:

- left stick X = steering;
- RT = throttle;
- LT = brake;
- buttons = camera switching / reverse / handbrake / pause / reset according to one clearly documented mapping.

Make the button mapping configurable.

### Camera rig

`camera/`

Implement one camera manager / rig with three primary modes:

1. first-person/cockpit;
2. third-person/chase;
3. top-down.

Prefer moving/changing the transform of the active camera rather than creating and destroying cameras every time the user presses the camera button.

Use stable camera presets in one file/module.

A separate rear-view camera belongs to the sensor/camera subsystem and is rendered by the dashboard as a mirror.

### Sensors

`sensors/`

Create clear sensor components for:

- main RGB camera;
- rear-view RGB camera;
- 360 LiDAR;
- rear parking distance;

Each sensor should provide a small, understandable data object or latest snapshot.

Do not make UI widgets reach into raw CARLA sensor actors.

Kinematic impact analysis belongs in a separate `safety/` service that consumes vehicle telemetry and control state; do not add a collision sensor for it.

#### Rear parking distance

Use a short-range rear-facing obstacle/distance solution. It may use multiple rear-facing obstacle traces/sensors for left/center/right coverage.

The result should be exposed as a small normalized state, for example:

```text
closest_distance_m
left_distance_m
center_distance_m
right_distance_m
has_obstacle
```

The Phase 1 renderer uses this to drive a two-sided bar whose visual fill starts at the center and expands outward.

The sensor must NOT apply brake or steering.

#### LiDAR

Use a 360-degree LiDAR with a practical configuration for a GTX 1080-class machine.

Do not blindly choose an extreme point count. The mini-map is a UI element, not a research visualization benchmark.

Convert the latest measurement into a lightweight renderable representation.

Keep the LiDAR processing independent from the UI.

## Driving control model

The human must feel the car responds naturally.

Never do this:

```text
axis > 0 -> throttle 1
axis < 0 -> brake 1
```

Instead:

- preserve analog values;
- apply deadzone;
- remap the remaining range to full scale;
- apply a configurable response curve;
- optionally smooth steering slightly;
- clamp only at the final normalized boundary.

Steering should be responsive around center while still reaching full left/right at the stick limits.

Throttle and brake should have usable low-end control. A small trigger movement must result in a small amount of throttle/brake.

Keep control mixing deterministic and easy to tune.

## World / launcher flow

At startup:

1. connect to CARLA;
2. enumerate/select map;
3. load the selected world if necessary;
4. apply weather;
5. configure synchronous settings;
6. configure Traffic Manager;
7. select and spawn the ego vehicle;
8. spawn the requested traffic/pedestrians;
9. initialize cameras and sensors;
10. start the Pygame driving screen.

Traffic must be created by the application and tracked so it can be destroyed reliably on exit.

Pedestrian controller actors must be stopped before destruction.

Map and vehicle selectors should prefer real CARLA data over hard-coded lists wherever feasible.

## Runtime timing

CARLA 0.9.16 documentation recommends synchronous mode for applications where the client must coordinate sensor data and simulation steps.

Design the loop so there is one clear owner of `world.tick()`.

Do not create multiple ticking threads.

GPU camera sensors can lag a few frames. Do not assume the newest callback arrives before the simulation advances.

Use latest-frame storage or a bounded queue deliberately.

Do not let sensor callbacks perform expensive Pygame rendering.

## UI requirements

Use a single Pygame window.

The main camera view is the visual focus.

### Layout

Recommended hierarchy:

```text
+-----------------------------------------------------------------------+
|                     REAR VIEW MIRROR                                 |
|                  +---------------------+                              |
|                  |     rear camera     |                              |
|                  +---------------------+                              |
|                 <==== PARK SENSOR ==== >                             |
|                                                                       |
|                                      +-----------------------------+  |
|                                      |       360 LiDAR             |  |
|                                      |                             |  |
|                 MAIN CAMERA          |         point view          |  |
|                                      +-----------------------------+  |
|                                                                       |
|   status / controls                               speed / gear        |
+-----------------------------------------------------------------------+
```

The exact visual design is yours, but retain these spatial rules:

- mirror = top-center;
- parking sensor = immediately below mirror;
- LiDAR = upper-right, pinned;
- primary driving image = dominant area;
- telemetry = lower area / corners;
- overlays must not cover critical road visibility unnecessarily.

### Visual quality

Aim for:

- crisp text;
- restrained panels;
- subtle borders;
- consistent typography;
- no debug-style rainbow overlays;
- no huge permanent labels;
- no unnecessary blur;
- no blocking popups during normal driving.

The app should look like a simulator dashboard, not a computer-vision prototype.

## Rear parking bar behavior

The bar is symmetric and grows from the center:

```text
safe                     object near
<------ | ------>        <===|===>
        ^                        ^
      center                  larger fill
```

Use distance bands defined in configuration.

Beep timing should get shorter as the object gets closer.

Do not tie the beep directly to render FPS; base its phase/timing on time or simulation time.

The beep should be clearly audible but not ear-piercing.

If no obstacle is detected, the bar should return to its neutral/empty state and audio should be silent.

## Vehicle telemetry

At minimum display:

- speed in km/h;
- gear/direction;
- steering amount;
- throttle amount;
- brake amount;
- camera mode.

Use one source of truth for these values so the HUD does not show stale or differently calculated values.

## Cleanup is a feature

On exit, including Ctrl+C or window close:

1. stop sensor listeners;
2. stop walker AI controllers;
3. destroy walker controllers;
4. destroy walkers;
5. destroy traffic vehicles;
6. destroy ego vehicle and sensors;
7. restore Traffic Manager state;
8. restore original world settings;
9. close Pygame and audio resources.

Never leave CARLA stuck in synchronous mode because the app crashed during a manual test.

Use best-effort cleanup with logging around individual failures.

## Logging

Use Python logging.

Log important lifecycle events:

- connection;
- selected map/weather/vehicle;
- spawned actor counts;
- controller connection and mapping;
- sensor startup;
- warnings;
- cleanup.

Normal driving should not spam the console every frame.

## Configuration

Put tuning values in a configuration file rather than hiding them inside modules.

At minimum keep configurable:

- CARLA host/port;
- TM port;
- sync/fixed timestep;
- render width/height;
- camera transforms;
- LiDAR range/points/frequency configuration;
- rear sensor range;
- parking distance thresholds;
- beep timing thresholds;
- controller deadzone;
- steering curve/sensitivity;
- input mappings;
- default traffic counts;
- default weather;
- debug flags.

A clean default configuration should work without editing Python.

## Testing requirements

Before calling a feature done:

- run syntax/import checks;
- run unit tests for pure logic;
- run a real CARLA smoke test when the CARLA server is available;
- manually test the controller and UI behavior.

Do not invent useless visual unit tests.

Do not silently skip tests. Report exactly what was executed.

## Git discipline

The user specifically wants a history that is easy to inspect and hand to other agents.

Therefore:

- make small, meaningful commits;
- each commit should represent one coherent slice;
- commit immediately after a coherent file/module/feature becomes working and tested;
- avoid giant commits containing the entire application;
- do not create meaningless "update" commits just to inflate the number;
- keep commit messages specific and human-readable.

A reasonable progression is:

```text
chore: add project skeleton
chore: add runtime configuration
feat: add carla session connection
feat: add world setup
feat: add ego vehicle spawning
feat: add traffic spawning
feat: add xbox input abstraction
feat: add analog input normalization
feat: add camera rig
feat: add main camera rendering
feat: add rear mirror camera
feat: add lidar sensor
feat: add lidar widget
feat: add rear parking distance sensor
feat: add parking distance widget
feat: add parking beep controller
feat: add telemetry hud
feat: add launcher session setup
feat: connect launcher to driving session
fix: restore carla settings on shutdown
fix: handle controller disconnect safely
refactor: simplify runtime state
```

Do not push broken commits merely to create more commits. Every commit should leave the repository runnable or clearly at a safe intermediate implementation point.

## How to work through the repository

Start by inspecting the repository you inherited.

Then:

1. read `README.md`;
2. read `docs/architecture.md`;
3. read `docs/phase1_scope.md`;
4. inspect the current codebase and identify reusable pieces;
5. build the skeleton;
6. implement one coherent subsystem at a time;
7. run focused tests;
8. commit;
9. continue.

Do not rewrite working code just because you prefer another style.

Do not remove comments or working behavior without a reason connected to this project.

Do not add unrelated refactors.

Do not overengineer.

## Final acceptance run

At the end of Phase 1, perform one complete real-world run:

- start CARLA;
- launch the app;
- choose a map;
- choose a weather preset;
- choose an ego vehicle;
- set traffic and pedestrian counts;
- spawn;
- confirm Xbox analog throttle;
- confirm Xbox analog brake;
- confirm progressive steering;
- switch all three primary cameras;
- verify mirror placement;
- reverse toward an object and verify the rear bar + beep behavior;
- verify the LiDAR panel rotates / updates;
- verify speed and gear;
- drive for several minutes;
- close normally;
- start again and confirm the previous run did not leave CARLA in a broken state.

Only after this is clean should Phase 1 be called complete.

## Definition of success

The success criterion is not "the script runs".

The success criterion is:

> **A person can sit in front of the CARLA window and naturally drive around the selected city with an Xbox controller while the application continuously presents the mirror, parking sensor, LiDAR and telemetry in a polished game-like dashboard, and the program remains clean enough that a future agent can add autonomous-driving features without touching the UI architecture or rewriting the CARLA session layer.**
