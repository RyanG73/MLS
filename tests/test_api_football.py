"""API-Football adapter — env-keyed, parses fixtures into the canonical frame. No network."""
from __future__ import annotations

import pytest


def _sample_payload():
    return {"response": [
        {  # finished match
            "fixture": {"id": 101, "date": "2025-04-05T23:00:00+00:00",
                        "status": {"short": "FT"}},
            "league": {"season": 2025},
            "teams": {"home": {"name": "Forge FC"}, "away": {"name": "Cavalry FC"}},
            "goals": {"home": 2, "away": 1},
        },
        {  # not-started match
            "fixture": {"id": 102, "date": "2026-07-16T23:00:00+00:00",
                        "status": {"short": "NS"}},
            "league": {"season": 2026},
            "teams": {"home": {"name": "Pacific FC"}, "away": {"name": "Forge FC"}},
            "goals": {"home": None, "away": None},
        },
    ]}


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
    from data_pipeline import api_football
    monkeypatch.setattr(api_football, "_load_dotenv", lambda: None)  # ignore any real .env
    with pytest.raises(RuntimeError, match="API_FOOTBALL_KEY"):
        api_football._require_key()


def test_parse_canonical_schema():
    from data_pipeline import api_football
    from data_pipeline.understat import _COLS
    df = api_football._parse_fixtures(_sample_payload())
    assert list(df.columns) == _COLS
    assert len(df) == 2


def test_parse_result_row():
    from data_pipeline import api_football
    df = api_football._parse_fixtures(_sample_payload())
    fin = df[df["is_result"]]
    assert len(fin) == 1
    row = fin.iloc[0]
    assert row["home_team"] == "Forge FC" and row["away_team"] == "Cavalry FC"
    assert row["home_goals"] == 2.0 and row["away_goals"] == 1.0
    assert row["label_result"] == 0.0        # home win
    assert row["season"] == 2025


def test_parse_upcoming_row_has_nan_goals():
    from data_pipeline import api_football
    df = api_football._parse_fixtures(_sample_payload())
    upc = df[~df["is_result"]]
    assert len(upc) == 1
    assert upc["home_goals"].isna().all() and upc["away_goals"].isna().all()


def test_results_and_upcoming_split(monkeypatch):
    from data_pipeline import api_football
    monkeypatch.setattr(api_football, "_fetch_league",
                        lambda af_id, seasons: api_football._parse_fixtures(_sample_payload()))
    monkeypatch.setitem(api_football.LEAGUE, "canadian-pl", (468, [2025, 2026]))
    up = api_football.upcoming_fixtures("canadian-pl")
    assert (~up["is_result"]).all() and len(up) == 1


# ── per-league canonical name map (Stage 3: spine names → our ESPN names) ────
def test_results_frame_applies_configured_team_names(monkeypatch, tmp_path):
    """Spine frames must carry OUR canonical (ESPN) spellings so crests,
    metadata, and downstream name-keyed logic survive the source flip."""
    import json
    from data_pipeline import api_football
    cfg = tmp_path / "names.json"
    cfg.write_text(json.dumps(
        {"canadian-pl": {"Forge FC": "Forge", "Pacific FC": "Pacific"}}))
    monkeypatch.setattr(api_football, "_NAMES_PATH", cfg)
    api_football._team_names.cache_clear()
    monkeypatch.setattr(api_football, "_fetch_league",
                        lambda af_id, seasons: api_football._parse_fixtures(_sample_payload()))
    monkeypatch.setitem(api_football.LEAGUE, "canadian-pl", (468, [2025, 2026]))
    df = api_football.results_frame("canadian-pl")
    names = set(df["home_team"]) | set(df["away_team"])
    assert "Forge" in names and "Pacific" in names
    assert "Forge FC" not in names
    assert "Cavalry FC" in names            # unmapped names pass through
    api_football._team_names.cache_clear()


def test_results_frame_without_config_is_unchanged(monkeypatch, tmp_path):
    from data_pipeline import api_football
    monkeypatch.setattr(api_football, "_NAMES_PATH", tmp_path / "absent.json")
    api_football._team_names.cache_clear()
    monkeypatch.setattr(api_football, "_fetch_league",
                        lambda af_id, seasons: api_football._parse_fixtures(_sample_payload()))
    monkeypatch.setitem(api_football.LEAGUE, "canadian-pl", (468, [2025, 2026]))
    df = api_football.results_frame("canadian-pl")
    assert "Forge FC" in set(df["home_team"])
    api_football._team_names.cache_clear()


# ── pagination (spec Stage 0: built blind, tested against fixtures) ──────────
def _page_fixture(fid: int) -> dict:
    return {"fixture": {"id": fid, "date": "2025-04-05T23:00:00+00:00",
                        "status": {"short": "FT"}},
            "league": {"season": 2025},
            "teams": {"home": {"name": f"H{fid}"}, "away": {"name": f"A{fid}"}},
            "goals": {"home": 1, "away": 0}}


def test_get_paged_merges_all_pages(monkeypatch):
    from data_pipeline import api_football
    calls = []

    def fake_get(path, params, budget="ops"):
        page = params.get("page", 1)
        calls.append(page)
        return {"response": [_page_fixture(page)],
                "paging": {"current": page, "total": 3}}

    monkeypatch.setattr(api_football, "_get", fake_get)
    payload = api_football._get_paged("fixtures", {"league": 1, "season": 2025})
    assert calls == [1, 2, 3]
    assert [f["fixture"]["id"] for f in payload["response"]] == [1, 2, 3]


def test_get_paged_single_page_makes_one_request(monkeypatch):
    from data_pipeline import api_football
    calls = []

    def fake_get(path, params, budget="ops"):
        calls.append(params.get("page", 1))
        return {"response": [_page_fixture(1)],
                "paging": {"current": 1, "total": 1}}

    monkeypatch.setattr(api_football, "_get", fake_get)
    payload = api_football._get_paged("fixtures", {"league": 1, "season": 2025})
    assert calls == [1] and len(payload["response"]) == 1


# ── governor wiring: budget before, plan assertion after, throttle pacing ────
class _FakeResponse:
    def __init__(self, headers=None):
        self.headers = headers or {}

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": [_page_fixture(1)]}


@pytest.fixture
def isolated_health(tmp_path, monkeypatch):
    from data_pipeline import source_health
    monkeypatch.setattr(source_health, "_HEALTH_PATH",
                        tmp_path / "source_health.parquet")


def test_get_refuses_before_requesting_when_budget_exhausted(monkeypatch, isolated_health):
    from data_pipeline import api_football, api_budget
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-key")

    def no_network(*a, **k):
        raise AssertionError("HTTP request made despite exhausted budget")

    monkeypatch.setattr(api_football.requests, "get", no_network)
    monkeypatch.setattr(api_budget, "check_budget",
                        lambda kind="ops", now=None: (_ for _ in ()).throw(
                            api_budget.BudgetExceeded("spent")))
    with pytest.raises(api_budget.BudgetExceeded):
        api_football._get("fixtures", {"league": 1})


def test_get_raises_plan_mismatch_from_response_headers(monkeypatch, isolated_health):
    from data_pipeline import api_football, api_budget
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-key")
    monkeypatch.setenv("API_FOOTBALL_PLAN", "pro")
    monkeypatch.setattr(api_football.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        api_football.requests, "get",
        lambda *a, **k: _FakeResponse({"x-ratelimit-requests-limit": "100"}))
    with pytest.raises(api_budget.PlanMismatch):
        api_football._get("fixtures", {"league": 1})


def test_get_paces_at_plan_throttle_delay(monkeypatch, isolated_health):
    from data_pipeline import api_football
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-key")
    monkeypatch.setenv("API_FOOTBALL_PLAN", "free")   # 10 r/m → 12 s at 50%
    sleeps = []
    monkeypatch.setattr(api_football.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(
        api_football.requests, "get",
        lambda *a, **k: _FakeResponse({"x-ratelimit-requests-limit": "100"}))
    api_football._get("fixtures", {"league": 1})
    assert sleeps == [pytest.approx(12.0)]
