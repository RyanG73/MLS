"""Coverage for the stale-figure grep in scripts/check_docs.py.

`check_docs.py` is what makes CLAUDE.md's fact rules executable, and until 2026-08-15 it had no
tests of its own — the guard enforcing "rules nothing checks are the ones that rot" was itself
unchecked. It had gone wrong in the way an unchecked guard does: `\\b748\\b` matched the `0.748`
calibration bin in postgame-win-expectancy.md and `\\b750\\b` matched "~1,750 tests" in the active
plan, so `check_docs` reported two failures that **no edit to either document could fix** — the
digits are correct where they stand. A checker that cries wolf gets ignored, which costs more
than the drift it was written to catch.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import check_docs


def _fake_rg(monkeypatch, lines: list[str]):
    """Feed _grep_stale a canned `rg -n` result so the filtering is tested, not the repo."""
    monkeypatch.setattr(
        check_docs.subprocess, "run",
        lambda *a, **k: SimpleNamespace(stdout="\n".join(lines)),
    )


@pytest.mark.parametrize("line, value", [
    # The two real false positives that motivated the fix.
    ("docs/postgame-win-expectancy.md:110:| 0.7–0.8 | 3,920 | 0.748 | 0.742 | 0.007 |", "748"),
    ("docs/plan.md:168:a run that reports ~1,750 tests rather than ~1,830 did not", "750"),
    # Same shape, other directions: leading digit, trailing digit, trailing decimal.
    ("docs/x.md:1:the ladder held 1965 entries", "965"),
    ("docs/x.md:2:latency was 9584ms at peak", "958"),
    ("docs/x.md:3:calibration error 0.9655 on the fold", "965"),
])
def test_a_figure_inside_a_larger_number_is_not_a_stale_figure(monkeypatch, line, value):
    _fake_rg(monkeypatch, [line])
    assert check_docs._grep_stale(value) == [], (
        f"{value!r} is embedded in a larger number here; reporting it asks for an edit that "
        "would make the document wrong"
    )


@pytest.mark.parametrize("text, value", [
    ("the live payload serves 958 clubs / 55 leagues", "958"),
    ("Global ELO runs 697–1,797 today", "697"),
    ("965 clubs across 55 leagues", "965"),
])
def test_a_standalone_stale_figure_is_still_reported(monkeypatch, text, value):
    """The guard must stay sharp — this is the drift it exists to catch."""
    _fake_rg(monkeypatch, [f"docs/STATUS.md:42:{text}"])
    assert check_docs._grep_stale(value) == ["docs/STATUS.md:42"]


def test_research_log_may_record_the_values_it_retired(monkeypatch):
    """docs/research-log.md is the append-only record of past measurements.

    Every entry is stamped and describes the transition that retired a value, so grepping it for
    stale figures reports the log's entire purpose as drift.
    """
    _fake_rg(monkeypatch, [
        "docs/research-log.md:324:Global ELO range moved 770–1770 → 697–1797",
        "docs/STATUS.md:78:Global ELO runs 697–1,797",
    ])
    assert check_docs._grep_stale("697") == ["docs/STATUS.md:78"], (
        "the exemption must cover research-log.md only — STATUS.md is current truth"
    )


def test_a_line_documenting_the_correction_may_name_the_old_value(monkeypatch):
    """The pre-existing escape hatch: prose explaining a correction has to quote what changed."""
    _fake_rg(monkeypatch, [
        "docs/STATUS.md:50:the 2026-08-07 copy was 958 clubs, and the payload now serves 959",
        "docs/STATUS.md:51:previously 958 clubs",
        "docs/STATUS.md:52:this stale 958 clubs figure",
    ])
    assert check_docs._grep_stale("958") == []


def test_malformed_grep_output_is_dropped_rather_than_crashing(monkeypatch):
    """rg emits binary-file and context markers that carry no `path:line:text` triple."""
    _fake_rg(monkeypatch, ["", "docs/STATUS.md", "Binary file docs/logo1.PNG matches"])
    assert check_docs._grep_stale("958") == []
