from pathlib import Path

from scripts.fetch_league_teams import REGISTRY

_VALID_GROUPS = {"Americas", "England", "Spain", "Italy", "Germany", "France",
                 "Other Europe", "Cups"}


def test_every_entry_has_a_valid_group():
    for lid, name, code, conf, status, group in REGISTRY:
        assert group in _VALID_GROUPS, f"{lid}: unknown group {group!r}"


def test_registry_matches_live_payloads_on_disk():
    """Every non-power .js payload under webapp/data/ should have a REGISTRY
    entry (B13 fix: ligue-2/segunda had drifted out of REGISTRY while their
    payloads and webapp/leagues.js still carried them, so regenerating the
    registry silently dropped two live leagues from the sidebar)."""
    data_dir = Path(__file__).parent.parent / "webapp" / "data"
    on_disk = {p.stem for p in data_dir.glob("*.js")
               if p.stem not in ("logos", "ledger", "edge-board", "power", "movers")}
    registered = {lid for lid, *_ in REGISTRY}
    missing = on_disk - registered
    assert not missing, f"payloads on disk with no REGISTRY entry: {sorted(missing)}"
