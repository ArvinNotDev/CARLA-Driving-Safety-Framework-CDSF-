# Kinematic impact candidate detector

`KinematicCollisionDetector` reports strong impact-like changes in the ego vehicle's motion. It is a passive estimate, not a collision sensor and not CARLA ground truth.

## Signals and method

The runtime supplies one sample per available CARLA world snapshot:

- simulation timestamp in seconds from the world snapshot;
- signed vehicle velocity projected onto the vehicle's forward axis, in m/s;
- applied brake and throttle inputs in `[0, 1]`;
- selected forward/reverse state.

The detector keeps the last eight samples. It uses elapsed simulation time between distinct samples, so duplicate render frames do not affect the derivatives and variable frame intervals do not change their units. It orients velocity using the selected gear, then tracks its absolute longitudinal component so a collision that reverses the vehicle's direction can still register as a speed loss. Longitudinal acceleration is estimated as `dv / dt`; deceleration is the negative component of that speed derivative. Jerk is estimated from the increase in deceleration over `dt`. CARLA's full acceleration vector is not used: differencing the forward-axis velocity directly avoids including lateral acceleration from turns or vertical motion in this longitudinal estimate.

The expected normal deceleration is a simple envelope:

```text
expected = max(
    1.0 + (1 - mean_throttle) * throttle_release_deceleration,
    1.0 + mean_brake * (normal_braking_deceleration - 1.0)
)  m/s²
```

The detector marks a sample as anomalous when the previous speed is at least `minimum_speed_mps` and observed deceleration exceeds this brake- and throttle-aware envelope by `excess_deceleration_mps2`. Ordinary braking and expected deceleration while off throttle are accounted for continuously rather than disabling detection whenever the brake is pressed. An event requires either two anomalous samples within `confirmation_window_seconds`, or one strong sample whose excess deceleration is at least 2.5 times the configured excess threshold and whose jerk exceeds `jerk_threshold_mps3`. A cooldown and return-to-normal rearm prevent duplicate reports for the same sustained event.

The reported `impact_score` is a bounded evidence score, **not a probability**. It combines normalized excess deceleration (50%), jerk (30%), pre-event speed (12%), and temporal persistence (8%). The event also contains the sample time, speeds before/after the candidate, peak deceleration and jerk, current brake/throttle, and a short reason.

Defaults are in `config/defaults.example.yaml` under `safety`. The detector resets on a vehicle reset or actor change, missing actor snapshot, reverse/forward change, backwards simulation time, or a long telemetry gap. It is created fresh for each driving loop.

## Limitations and validation

Kinematics alone cannot distinguish every collision from emergency braking, curbs, physics discontinuities, or other abrupt maneuvers. Low-speed and glancing impacts may not produce enough longitudinal speed loss to cross the thresholds. Treat each result as an impact candidate; do not treat it as collision ground truth or use it as an automatic control input.

The unit tests use deterministic synthetic velocity/control sequences. A CARLA controlled-drive validation is still needed to tune the defaults against normal braking, rough roads, and representative impacts on the target vehicle and timestep.
