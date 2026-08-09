"""Club display-name normalisation at the source boundary.

Deliberately dependency-free — stdlib only, and nothing at module scope beyond
this docstring. `scripts/fast_refresh.py` imports it on the `--select` path,
which runs on the runner's bare Python *before* `pip install -r
requirements.txt`; a pandas or requests import reachable from here would break
league selection in CI every 15 minutes, which is exactly what defect #8 did on
2026-08-08. `data_pipeline/__init__.py` is a docstring only, so importing this
module pulls in nothing else.

Why it exists: ESPN's `aus.w.1` feed returns 6 of 11 A-League Women clubs with
a trailing space in `displayName` ('Western Sydney ', 'Sydney FC ', …), and
every one of them reached the published payload untouched — in the standings
table and the fixtures alike.

That was harmless only by luck. `scripts.payload_utils.canonical_team_id`
already strips and casefolds before hashing, so club ids and the fixture ids
derived from them are whitespace-invariant, and no archived record is keyed on
the untrimmed form. Nothing needs migrating.

The exposure is forward. Any join, filter or lookup that matches on the
DISPLAY name rather than the id silently drops those clubs, and that is the
shape that came 2,114 rows from deleting a third of a league (spec
2026-08-09 §8.3, 'Liga Profesional ' vs 'Liga Profesional'). Normalising at
the boundary means a name is clean for every consumer, rather than for
whichever call site remembered to trim it.
"""
from __future__ import annotations


def clean_display_name(value) -> str:
    """Trim and collapse whitespace in a club's display name.

    Case and punctuation are preserved on purpose: this is the string the site
    renders, not a match key. The various `_norm` helpers around the codebase
    lowercase and strip punctuation to build lookup keys and are NOT
    interchangeable with this — using one where the other belongs is how a
    display name ends up lowercased on a public page.

    Idempotent, and safe on None (returns "").
    """
    return " ".join(str(value or "").split())
