# Sensor Plan

## Main RGB

Purpose: driving view.

Use one active camera whose transform is controlled by the CameraRig.

## Rear RGB

Purpose: mirror only.

Fixed rear-facing transform relative to the ego vehicle.

## LiDAR

Purpose: 360 environmental visualization.

Phase 1 visualizes only the latest usable point set. Do not write a recording pipeline unless explicitly requested later.

## Rear parking sensor

Purpose: human feedback while reversing.

Suggested coverage:

- rear-left;
- rear-center;
- rear-right.

Use the nearest valid distance for the main visual state and preserve left/right distances for future richer visualization.

The sensor may be built with multiple `sensor.other.obstacle` actors facing backward. CARLA's obstacle detector is a distance-to-obstacle event sensor with configurable trace distance and hit radius.

## Collision sensor

Purpose: observation/logging only in Phase 1.

Never mutate manual control because of collision state.

## Sensor data contract

Every sensor module should expose data that is safe to consume from the UI without the UI knowing about raw CARLA actor APIs.

Also expose data age / availability so the UI can handle a temporarily missing sensor frame gracefully.
