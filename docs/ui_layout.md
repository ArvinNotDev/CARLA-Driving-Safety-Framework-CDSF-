# UI Layout Contract

The UI contract is more important than the exact artwork. Agents may improve the visual style while preserving placement and hierarchy.

## Session setup screen

Show a clear connection and content-discovery state before setup. Read the available Town maps from CARLA before opening the map dropdown, and show the number of available maps. Keep environment and vehicle choices in dropdowns, use direct increment/decrement controls for traffic counts, and show a compact session summary beside the settings. Include a working link to the project GitHub page.

## Screen hierarchy

1. Main driving camera — dominant area.
2. Rear-view mirror — top-center.
3. Rear parking bar — directly below mirror.
4. LiDAR panel — upper-right.
5. Driving telemetry — lower region.
6. Small contextual indicators — corners / low contrast.

## Suggested proportions

These are starting points, not hard-coded pixel requirements.

- mirror width: ~24–30% of the viewport;
- mirror height: ~10–14% of the viewport;
- LiDAR panel: ~18–24% of viewport width and height;
- main camera: remaining space;
- telemetry: compact and readable at 720p.

## Mirror

Should visually resemble an embedded rear-view mirror, with rounded frame and subtle border.

Do not let the mirror become a second full screen.

## Rear sensor bar

The neutral center should be obvious.

Fill grows outward in both directions.

Distance state should be understandable without reading text.

## LiDAR

Use a dark panel that emphasizes the point cloud and leaves enough contrast for UI labels. Keep the view range independently tunable from the physical sensor range. Show distance rings, vehicle heading, and a small height-color legend so nearby returns are easier to separate.

Prefer top-down 2D projection for Phase 1 so 360 coverage is immediately understandable.

## Speed / gear

The speed readout should be the largest telemetry element.

Gear should be immediately recognizable, e.g. P / R / N / D or an equivalent state.

## Responsiveness

UI animations should never block the simulation loop.

## Controls shown at runtime

Use the configured Xbox button mapping to cycle the three camera modes, toggle reverse, pause, reset to the original spawn, and use the handbrake. Keyboard fallback supports the same actions: A/D steer, W/S or Up/Down control pedals, C/Q cycle cameras or 1/2/3 select one, R toggles reverse, Space holds the handbrake, Backspace resets, P pauses, and Esc exits. Z/X toggle indicators, H cycles headlight modes, and holding F sounds the horn. The rear distance bar and beep are active only while reversing.
