# Suggested Commit Sequence

The exact split may change after repository inspection, but keep the history incremental and meaningful.

1. `chore: add project skeleton`
2. `chore: add runtime configuration`
3. `feat: add carla connection session`
4. `feat: add world and synchronous setup`
5. `feat: add ego vehicle selection and spawn`
6. `feat: add traffic and pedestrian spawning`
7. `feat: add xbox controller abstraction`
8. `feat: add analog input normalization`
9. `feat: add camera rig`
10. `feat: add main driving renderer`
11. `feat: add rear mirror camera`
12. `feat: add lidar monitor`
13. `feat: add rear parking sensor`
14. `feat: add parking distance widget`
15. `feat: add parking beep feedback`
16. `feat: add telemetry hud`
17. `feat: add launcher session controls`
18. `feat: connect launcher to driving session`
19. `fix: harden actor cleanup`
20. `fix: handle controller disconnect`
21. `test: cover input and sensor mapping logic`
22. `docs: document phase one runtime`

A commit can combine two inseparable files when separating them would create a broken intermediate state. Do not artificially fragment a change.
