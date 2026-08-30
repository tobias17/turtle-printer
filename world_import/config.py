"""
Loads world_import/config.json - the local, gitignored settings for
importing generated structures into a real Minecraft world save (the
save's filesystem path, which dimension, where to paste, how big an area
to clear first). See config.example.json for the template; config.json
itself is never committed since the save path is machine-specific and the
save itself is personal data.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
EXAMPLE_PATH = HERE / "config.example.json"

REQUIRED_KEYS = ("save_path", "dimension", "origin", "clear_size", "clear_margin")


def load_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"{CONFIG_PATH} not found - copy {EXAMPLE_PATH.name} to "
            f"{CONFIG_PATH.name} and fill in your own save_path/dimension "
            f"(config.json is gitignored, it's never committed)."
        )
    config = json.loads(CONFIG_PATH.read_text())
    missing = [k for k in REQUIRED_KEYS if k not in config]
    if missing:
        raise ValueError(f"{CONFIG_PATH} is missing required key(s): {missing}")

    save_path = Path(config["save_path"])
    if not save_path.is_dir():
        raise FileNotFoundError(f"save_path {save_path} (from {CONFIG_PATH}) does not exist")
    if not (save_path / "level.dat").exists():
        raise FileNotFoundError(f"save_path {save_path} has no level.dat - is this a world save directory?")

    config["save_path"] = save_path
    config["origin"] = tuple(config["origin"])
    config["clear_size"] = tuple(config["clear_size"])
    return config
