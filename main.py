"""Run CARLA Drive from a source checkout."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from carla_drive.app.main import main


if __name__ == "__main__":
    raise SystemExit(main())
