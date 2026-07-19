import json

import pandas as pd

import scripts.archive_odds_snapshot as aos
from scripts.archive_odds_snapshot import (
    append_snapshot, config_id, match_prob_rows, snapshot_rows,
)


def _payload(generated="2026-07-03 12:00 UTC"):
    return {
        "status": "live",
        "generated": generated,
        "standings": [
            {"team": "Alpha", "elo": 1550, "title": 0.4, "ucl": 0.8,
             "releg": 0.0, "proj_pts": 78.2},
            {"team": "Beta", "elo": 1440, "title": 0.01, "ucl": 0.05,
             "releg": 0.42, "proj_pts": 41.0},
        ],
        "games": [
            {"id": "g1", "home": "Alpha", "away": "Beta", "date": "2026-07-05",
             "pH": 0.61, "pD": 0.22, "pA": 0.17, "result": None},
            {"id": "g0", "home": "Beta", "away": "Alpha", "date": "2026-06-01",
             "pH": 0.3, "pD": 0.3, "pA": 0.4, "result": "H"},
        ],
    }


def test_snapshot_rows_shape():
    rows = snapshot_rows("epl", _payload())
    assert len(rows) == 2
    a = next(r for r in rows if r["team"] == "Alpha")
    assert a["league"] == "epl"
    assert a["snapshot_date"] == "2026-07-03"
    assert a["title"] == 0.4 and a["releg"] == 0.0 and a["elo"] == 1550
    # next upcoming match probs from the team's perspective flags
    assert a["nm_id"] == "g1" and a["nm_is_home"] is True
    assert a["nm_ph"] == 0.61
    # market probs not in payloads yet → archived as None
    assert a["nm_mh"] is None


def test_same_build_appends_once(tmp_path):
    out = tmp_path / "hist.parquet"
    rows = snapshot_rows("epl", _payload())
    append_snapshot(rows, out)
    append_snapshot(rows, out)
    df = pd.read_parquet(out)
    assert len(df) == 2  # deduped on league+team+snapshot_date


def test_second_date_appends_new_rows(tmp_path):
    out = tmp_path / "hist.parquet"
    append_snapshot(snapshot_rows("epl", _payload()), out)
    append_snapshot(snapshot_rows(
        "epl", _payload(generated="2026-07-04 12:00 UTC")), out)
    df = pd.read_parquet(out)
    assert len(df) == 4
    assert set(df["snapshot_date"]) == {"2026-07-03", "2026-07-04"}


# ── provenance (n_played, config_id, code_rev) — 2026-07-10 drift-tracking step 1 ──

def test_n_played_counts_results_only():
    rows = snapshot_rows("epl", _payload())
    # _payload() has 1 played game (result="H") and 1 upcoming (result=None)
    assert all(r["n_played"] == 1 for r in rows)


def test_config_id_reads_champion_run_id(monkeypatch, tmp_path):
    champ = tmp_path / "champion.json"
    champ.write_text(json.dumps({"run_id": "test-run-abc123"}))
    monkeypatch.setattr(aos, "_CHAMPION", champ)
    monkeypatch.setattr(aos, "_config_id_cache", None)
    assert config_id() == "test-run-abc123"


def test_config_id_missing_file_is_unknown_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.setattr(aos, "_CHAMPION", tmp_path / "nope.json")
    monkeypatch.setattr(aos, "_config_id_cache", None)
    assert config_id() == "unknown"


def test_provenance_columns_present_on_every_row(monkeypatch, tmp_path):
    champ = tmp_path / "champion.json"
    champ.write_text(json.dumps({"run_id": "rX"}))
    monkeypatch.setattr(aos, "_CHAMPION", champ)
    monkeypatch.setattr(aos, "_config_id_cache", None)
    rows = snapshot_rows("epl", _payload())
    assert all(r["config_id"] == "rX" for r in rows)
    assert all("code_rev" in r for r in rows)


def test_snapshot_rows_captures_season():
    payload = _payload()
    payload["season"] = 2026
    rows = snapshot_rows("epl", payload)
    assert all(r["season"] == 2026 for r in rows)


def test_snapshot_rows_season_defaults_to_none_when_absent():
    rows = snapshot_rows("epl", _payload())
    assert all(r["season"] is None for r in rows)


# ── S1: stable team_id / fixture_id capture ─────────────────────────────────

def test_snapshot_rows_captures_team_id():
    payload = _payload()
    payload["standings"][0]["team_id"] = "TID_ALPHA"
    rows = snapshot_rows("epl", payload)
    a = next(r for r in rows if r["team"] == "Alpha")
    assert a["team_id"] == "TID_ALPHA"


def test_snapshot_rows_derives_stable_team_id_when_absent():
    rows = snapshot_rows("epl", _payload())
    assert all(r["team_id"].startswith("v1:") for r in rows)
    assert len({r["team_id"] for r in rows}) == len(rows)


def test_match_prob_rows_captures_home_away_fixture_ids():
    payload = _payload()
    payload["games"][0].update(home_id="TID_A", away_id="TID_B", fixture_id="v1:deadbeef")
    r = match_prob_rows("epl", payload)[0]
    assert r["home_id"] == "TID_A" and r["away_id"] == "TID_B" and r["fixture_id"] == "v1:deadbeef"


def test_match_prob_rows_derives_stable_ids_when_absent():
    first = match_prob_rows("epl", _payload())[0]
    second = match_prob_rows("epl", _payload())[0]
    assert first["home_id"].startswith("v1:")
    assert first["away_id"].startswith("v1:")
    assert first["fixture_id"].startswith("v1:")
    assert first["fixture_id"] == second["fixture_id"]


# ── the "conf" collision fix (2026-07-10): MLS ships conf="East"/"West"      ──
# (conference name, a string); some UEFA leagues ship conf=<float>           ──
# (Conference-League qualification %). Only the numeric form belongs in an   ──
# odds column — mixing the two crashed to_parquet the first time this ran.  ──

def test_string_conf_is_dropped_not_archived():
    payload = _payload()
    payload["standings"][0]["conf"] = "East"   # MLS-shaped value
    rows = snapshot_rows("mls", payload)
    assert all(r["conf"] is None for r in rows)


def test_numeric_conf_is_kept():
    payload = _payload()
    payload["standings"][0]["conf"] = 2.3       # UEFA Conference-League odds
    rows = snapshot_rows("epl", payload)
    a = next(r for r in rows if r["team"] == "Alpha")
    assert a["conf"] == 2.3


def test_mixed_league_conf_types_do_not_break_parquet_write(tmp_path):
    """The original crash: concatenating an MLS-shaped string 'conf' with a
    UEFA-shaped float 'conf' into one DataFrame broke to_parquet outright."""
    mls_rows = snapshot_rows("mls", {**_payload(),
                             "standings": [{**_payload()["standings"][0], "conf": "East"}]})
    epl_rows = snapshot_rows("epl", {**_payload(),
                             "standings": [{**_payload()["standings"][0], "conf": 1.8}]})
    out = tmp_path / "hist.parquet"
    append_snapshot(mls_rows + epl_rows, out)   # must not raise
    df = pd.read_parquet(out)
    assert len(df) == 2


# ── match_prob_rows / match_prob_history (drift-tracking step 1b) ───────────

def test_match_prob_rows_only_upcoming_games():
    rows = match_prob_rows("epl", _payload())
    assert len(rows) == 1        # the played g0 row is excluded
    r = rows[0]
    assert r["home"] == "Alpha" and r["away"] == "Beta"
    assert r["pH"] == 0.61 and r["pD"] == 0.22 and r["pA"] == 0.17


def test_match_prob_rows_days_to_kickoff():
    # snapshot_date=2026-07-03, fixture date=2026-07-05 → 2 days out
    r = match_prob_rows("epl", _payload())[0]
    assert r["days_to_kickoff"] == 2


def test_match_prob_rows_carries_market_probs_when_present():
    payload = _payload()
    payload["games"][0].update(mkt_home=0.55, mkt_draw=0.24, mkt_away=0.21)
    r = match_prob_rows("epl", payload)[0]
    assert r["mkt_home"] == 0.55 and r["mkt_draw"] == 0.24 and r["mkt_away"] == 0.21


def test_match_prob_rows_empty_without_snapshot_date():
    assert match_prob_rows("epl", {"generated": "", "games": []}) == []


def test_match_prob_history_dedup_key_is_fixture_not_ephemeral_id(tmp_path):
    """game card 'id' is an index into that build's remaining-fixtures array
    (SIM PORTING CONTRACT) — NOT stable across builds — so two builds on the
    same day for the same fixture must collapse to one row even if 'id' drifts."""
    out = tmp_path / "match.parquet"
    p1 = _payload()
    p1["games"][0]["id"] = "gX"
    p2 = _payload()
    p2["games"][0]["id"] = "gY"       # id reshuffled, fixture identity unchanged
    append_snapshot(match_prob_rows("epl", p1), out, aos._MATCH_DEDUP_KEYS)
    append_snapshot(match_prob_rows("epl", p2), out, aos._MATCH_DEDUP_KEYS)
    df = pd.read_parquet(out)
    assert len(df) == 1


def test_match_prob_history_accrues_across_snapshot_dates(tmp_path):
    out = tmp_path / "match.parquet"
    append_snapshot(match_prob_rows("epl", _payload()), out, aos._MATCH_DEDUP_KEYS)
    append_snapshot(match_prob_rows(
        "epl", _payload(generated="2026-07-04 12:00 UTC")), out, aos._MATCH_DEDUP_KEYS)
    df = pd.read_parquet(out)
    assert len(df) == 2
    assert sorted(df["days_to_kickoff"]) == [1, 2]   # kickoff funnel: closer each day
