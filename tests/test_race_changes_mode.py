"""Contract tests for the race panel's "Changes since" diff mode (P5).

The diff renders DRIFT_TRAJ, which merges point-in-time *reconstructed* replays
with *archived* forecasts that were genuinely published. A diff whose endpoints
straddle that boundary is partly an artifact of re-running the model, and
`docs/paid-claim-matrix.md` forbids calling a reconstruction an originally
published forecast. These lock the honesty rules in the shell source, the same
way tests/test_club_watch_lock.py locks the Club Watch teaser.

Behaviour was additionally verified in a browser on 2026-08-01: EPL 7-day window
reported archived provenance; MLS since=2026-03-01 reported mixed provenance with
a REPLAY flag on all 12 rows; Bundesliga 2026-07-30 -> 2026-07-31 produced the
empty state; round-trip back to the trajectory cleared both URL params.
"""
from __future__ import annotations

import re
from pathlib import Path

SHELL = (Path(__file__).resolve().parents[1] / "webapp" / "index.html").read_text()


def test_diff_mode_exists_and_is_url_addressable():
    """Shareable and indexable, per the design: state lives in the URL."""
    assert "function renderRaceChanges(" in SHELL
    assert "mode','changes'" in SHELL or "mode\")==='changes'" in SHELL
    assert "searchParams.set('mode','changes')" in SHELL
    assert "searchParams.set('since'" in SHELL


def test_all_three_provenance_notes_are_present_and_distinct():
    block = SHELL[SHELL.index("RACE_PROVENANCE_NOTE"):]
    block = block[:block.index("function renderRaceChanges")]
    for key in ("archived:", "reconstructed:", "mixed:"):
        assert key in block, f"missing provenance case {key}"
    # The three must say different things — a shared string would defeat them.
    notes = re.findall(r"'([^']{40,})'", block)
    assert len(set(notes)) >= 3, notes


def test_mixed_provenance_discloses_the_boundary_in_words():
    """Styling alone is not disclosure. The claim matrix requires words."""
    block = SHELL[SHELL.index("RACE_PROVENANCE_NOTE"):]
    block = block[:block.index("function renderRaceChanges")]
    mixed = block[block.index("mixed:"):]
    for phrase in ("reconstructed replay", "not a forecast published",
                   "re-running the model"):
        assert phrase in mixed, f"mixed-provenance note must say {phrase!r}"


def test_reconstructed_endpoints_are_flagged_per_row():
    assert "rc-flag" in SHELL
    assert "reconstructed replay" in SHELL


def test_empty_window_reads_as_nothing_moved_not_as_an_error():
    """Preseason and quiet weeks are the normal case, not a failure."""
    assert "Nothing moved." in SHELL
    # Scope to the empty branch itself. A wider window catches unrelated
    # identifiers — "NaN" lives inside "raceProvenance".
    branch = SHELL[SHELL.index("if(!moved.length){"):]
    branch = branch[:branch.index("raceBindChanges")]
    # Strip // comments — the surrounding comment explains that this state is
    # *not* an error, and scanning it would match its own explanation.
    copy = "\n".join(line.split("//")[0] for line in branch.splitlines())
    assert "Nothing moved." in copy
    for banned in ("error", "failed", "unavailable", "NaN", "0.0%"):
        assert not re.search(rf"\b{re.escape(banned)}\b", copy, re.I), (
            f"empty state must not read as {banned!r}")


def test_baseline_never_interpolates():
    """A date the model did not publish on is answered with the last one it
    did. Interpolating would invent a forecast that never existed."""
    fn = SHELL[SHELL.index("function raceAtOrBefore"):]
    fn = fn[:fn.index("function raceDefaultSince")]
    assert "r.date<=date" in fn
    assert "interpolat" not in fn.lower()


def test_diff_mode_is_not_paywalled():
    """The free-floor ratchet: current public trajectories stay free, and this
    mode is a view over exactly that data."""
    fn = SHELL[SHELL.index("function renderRaceChanges"):]
    fn = fn[:fn.index("function raceBindChanges")]
    for gate in ("entitlement", "isPaid", "clubWatchLock", "locked"):
        assert gate not in fn, f"diff mode must not gate on {gate!r}"
