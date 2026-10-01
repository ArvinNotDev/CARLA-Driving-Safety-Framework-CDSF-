# Legacy Inspiration Notes

This file records useful patterns found in the user's earlier CARLA work so a new agent can borrow ideas without importing unrelated complexity.

## Useful patterns

### CameraManager

Previous experiments already use a dedicated camera object, a sensor queue/latest-image pattern and explicit image conversion. Keep that concept, but make it part of the new camera subsystem.

### Manual collector / runtime scripts

Earlier code contains a good lifecycle pattern:

- connect;
- capture original world settings;
- enable synchronous mode when required;
- configure Traffic Manager;
- spawn actors;
- clean up in reverse order;
- restore original settings.

This is a good foundation for `CarlaSession`.

### Route helper

The existing route helper demonstrates the value of small focused CARLA helpers. Phase 1 does not need route planning, but the project structure should leave a clean place for it later.

### Previous driving app

The old driving application has useful separation ideas for a Carla manager, input manager, controller, camera manager and vision components. The new Phase 1 system should stop at the human-driving boundary and remove the autonomous-driving coupling.

## Patterns to avoid carrying forward

- giant main application modules;
- ML inference in the manual UI loop;
- parking state machines inside the core runtime;
- safety code that silently alters human control;
- debug overlays everywhere;
- feature flags that expose half-finished autonomy behavior.

The new project should be simpler even if it can eventually become more capable.
