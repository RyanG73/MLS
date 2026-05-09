import os
import yaml
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent


def load_settings() -> dict:
    settings_path = _REPO_ROOT / "config" / "settings.yaml"
    with open(settings_path) as f:
        cfg = yaml.safe_load(f)
    cfg["_repo_root"] = str(_REPO_ROOT)
    return cfg


SETTINGS = load_settings()
