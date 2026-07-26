import pytest
from data_pipeline import coefficients as co


def test_reference_league_has_zero_offset():
    # The strongest modeled league (EPL) anchors the scale at 0.
    assert co.league_offset("epl") == 0.0


def test_weaker_league_has_negative_offset():
    # A weaker league sits below EPL on the common scale.
    assert co.league_offset("ligue-1") < 0.0


def test_unknown_league_offset_is_zero_with_no_crash():
    # Graceful fallback: an unmapped league contributes no offset.
    assert co.league_offset("nonexistent-league") == 0.0


def test_club_strength_maps_coefficient_to_elo_scale():
    # A top club coefficient maps to a strength near a strong domestic ELO.
    assert co.club_strength("Real Madrid") == 1720.0


def test_unknown_club_strength_returns_baseline():
    # Unknown club -> conservative baseline, never a crash.
    assert co.club_strength("FC Nonexistent") == co.BASELINE_STRENGTH


def test_concacaf_internal_gap_survives_the_confederation_shift():
    """Liga MX keeps its modest edge over MLS on the new one-ladder scale.

    Rewritten 2026-07-26. This test used to assert `league_offset("mls") == 0.0`
    — i.e. that Concacaf sat on its OWN scale, uncomparable to UEFA's. That was
    the limitation, not the contract: MLS and EPL both reading 0.0 never meant
    they were equal, it meant no match had ever connected them. A whole-scale
    confederation shift now places them on one ladder
    (scripts/eval/interconf_calibrate.py).

    What must still hold is the part that was actually calibrated: the gap
    BETWEEN Concacaf leagues is unchanged, because a constant added to every
    league in a confederation cancels in any within-confederation comparison.
    """
    gap = co.league_offset("liga-mx") - co.league_offset("mls")
    assert gap > 0, "Liga MX should still rate above MLS"
    assert gap <= 60, "the internal gap should stay modest, not UEFA-sized"


def test_concacaf_now_sits_below_uefa_on_one_ladder():
    """The point of the shift: cross-confederation offsets are comparable."""
    assert co.league_offset("mls") < co.league_offset("epl")
    assert co.league_offset("liga-mx") < co.league_offset("epl")
    # CONMEBOL's champions are closer to UEFA than Concacaf's — the ordering the
    # Club World Cup data produced, and the one conventional wisdom expects.
    assert co.league_offset("brazil-serie-a") > co.league_offset("mls")


def test_confederation_shift_is_zero_for_the_anchor_and_unknowns():
    assert co.confederation_shift("epl") == 0.0
    assert co.confederation_shift("not-a-league") == 0.0


def test_concacaf_club_strength_below_modeled_top():
    # An unmodeled Central-American club sits well below the MLS/Liga MX modeled range.
    assert co.club_strength("Alajuelense") < 1550


# ── tier2_offset ──────────────────────────────────────────────────────────────

def test_tier2_offset_unknown_league_returns_zero():
    """Unsupported league pair returns 0.0, no crash."""
    from data_pipeline import coefficients as co
    assert co.tier2_offset("unknown-league") == 0.0


def test_tier2_offset_returns_static_prior_when_json_absent(tmp_path, monkeypatch):
    """Falls back to static prior when experiments/tier2_offsets.json is absent."""
    import data_pipeline.coefficients as co
    monkeypatch.setattr(co, "_TIER2_JSON", tmp_path / "nonexistent.json")
    monkeypatch.setattr(co, "_TIER2_OFFSETS_LOADED", False)
    monkeypatch.setattr(co, "_TIER2_OFFSETS", None)
    result = co.tier2_offset("championship")
    assert result == co._TIER2_PRIORS["championship_to_epl"]


def test_tier2_offset_reads_fitted_value_from_json(tmp_path, monkeypatch):
    """Returns the fitted offset from JSON when present, not the prior."""
    import json
    import data_pipeline.coefficients as co
    fitted = {"championship_to_epl": -95.5, "bundesliga-2_to_bundesliga": -80.0,
              "serie-b_to_serie-a": -110.0}
    json_path = tmp_path / "tier2_offsets.json"
    json_path.write_text(json.dumps(fitted))
    monkeypatch.setattr(co, "_TIER2_JSON", json_path)
    monkeypatch.setattr(co, "_TIER2_OFFSETS_LOADED", False)
    monkeypatch.setattr(co, "_TIER2_OFFSETS", None)
    assert co.tier2_offset("championship") == -95.5
    assert co.tier2_offset("bundesliga-2") == -80.0


def test_tier1_offset_is_positive_for_relegated_seeding():
    # A team relegated INTO the second tier seeds ABOVE the second-tier field.
    assert co.tier1_offset("championship") > 0
    assert co.tier1_offset("segunda") > 0
    assert co.tier1_offset("nonexistent") == 0.0


# ── UEFA-spots page builder (I1, 2026-07-09) ─────────────────────────────────

def test_coefficients_page_covers_all_modeled_uefa_leagues():
    from scripts.build_coefficients_page import build
    from scripts.build_league_data import OUTLOOK
    data = build()
    got = {r["league_id"] for r in data["associations"]}
    want = {lid for lid, cfg in OUTLOOK.items()
            if any(b["key"] == "ucl" for b in cfg["buckets"])}
    assert want <= got, f"missing: {want - got}"
    # ranks are 1..n by coefficient, descending
    coeffs = [r["coeff"] for r in sorted(data["associations"], key=lambda r: r["rank"])]
    assert coeffs == sorted(coeffs, reverse=True)
    # EPS holders show the extra UCL spot the sim uses (5 vs base 4)
    by_id = {r["league_id"]: r for r in data["associations"]}
    assert by_id["epl"]["eps"] and by_id["epl"]["ucl"] == 5
    assert by_id["la-liga"]["ucl"] == 4
