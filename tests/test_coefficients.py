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


def test_concacaf_offsets_are_relative_not_uefa_scale():
    assert co.league_offset("mls") == 0.0
    assert co.league_offset("liga-mx") > co.league_offset("mls")
    assert co.league_offset("liga-mx") <= 60  # modest, not a UEFA-sized gap


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
