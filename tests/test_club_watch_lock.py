"""The club-page Club Watch teaser must tease without lying or over-locking.

Two failure modes this guards, both hit while building it on 2026-08-01:

1. Fabricated figures behind the blur. A blurred "+6.1" is still the string
   "+6.1" in the DOM, sitting where the real locked answer belongs — visible to
   anyone with devtools and impossible to stand behind. Blurred content must be
   prose describing what is locked, never a number claiming to be it.

2. Locking something already free. Next 5 Sim computes what a result does to the
   season target, free, in the table on the same page. Locking that would break
   the durable rule in CLAUDE.md: lock the continuity, never the current answer.
"""
import re
from pathlib import Path

SHELL = (Path(__file__).resolve().parents[1] / "webapp" / "index.html").read_text()


def _lock_block() -> str:
    start = SHELL.index("function clubWatchLock(")
    end = SHELL.index("function renderProfile(", start)
    return SHELL[start:end]


def test_blurred_values_are_never_bare_figures():
    block = _lock_block()
    for value in re.findall(r"\$\{blur\('([^']*)'\)\}", block):
        assert not re.fullmatch(r"[+\-]?[\d.,%pp ]+", value.strip()), (
            f"blur() carries a bare figure {value!r} — blurred content must "
            "describe what is locked, not assert a number nobody can verify")


def test_blurred_values_are_hidden_from_screen_readers():
    assert 'class="cw-blur" aria-hidden="true"' in _lock_block(), (
        "blurred placeholders must not be announced as real content")


def test_next_five_sim_is_named_as_free():
    """The teaser must point at the free tool that already answers this."""
    block = _lock_block()
    assert "Next 5 Sim" in block
    assert "free" in block.lower()


def test_teaser_states_the_free_forever_promise():
    assert "stays free, forever" in _lock_block(), (
        "every lock has to restate the promise, or it reads as bait")


def test_club_page_still_renders_the_free_panels():
    """The locks are ADDED to the club page — nothing free may be displaced."""
    start = SHELL.index("function renderProfile(")
    body = SHELL[start:start + 4000]
    for panel in ("outlookCard", "trajCardHTML(team)", "team-news", "seasonFixturesHTML"):
        assert panel in body, f"{panel} disappeared from the club page"
    assert "clubWatchLock(team,s,gms)" in body
