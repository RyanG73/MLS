"""Per-league, per-capability source routing with ordered fallback.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md
(§6.1 registry, §6.2 provenance). Today each league carries one `source` string
— all-or-nothing. This module replaces that with an ordered list per *column
family* (fixtures, xg, odds, statistics, …), so a league can draw each family
from whichever source is best for it and fall back when a source goes dark.

Two deliberate properties:

- **Empty by default.** A league with no REGISTRY entry resolves to exactly its
  existing `source` string, so nothing changes for any league until a second
  source is explicitly added (that is Stage 3, per migration batch — not here).
- **No silent fallback.** Every failed attempt is recorded in source_health
  before the next source is tried, and the winning source is returned to the
  caller so the payload can publish its provenance. Two leagues disagreeing
  must be explainable; a fallback must be distinguishable from a healthy build.

Stage-3 caveat, documented rather than hidden: parts of build_league_data still
branch on `cfg["source"]` for name-mapping and season quirks. Until a league's
branches are audited, a *fallback* answer may not flow through those branches
correctly — which is exactly why migration happens per league with a rollback,
not by flipping the default.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

# pandas is NOT imported at module scope. fast_refresh's `--select` step runs
# on the runner's bare Python before `pip install -r requirements.txt` (see
# refresh-fast.yml and the deferred-import comments in scripts/fast_refresh.py),
# and select_leagues reaches this module through uses_spine. A module-scope
# pandas import here therefore breaks league selection in CI with
# ModuleNotFoundError — which it did, every 15 minutes, on 2026-08-08. Nothing
# below needs pandas at runtime: the annotations are deferred by
# `from __future__ import annotations`, and `frame.empty` is duck-typed.
if TYPE_CHECKING:                                   # pragma: no cover
    import pandas as pd

# league_id → {family: [source, ...]} in priority order. Empty at Stage 0;
# Tier A migration (Stage 3) adds entries batch by batch, each backed by a
# full-season diff at 100% scoreline agreement before it lands here.
REGISTRY: dict[str, dict[str, list[str]]] = {
    # ── Stage 3, batch 1 (2026-08-08) ────────────────────────────────────────
    # Validated: every shared-season fixture matched, 100% scoreline
    # agreement, standings identical (see the spec's Stage-3 record).
    # ESPN stays as ordered fallback; a spine failure is recorded in
    # source_health and the build falls back rather than failing.
    # NSL: spine adds 2026 in-progress coverage ESPN 403'd on during
    # validation. USL Super League: spine adds the 2024 inaugural season
    # ESPN never had — a history GAIN.
    "northern-super-league": {"fixtures": ["api_football", "espn"]},
    "usl-super-league":      {"fixtures": ["api_football", "espn"]},
    # ── MLS (2026-08-09, spec §3.1) ──────────────────────────────────────────
    # ESPN stays FIRST here, deliberately, and this is the one entry that is
    # not a migration. MLS results come from ASA and its schedule from ESPN;
    # `build (mls)` has been red since ~2026-08-06 because a 403 on
    # usa.1/scoreboard is fatal with no second source. This entry adds the
    # fallback without moving the primary, so a healthy build is byte-identical
    # to today's payload while a dark ESPN degrades instead of failing.
    # It is NOT a Stage-3 migration: making api_football primary requires the
    # 100%-agreement diff and the generated name map that §3.2 mandates, and
    # config/api_football_team_names.json has no "mls" entry yet — until it
    # does, the fallback's own name-coverage guard fails it closed.
    "mls":                   {"fixtures": ["espn", "api_football"]},
    # costa-rica-primera: HELD on ESPN-first (2026-08-08) — spine history
    # starts 2016 vs ESPN's 2015 (invariant 3: no history loss), and 4 of 110
    # matched fixtures disagreed on scorelines, unadjudicated. Revisit with a
    # name-mapped full diff before any flip.
}


def sources_for(league_id: str, family: str, default: str) -> list[str]:
    """Ordered source names for one league's column family. Without a REGISTRY
    entry this is exactly [default] — today's behavior, untouched."""
    return list(REGISTRY.get(league_id, {}).get(family) or [default])


def resolve(league_id: str, family: str,
            loaders: dict[str, Callable[[], pd.DataFrame]],
            default: str) -> tuple[pd.DataFrame, str]:
    """Try each source in order; return (frame, source_that_answered).

    A loader that raises, is missing, or returns an empty frame counts as a
    failure: it is recorded in source_health and the next source is tried.
    When every source fails, raises with all of them named — the caller gets
    one error that explains the whole chain, not just the last link.
    """
    from data_pipeline.source_health import record_fetch
    errors: list[str] = []
    for src in sources_for(league_id, family, default):
        loader = loaders.get(src)
        if loader is None:
            errors.append(f"{src}: no loader wired")
            record_fetch(src, f"router:{league_id}:{family}", ok=False,
                         error="no loader wired")
            continue
        try:
            frame = loader()
        except Exception as exc:  # noqa: BLE001 — recorded, then next source
            errors.append(f"{src}: {exc}")
            record_fetch(src, f"router:{league_id}:{family}", ok=False,
                         error=str(exc))
            continue
        if frame is None or frame.empty:
            errors.append(f"{src}: empty frame")
            record_fetch(src, f"router:{league_id}:{family}", ok=False,
                         error="empty frame")
            continue
        return frame, src
    raise RuntimeError(
        f"every source failed for {league_id}/{family}: " + "; ".join(errors))
