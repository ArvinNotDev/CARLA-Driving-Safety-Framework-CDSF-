"""Main camera modes backed by one transform-switching RGB sensor."""

from __future__ import annotations

import threading
import time

import carla
import numpy as np

from carla_drive.config import CameraConfig
from carla_drive.domain import CameraMode


class LatestImage:
    """Thread-safe latest-frame slot; old camera frames are discarded."""

    def __init__(self):
        self._lock = threading.Lock()
        self._image: np.ndarray | None = None
        self._received_at = 0.0

    def callback(self, image: carla.Image) -> None:
        rgba = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(image.height, image.width, 4)
        rgb = rgba[:, :, 2::-1].copy()
        with self._lock:
            self._image = rgb
            self._received_at = time.monotonic()

    def read(self) -> tuple[np.ndarray | None, float]:
        with self._lock:
            return self._image, self._received_at


class CameraRig:
    """Owns the active driving camera and changes its relative transform by mode."""

    def __init__(self, session, config: CameraConfig):
        if session.ego_vehicle is None:
            raise RuntimeError("Spawn the ego vehicle before creating its camera rig.")
        self.config = config
        self.mode = CameraMode.CHASE
        self.transforms = {
            CameraMode.COCKPIT: carla.Transform(
                carla.Location(x=config.cockpit_x, y=config.cockpit_y, z=config.cockpit_z),
                carla.Rotation(pitch=config.cockpit_pitch),
            ),
            CameraMode.CHASE: carla.Transform(
                carla.Location(x=config.chase_x, y=config.chase_y, z=config.chase_z),
                carla.Rotation(pitch=config.chase_pitch),
            ),
            CameraMode.OVERHEAD: carla.Transform(
                carla.Location(x=config.overhead_x, y=config.overhead_y, z=config.overhead_z),
                carla.Rotation(pitch=config.overhead_pitch),
            ),
        }
        self.frame = LatestImage()
        library = session.world.get_blueprint_library()
        blueprint = library.find("sensor.camera.rgb")
        blueprint.set_attribute("image_size_x", str(config.width))
        blueprint.set_attribute("image_size_y", str(config.height))
        blueprint.set_attribute("fov", str(config.fov))
        self.actor = session.world.spawn_actor(
            blueprint,
            self.transforms[self.mode],
            attach_to=session.ego_vehicle,
            attachment_type=carla.AttachmentType.Rigid,
        )
        session.track_sensor(self.actor)
        self.actor.listen(self.frame.callback)

    def set_mode(self, mode: CameraMode) -> None:
        self.mode = mode
        self.actor.set_transform(self.transforms[mode])

    def next_mode(self, direction: int = 1) -> CameraMode:
        modes = list(CameraMode)
        self.set_mode(modes[(modes.index(self.mode) + direction) % len(modes)])
        return self.mode

    def latest_frame(self) -> tuple[np.ndarray | None, float]:
        return self.frame.read()
