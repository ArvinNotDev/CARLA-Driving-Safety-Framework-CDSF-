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
- `quit`

The mapping should live in configuration.
