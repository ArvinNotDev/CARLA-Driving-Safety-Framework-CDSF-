"""Read-only CARLA connection smoke check for the configured server."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import carla

from carla_drive.carla.session import friendly_map_name, vehicle_options
from carla_drive.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "config" / "defaults.example.yaml")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        config = load_config(args.config)
        client = carla.Client(config.carla.host, config.carla.port)
        client.set_timeout(config.carla.timeout_seconds)
        world = client.get_world()
        maps = client.get_available_maps()
        vehicles = vehicle_options(world)
        print(f"Connected to CARLA {client.get_client_version()}")
        print(f"Current map: {friendly_map_name(world.get_map().name)}")
        print(f"Maps available: {len(maps)}")
        print(f"Four-wheel vehicle blueprints: {len(vehicles)}")
    except (RuntimeError, ValueError) as exc:
        print(f"CARLA smoke check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
