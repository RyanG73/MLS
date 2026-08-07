"""Every modeled UEFA league must carry an informative prior.

The 2026-07-31 power-rankings bug: ten UEFA top flights were absent from
_LEAGUE_COEFF, so their prior was 0.0 — which on an EPL-anchored scale asserts
Premier League strength rather than absence of knowledge. The bridge's ridge
faithfully held them there, putting Bodo/Glimt 4th and Zenit 5th in the world.
"""
import json
from pathlib import Path

import pytest

from data_pipeline import coefficients as co

_ROOT = Path(__file__).resolve().parents[1]


def _registry():
    txt = (_ROOT / "webapp" / "leagues.js").read_text(encoding="utf-8")
    return json.loads(txt.split("=", 1)[1].rstrip().rstrip(";"))


def _uefa_top_flights():
    return [r["id"] for r in _registry()
            if r.get("confederation") == "UEFA" and r.get("status") == "live"
            and (r.get("tier") or 9) == 1 and not r.get("women")]


def test_no_uefa_top_flight_priors_as_strong_as_the_epl():
    epl = co.static_league_offset("epl")
    for lid in _uefa_top_flights():
        if lid == "epl":
            continue
        offset = co.static_league_offset(lid)
        assert offset < epl - 30, (
            f"{lid} priors within 30 ELO of the Premier League ({offset:.1f} vs "
            f"{epl:.1f}) — add a coefficient to _LEAGUE_COEFF")


def test_every_uefa_top_flight_has_a_coefficient():
    for lid in _uefa_top_flights():
        assert co.uefa_coeff(lid) is not None, f"{lid} has no UEFA coefficient"


def test_bridge_prior_never_reads_the_fitted_file(monkeypatch):
    """static_league_offset must ignore experiments/league_offsets.json.

    league_bridge ridges toward this value. If it followed league_offset() it
    would regularise each fit toward its own previous output, making the
    offsets a fixed point that no coefficient edit can move.

    This used to be asserted by requiring the prior and the file to DISAGREE,
    with norway-eliteserien named as a league that had moved. That inferred the
    mechanism from the values, and the inference is not sound: when a fit fails
    the robustness gate, league_bridge writes the PRIORS to the file, and the
    two agree everywhere for a completely correct reason. That is exactly what
    happened on 2026-08-06 once the UEFA match constants were calibrated — the
    priors beat the fit on held-out Brier, the gate adopted them, and this test
    failed on a repository that was behaving properly.

    So test the mechanism directly: feed the loader an answer that could only
    come from the file, and assert the prior path does not return it.
    """
    sentinel = -12345.0
    monkeypatch.setattr(co, "_load_fitted",
                        lambda: {lid: sentinel for lid in co._LEAGUE_COEFF})
    for lid in ("epl", "norway-eliteserien", "ligue-1", "eredivisie"):
        assert co.static_league_offset(lid) != sentinel, (
            f"static_league_offset({lid}) is reading the fitted file")
    # …and the fitted path must still be the one that does read it.
    assert co.league_offset("norway-eliteserien") == sentinel


def test_suspended_russia_is_labeled_and_decays():
    assert co.global_elo_quality("russia-premier") == "suspended_estimate"
    early, late = co._russia_coeff(2023), co._russia_coeff(2030)
    assert early > late, "estimate must decay while evidence is missing"
    assert late >= co._UEFA_UNLISTED_COEFF, "decay must floor at 'we don't know'"


def test_manual_override_outranks_the_fitted_file(monkeypatch):
    """_MANUAL_LEAGUE_OFFSET must win over experiments/league_offsets.json.

    The file used to win, on the reasoning that a real bridge-regression fit
    supersedes a hand-calibrated value. That stopped being true once
    league_bridge began writing the PRIORS to the same file whenever its
    robustness gate rejects a fit — an override was then shadowed by a copy of
    the prior it existed to correct.

    Observed 2026-08-07: the Eredivisie override was added, payloads and
    power.js were rebuilt, and PSV Eindhoven did not move. Nothing warned.
    """
    monkeypatch.setattr(co, "_MANUAL_LEAGUE_OFFSET", {"eredivisie": -206.0})
    monkeypatch.setattr(co, "_load_fitted", lambda: {"eredivisie": -155.1})
    assert co.league_offset("eredivisie") == pytest.approx(
        -206.0 + co.confederation_shift("eredivisie"))


def test_fitted_file_still_wins_for_leagues_without_an_override(monkeypatch):
    monkeypatch.setattr(co, "_MANUAL_LEAGUE_OFFSET", {})
    monkeypatch.setattr(co, "_load_fitted", lambda: {"primeira": -123.0})
    assert co.league_offset("primeira") == pytest.approx(
        -123.0 + co.confederation_shift("primeira"))
