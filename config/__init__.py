import os
import yaml
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent


def load_settings() -> dict:
    settings_path = _REPO_ROOT / "config" / "settings.yaml"
    with open(settings_path) as f:
        cfg = yaml.safe_load(f)
    # Allow env-var overrides for paths
    if db_path_env := os.environ.get("MLS_DB_PATH"):
        cfg["data"]["db_path"] = db_path_env
    # Resolve db_path relative to repo root
    cfg["data"]["db_path"] = str(_REPO_ROOT / cfg["data"]["db_path"])
    cfg["_repo_root"] = str(_REPO_ROOT)
    return cfg


SETTINGS = load_settings()
