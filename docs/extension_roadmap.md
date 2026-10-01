# Future Extension Roadmap

The directory structure should support these future phases without a rewrite.

## Phase 2 — Driver assistance

Possible passive modules:

- front obstacle awareness;
- lane departure warning;
- blind-spot monitoring;
- richer parking visualization.

## Phase 3 — Assisted control

Possible modules:

- collision-warning intervention behind an explicit driver-assistance mode;
- lane centering;
- speed assistance.

## Phase 4 — Perception

Possible modules:

- camera-based lane detection;
- object detection;
- semantic segmentation;
- multi-sensor fusion.

## Phase 5 — Autonomous behavior

Possible modules:

- planning;
- steering control;
- longitudinal control;
- route execution;
- scenario handling.

## Architecture rule for future phases

New autonomy modules should consume clean state/sensor interfaces and publish proposed control or assistance state. They should not reach directly into Pygame widgets or duplicate CARLA actor ownership.
