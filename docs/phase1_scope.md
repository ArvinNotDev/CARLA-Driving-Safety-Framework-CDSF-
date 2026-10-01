# Phase 1 Scope

## In

- launcher/setup screen;
- map selection;
- weather selection;
- ego vehicle selection;
- vehicle/pedestrian traffic counts;
- manual Xbox driving;
- analog controls;
- three camera modes;
- rear-view mirror;
- 360 LiDAR mini-panel;
- rear parking sensor visualization;
- rear sensor beeps;
- speed / gear / control telemetry;
- robust cleanup;
- basic logs and tests.

## Explicitly out

- autonomous driving;
- collision avoidance control;
- emergency braking;
- lane keeping;
- route following;
- ML model inference;
- perception-to-control pipeline;
- autonomous parking.

## Design constraint

Future assistance/autonomy features should be added beside the human-control pipeline, not hidden inside it.

A future system should be able to consume the same sensor snapshots without requiring a rewrite of the dashboard.
