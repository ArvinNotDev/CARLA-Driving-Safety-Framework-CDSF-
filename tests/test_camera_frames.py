from types import SimpleNamespace

import numpy as np

from carla_drive.camera.rig import LatestImage


def test_camera_switch_discards_frames_from_previous_view():
    frames = LatestImage()
    pixels = np.zeros((2, 3, 4), dtype=np.uint8)
    old = SimpleNamespace(frame=10, width=3, height=2, raw_data=pixels.tobytes())
    current = SimpleNamespace(frame=12, width=3, height=2, raw_data=pixels.tobytes())

    frames.callback(old)
    assert frames.read()[0] is not None
    frames.clear_before(12)
    frames.callback(old)
    assert frames.read()[0] is None
    frames.callback(current)
    assert frames.read()[0].shape == (2, 3, 3)
