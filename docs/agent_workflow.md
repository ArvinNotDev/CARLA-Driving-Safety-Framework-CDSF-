# Agent Workflow

## Before editing

1. Read `README.md`.
2. Read `AGENT_PROMPT.md`.
3. Read this folder.
4. Inspect the existing repository before creating replacement files.

## Implementation rhythm

Work in small slices:

```text
inspect
-> implement
-> run focused checks
-> manual smoke test when relevant
-> commit
-> continue
```

## Do not do

- giant rewrites;
- automatic refactors across unrelated modules;
- deleting working code without a requirement;
- adding frameworks just for abstraction;
- changing CARLA version silently;
- mixing Phase 1 UI work with autonomous driving.

## Agent-friendly naming

Prefer names like:

- `CarlaSession`
- `TrafficManagerController`
- `XboxController`
- `CameraRig`
- `RearParkingSensor`
- `LidarMonitor`
- `Dashboard`
- `VehicleState`
- `SensorSnapshot`

Avoid generic names like `Manager2`, `HelperFinal`, `utils2`.

## Commit quality

A commit should tell a future agent what became true after that commit.

Good:

`feat: add rear parking distance snapshot`

Bad:

`changes`
