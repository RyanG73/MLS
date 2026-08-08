"""Guards against leagues stranded on a dead final table.

Status is a FIXTURE-FEED decision, not a calendar one: a league parks on
"completed" from its last match until its source publishes the next schedule
(`scripts/eval/season_state.py`). Nothing watched that gap, so on 2026-07-26
twenty-four leagues were showing a final table 45+ days old and nine of them had
next-season fixtures already public.

Root cause: `build_league_data` had a pre-season flip for `understat`,
`footballdata`, `footballdata_intl`, `asa` and `api_football` sources but NOT for
`espn` — 30 of the 78 leagues, the largest source group. `ts` derives from
max_played_season, so those leagues waited for ESPN to report RESULTS rather than
a schedule. The `footballdata_intl` path had the same hole for a different
reason: it only ever asked ESPN for the CURRENT season.

Both now roll forward, guarded on the current season having nothing left to
play — the condition that stops a league which publishes fixtures months ahead
(the J-League) from ending its season early.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "webapp" / "data"

# Leagues whose SOURCE genuinely cannot supply a newer season. These are data
# problems, not build problems, and must stay listed (with the reason) rather
# than quietly widening the tolerance for everyone else.
SOURCE_BLOCKED = {
    # canadian-pl and k-league-1 were blocked by the API-Football FREE plan's
    # 2024 season cap. The paid plan (2026-08-08) removed it — CPL's rebuilt
    # payload runs to 2026-10-25 — and this file's own accuracy test is what
    # flagged the stale entries. Removed rather than kept "just in case": the
    # list is for sources that genuinely cannot supply a newer season.
    # Poland remains results-only, but its results source now supplies the
    # current 2026 season, so it is no longer blocked on season rollover.
    # finland-veikkausliiga is deliberately NOT here: it has no ESPN slug either,
    # but FIXTURE_OVERRIDE supplies its schedule from API-Football and it tracks
    # the current season fine. It was listed on first draft and this file's own
    # accuracy test rejected it.
}


def _payloads():
    out = {}
    for p in sorted(DATA.glob("*.js")):
        try:
            m = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$", p.read_text(encoding="utf-8"), re.DOTALL)
            d = json.loads(m.group(1)) if m else None
        except Exception:
            continue
        if isinstance(d, dict) and "status" in d:
            out[p.stem] = d
    return out


@pytest.fixture(scope="module")
def payloads():
    d = _payloads()
    if not d:
        pytest.skip("no payloads built")
    return d


def test_no_league_shows_a_season_two_years_stale(payloads):
    """A table from two seasons ago is never defensible on a live site."""
    this_year = date.today().year
    bad = []
    for lid, d in payloads.items():
        if lid in SOURCE_BLOCKED:
            continue
        season = d.get("season")
        if not isinstance(season, int) or season < 100:
            continue          # Liga MX uses sequential torneo ids, not years
        if season <= this_year - 2:
            bad.append(f"{lid}: showing season {season} in {this_year} "
                       f"(status={d.get('status')})")
    assert not bad, "leagues stranded on an old season:\n  " + "\n  ".join(bad)


def test_preseason_leagues_actually_have_fixtures(payloads):
    """A 'preseason' payload with nothing to simulate is worse than 'completed'."""
    bad = []
    for lid, d in payloads.items():
        if d.get("status") != "preseason":
            continue
        games = d.get("games") or []
        scheduled = [g for g in games if g.get("result") is None]
        if not scheduled:
            bad.append(f"{lid}: status=preseason but 0 scheduled fixtures")
    assert not bad, "\n  ".join(bad)


def test_completed_leagues_have_no_scheduled_fixtures_left(payloads):
    """The definition of 'completed' — anything else means the flip misfired."""
    bad = []
    for lid, d in payloads.items():
        if d.get("status") != "completed":
            continue
        scheduled = [g for g in (d.get("games") or []) if g.get("result") is None]
        if scheduled:
            bad.append(f"{lid}: status=completed but {len(scheduled)} fixtures unplayed")
    assert not bad, "\n  ".join(bad)


def test_source_blocked_list_is_still_accurate(payloads):
    """If a blocked league starts producing a current season, drop it from the list."""
    this_year = date.today().year
    stale_entries = []
    for lid in SOURCE_BLOCKED:
        d = payloads.get(lid)
        if not d:
            continue
        season = d.get("season")
        if isinstance(season, int) and 100 < season and season >= this_year:
            stale_entries.append(f"{lid} now has season {season} — remove from SOURCE_BLOCKED")
    assert not stale_entries, "\n  ".join(stale_entries)
