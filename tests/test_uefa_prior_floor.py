"""Every modeled UEFA league must carry an informative prior.

The 2026-07-31 power-rankings bug: ten UEFA top flights were absent from
_LEAGUE_COEFF, so their prior was 0.0 — which on an EPL-anchored scale asserts
Premier League strength rather than absence of knowledge. The bridge's ridge
faithfully held them there, putting Bodo/Glimt 4th and Zenit 5th in the world.
"""
import json
from pathlib import Path

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


def test_bridge_prior_never_reads_the_fitted_file():
    """static_league_offset must ignore experiments/league_offsets.json.

    league_bridge ridges toward this value. If it followed league_offset() it
    would regularise each fit toward its own previous output, making the
    offsets a fixed point that no coefficient edit can move.
    """
    fitted = co._load_fitted() or {}
    moved = [lid for lid in fitted
             if abs(fitted[lid] - co.static_league_offset(lid)) > 1e-9]
    assert moved, "static prior is echoing the fitted file for every league"
    assert abs(co.static_league_offset("norway-eliteserien")
               - fitted.get("norway-eliteserien", 0.0)) > 1.0


def test_suspended_russia_is_labeled_and_decays():
    assert co.global_elo_quality("russia-premier") == "suspended_estimate"
    early, late = co._russia_coeff(2023), co._russia_coeff(2030)
    assert early > late, "estimate must decay while evidence is missing"
    assert late >= co._UEFA_UNLISTED_COEFF, "decay must floor at 'we don't know'"
