from pathlib import Path

from scripts.fetch_league_teams import REGISTRY
from scripts.validate_payloads import _NON_PAYLOAD

# Cross-league data-file stems ("drift", "model-slices", …) plus "power", which
# has its own POWER_DATA payload and no REGISTRY row. Derived from the single
# canonical exclusion set so a new cross-league file never silently breaks this.
_NON_LEAGUE_STEMS = {name.removesuffix(".js") for name in _NON_PAYLOAD} | {"power"}

# Must track webapp/index.html's GROUP_ORDER exactly — a group here with no
# sidebar entry there silently vanishes from the UI (found 2026-07-10 shipping
# the Tier-1 South America/Asia leagues).
_VALID_GROUPS = {"Americas", "South America", "Asia", "England", "Spain", "Italy",
                 "Germany", "France", "Other Europe", "Women", "Cups"}


def test_every_entry_has_a_valid_group():
    for lid, name, code, conf, status, group in REGISTRY:
        assert group in _VALID_GROUPS, f"{lid}: unknown group {group!r}"


def test_registry_matches_live_payloads_on_disk():
    """Every non-power .js payload under webapp/data/ should have a REGISTRY
    entry (B13 fix: ligue-2/segunda had drifted out of REGISTRY while their
    payloads and webapp/leagues.js still carried them, so regenerating the
    registry silently dropped two live leagues from the sidebar)."""
    data_dir = Path(__file__).parent.parent / "webapp" / "data"
    # excluded stems = cross-league data files, not league payloads (see _NON_LEAGUE_STEMS)
    on_disk = {p.stem for p in data_dir.glob("*.js")
               if p.stem not in _NON_LEAGUE_STEMS}
    registered = {lid for lid, *_ in REGISTRY}
    missing = on_disk - registered
    assert not missing, f"payloads on disk with no REGISTRY entry: {sorted(missing)}"
