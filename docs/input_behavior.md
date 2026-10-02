# Xbox Input Behavior

## Normalization pipeline

Raw axis
 -> device-specific mapping
 -> polarity correction
 -> deadzone removal
 -> range remap
 -> response curve
 -> optional smoothing
 -> final clamp
 -> VehicleControl

## Steering

Desired characteristics:

- centered stick = centered steering;
- tiny stick input = tiny steering;
- mid stick = moderate steering;
- full stick = full steering;
- leaving the stick should return steering naturally toward center;
- steering should not jump because of a small controller noise signal.

Keep all response parameters configurable.

## Throttle / brake

The trigger should remain analog from 0 to 1.

Low trigger travel must remain useful; do not immediately jump to high throttle.

## Recommended defaults

Use a small configurable steering deadzone rather than a large deadzone. Start conservatively, then tune during a real driving test.

Do not hard-code a response curve that cannot be changed without editing Python.

## Button layer

Use named actions instead of raw button indices:

- `camera_next`
- `camera_previous`
- `reverse_toggle`
- `handbrake`
- `reset_vehicle`
- `pause`
- `indicator_left`
- `indicator_right`
- `headlight_cycle`
- `quit`

The mapping should live in configuration.

## Current default mapping

The starting mapping uses pygame axis 0 for steering, axis 5 for throttle, and axis 4 for brake. Trigger values are remapped from configurable `trigger_rest_value` to `trigger_full_value`; some drivers expose triggers in a different range or share a single axis. D-pad actions use the configured pygame hat (`dpad_hat`), and the held horn uses the configured button (`horn_button`, default 9). Use `carla-drive --controller-debug` to read raw axes, buttons, and hats, then tune mappings in YAML rather than assuming every driver reports controls identically.

Keyboard fallback is available when no configured gamepad is connected: W/S or arrow keys control throttle/brake, A/D steer, R toggles reverse, C/Q cycle views, Space is handbrake, Backspace resets, P pauses, and Esc exits. Reverse changes are rejected above the configured low-speed limit when stop-before-reverse is enabled. Indicators turn off when the controller disconnects; headlights retain their selected mode.
