# Architecture

## Core principle

Keep the application readable enough that a new agent can open the repository and understand the runtime in a few minutes.

The project has one top-level coordinator and several practical managers. Managers own resources; UI widgets do not.

## Layers

```text
Pygame UI
    |
    v
Presentation state / snapshots
    |
    +-------------------+
    |                   |
Input normalization   Sensor snapshots
    |                   |
    +---------+---------+
              |
        Driving session
              |
       CARLA session layer
              |
          CARLA API
```

This is a dependency direction, not an invitation to build a giant layered framework.

## Ownership

### `app`

The application lifecycle, screen transitions and main loop.

### `carla`

All direct world/actor lifecycle operations.

### `input`

Raw gamepad -> normalized user intent.

### `camera`

Camera presets and active image stream.

### `sensors`

Raw CARLA sensor actors -> compact state.

### `domain`

Small data objects shared across modules.

### `ui`

State -> pixels/audio. UI does not own CARLA actors.

### `utils`

Only reusable low-level helpers.

## Important ownership rule

Any CARLA actor spawned by the application must have exactly one obvious owner.

That owner must register it for cleanup.

Do not keep random actor references in UI widgets.

## Main loop responsibilities

The main loop may coordinate:

- controller read;
- control application;
- simulation tick;
- snapshot refresh;
- UI render;
- input events.

The main loop should not contain:

- raw joystick axis remapping;
- blueprint selection logic;
- LiDAR point-cloud conversion details;
- rear sensor threshold logic;
- complicated drawing code;
- actor destruction details.

## Threading

Do not add threads by default.

Use CARLA's sensor callback system to capture incoming data into bounded/latest-frame state. Pygame rendering stays in the main thread.

Introduce a worker only if a measured bottleneck justifies it, and document the ownership of any shared data.

## Phase 1 implementation map

The entry point is `carla_drive.app.main`. The launcher collects a `SessionConfig`; `CarlaSession` loads the selected map/weather and registers every spawned actor. `CameraRig` owns one transform-switching main camera. `MonitorSensors` owns passive dashboard sensors and publishes latest-frame or latest-distance snapshots. `Dashboard` receives those snapshots and never queries CARLA actors.

The synchronous world is advanced only by `run_driving_loop`. It ticks at the configured fixed step while Pygame renders at its own target frame rate. Camera and LiDAR callbacks replace bounded latest-frame values; they do not render or mutate controls.
