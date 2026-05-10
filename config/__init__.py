import os
from datetime import date
import yaml
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent


def _resolve_current_season(raw_value) -> int:
    """Resolve active MLS season from env, config, or today's year."""
    env_value = os.environ.get("MLS_CURRENT_SEASON")
    if env_value:
        return int(env_value)
    if raw_value not in (None, ""):
        configured = int(raw_value)
        # Avoid silently running stale daily updates after New Year unless the
        # operator explicitly pins the season with MLS_CURRENT_SEASON.
        return max(configured, date.today().year)
    return date.today().year


def load_settings() -> dict:
    settings_path = _REPO_ROOT / "config" / "settings.yaml"
    with open(settings_path) as f:
        cfg = yaml.safe_load(f)
    cfg["_repo_root"] = str(_REPO_ROOT)
    cfg.setdefault("data", {})
    cfg["data"]["current_season"] = _resolve_current_season(
        cfg["data"].get("current_season")
    )
    return cfg


SETTINGS = load_settings()
