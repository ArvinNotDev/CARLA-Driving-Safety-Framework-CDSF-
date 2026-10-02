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

The implementation uses three narrow traces (left, center, right), expires measurements that stop receiving callbacks, and presents the nearest fresh distance. The bar uses each side's distance, with the center trace contributing to both halves. Missing events display “NO TARGET,” since silence does not prove the space behind the vehicle is clear. Its coordinates and trace range are configurable. It only produces dashboard state; no sensor callback can apply control.

The LiDAR callback decimates each measurement to a configured display-point budget before storing it. The UI draws a zoomed top-down 360-degree view with distance rings and return-height colors. `display_range_m` controls the visible crop independently of the physical sensor `range_m`. This is a display monitor, not object classification or control input.

## Kinematic impact detection

Impact candidates are estimated in `safety/kinematic_collision.py` from the ego vehicle's longitudinal velocity, simulation timestamps, and applied pedal inputs. The estimator derives deceleration and jerk from short-term history and accounts for the expected braking response.

The detector does not spawn or consume collision, obstacle, camera, or LiDAR sensors. It reports kinematic candidates only; it does not mutate manual control and is not ground-truth collision data. See `docs/kinematic_collision.md` for the decision rule and limitations.

## Sensor data contract

Every sensor module should expose data that is safe to consume from the UI without the UI knowing about raw CARLA actor APIs.

Also expose data age / availability so the UI can handle a temporarily missing sensor frame gracefully.
