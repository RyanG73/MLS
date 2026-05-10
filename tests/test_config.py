from datetime import date

from config import _resolve_current_season


def test_current_season_defaults_to_current_year(monkeypatch):
    monkeypatch.delenv("MLS_CURRENT_SEASON", raising=False)
    assert _resolve_current_season(None) == date.today().year


def test_current_season_env_override(monkeypatch):
    monkeypatch.setenv("MLS_CURRENT_SEASON", "2030")
    assert _resolve_current_season(None) == 2030


def test_stale_config_season_is_advanced_without_env(monkeypatch):
    monkeypatch.delenv("MLS_CURRENT_SEASON", raising=False)
    assert _resolve_current_season(2025) >= date.today().year
