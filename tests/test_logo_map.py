"""Tests for scripts/build_logo_map.py — crest resolution must not cross clubs.

The bug these guard against (found 2026-07-25): the resolver kept ONE flat
{normalized_name: url} index and matched into it by substring with only a
">= 4 characters" guard. Because norm() strips club-type tokens ("SC", "CD",
"FC", "Club"), and because the pool contains single-word short-name aliases
("United", "Sporting", "Atlético", "América", "Union", "Orlando"), 71 clubs
ended up wearing another club's crest — Barcelona SC (Ecuador) wore FC
Barcelona's, thirteen "… United" sides wore Carlisle United's, ten "Atlético
…" sides wore Atlético Madrid's.

Two rules fix it and both are asserted here:
  1. an ambiguous key (claimed by clubs in more than one country) never
     resolves through the global index;
  2. substring matching only accepts a multi-token index key.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOGOS = ROOT / "webapp" / "data" / "logos.js"

# Registry `country` values that name a competition region rather than a nation.
REGIONS = {"Europe", "North America", "South America"}

# Collisions the current data structure CANNOT fix. window.TEAM_LOGOS is keyed
# by team NAME, so two clubs whose names normalise identically can only ever
# hold one crest between them — no amount of resolver scoping helps, because
# the collision happens in the output map, not in the lookup.
#
#   Liverpool (Uruguay)      vs Liverpool (England)      — identical
#   Santos (Mexico)          vs Santos (Brazil)          — identical
#   Platense (Honduras)      vs Platense (Argentina)     — identical
#   Alianza FC (Colombia)    vs Alianza FC (El Salvador) — identical
#   Athletic (Brazil)        vs Athletic Club (Spain)    — identical after norm()
#   Aurora (Bolivia)         vs Aurora FC (Guatemala)    — identical after norm()
#   Nacional (Uruguay)       vs C.D. Nacional (Portugal) — identical after norm()
#   Atlanta (Argentina)      vs Atlanta United (USA)
#   San Antonio Bulo Bulo (Bolivia) vs San Antonio FC (USA)
#   AFC Toronto (Canada)     vs Toronto FC (USA)
#
# The real fix is to key the map by (league_id, name) — or by the team_id the
# payloads already carry — and have the webapp look up with its own league in
# hand. That is a schema change across build_logo_map.py and every consumer,
# so it is tracked separately rather than bolted on here.
KNOWN_NAME_CLASHES = {
    "364.png", "2674.png", "7764.png", "7225.png", "93.png",
    "131213.png", "3472.png", "18418.png", "18265.png", "7318.png",
}


def _load(path: Path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^[\s\S]*?=\s*", "", text).rstrip().rstrip(";")
    return json.loads(text)


@pytest.fixture(scope="module")
def logos() -> dict[str, str]:
    if not LOGOS.exists():
        pytest.skip("webapp/data/logos.js not built")
    return _load(LOGOS)


# Each pair is (club, club-whose-crest-it-must-not-wear). Every one of these
# was a real mis-render before the scoped resolver landed.
COLLISIONS = [
    ("Barcelona SC", "Barcelona"),              # Ecuador vs Spain
    ("Everton CD", "Everton"),                  # Chile vs England
    ("Bangkok United", "Carlisle United"),      # Thailand vs England
    ("Buriram United", "Carlisle United"),
    ("Chippa United", "Carlisle United"),       # South Africa
    ("Canberra United", "Carlisle United"),     # Australia
    ("Atlético Junior", "Atletico Madrid"),     # Colombia vs Spain
    ("Atlético Goianiense", "Atletico Madrid"),  # Brazil
    ("Club Atlético Morelia", "Atletico Madrid"),  # Mexico
    ("Sporting Cristal", "Sporting CP"),        # Peru vs Portugal
    ("Defensor Sporting", "Sporting CP"),       # Uruguay
    ("América de Cali", "América"),             # Colombia vs Mexico
    ("Orlando Pirates", "Orlando City SC"),     # South Africa vs USA
    ("Union Omaha", "Philadelphia Union"),      # USL vs MLS
    ("Unión La Calera", "Philadelphia Union"),  # Chile vs MLS
    ("Boston River", "Boston Legacy FC"),       # Uruguay vs USA
    ("Inter Turku", "Inter Milan"),             # Finland vs Italy
    ("Athletic Club Boise", "Athletic Club"),   # USL vs Spain
]


@pytest.mark.parametrize("club,other", COLLISIONS)
def test_club_does_not_wear_another_clubs_crest(logos, club, other):
    """A same-name club in a different country must not inherit the crest."""
    other_url = logos.get(other)
    if other_url is None:
        pytest.skip(f"{other} absent from the map — nothing to collide with")
    assert logos.get(club) != other_url, (
        f"{club!r} resolved to {other!r}'s crest ({other_url}). "
        "The resolver must scope by country/confederation and refuse "
        "ambiguous global keys."
    )


def test_big_clubs_still_resolve(logos):
    """The scoping must not cost the unambiguous cases their own crests."""
    for name in ("Barcelona", "Atletico Madrid", "Inter Milan", "PSG",
                 "Athletic Club", "Sporting CP"):
        assert logos.get(name), f"{name} lost its own crest"


def test_no_crest_is_worn_by_a_crowd(logos):
    """A crest worn by many names is the signature of the old substring bug.

    Legitimate sharing is a single club's alias cluster — "Sheffield Wed" /
    "Sheffield Wednesday" / "Owls", or "Portland" / "Portland Timbers" /
    "Timbers". Those top out around four. The bug produced thirteen names on
    Carlisle United's crest and ten on Atlético Madrid's, so a threshold
    cleanly separates the two regimes without needing to model nicknames.
    """
    by_url: dict[str, list[str]] = {}
    for name, url in logos.items():
        by_url.setdefault(url, []).append(name)
    crowded = {u.rsplit("/", 1)[-1]: sorted(n)
               for u, n in by_url.items() if len(n) > 5}
    assert not crowded, (
        "crest worn by more than five names — likely a fuzzy-match leak:\n" +
        "\n".join(f"  {u}: {n}" for u, n in crowded.items())
    )


def test_countries_do_not_share_a_crest(logos):
    """Two clubs from different countries must never resolve to one crest.

    This is the invariant the whole scoped resolver exists to hold. Aliases in
    ALIAS are deliberate same-club mappings and are checked by name, not
    country, so the test reads the registry to locate each name's league.
    """
    payloads = {}
    for p in sorted((ROOT / "webapp" / "data").glob("*.js")):
        if p.name in ("logos.js",):
            continue
        try:
            d = _load(p)
        except Exception:
            continue
        if isinstance(d, dict):
            payloads[p.stem] = d

    registry = {r["id"]: r for r in _load(ROOT / "webapp" / "leagues.js")}
    # name -> countries it plays in, taking each continental row's domestic
    # league tag when present (that is what separates Barcelona SC from Barça).
    where: dict[str, set[str]] = {}
    for lid, d in payloads.items():
        for row in (d.get("standings") or []) + (d.get("field") or []):
            name = row.get("team")
            if not name:
                continue
            meta = registry.get(row.get("league")) or registry.get(lid) or {}
            country = meta.get("country")
            # Continental competitions carry a REGION in `country` ("Europe",
            # "North America"). A UCL row is not evidence of a second country,
            # so those never contribute — only the domestic-league tag does.
            if country and country not in REGIONS:
                where.setdefault(name, set()).add(country)

    by_url: dict[str, set[str]] = {}
    for name, url in logos.items():
        by_url.setdefault(url, set()).update(where.get(name, set()))
    offenders = {u.rsplit("/", 1)[-1]: sorted(c)
                 for u, c in by_url.items() if len(c) > 1}
    new = {u: c for u, c in offenders.items() if u not in KNOWN_NAME_CLASHES}
    assert not new, (
        "NEW cross-country crest collision (the scoped resolver should have "
        "prevented this):\n" +
        "\n".join(f"  {u}: {c}" for u, c in new.items())
    )
    # Guard the other direction too: if a known clash gets fixed, shrink the
    # list rather than letting it rot.
    stale = set(KNOWN_NAME_CLASHES) - set(offenders)
    assert not stale, f"KNOWN_NAME_CLASHES entries no longer collide: {sorted(stale)}"
