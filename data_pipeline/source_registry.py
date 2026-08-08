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

from typing import Callable

import pandas as pd

# league_id → {family: [source, ...]} in priority order. Deliberately empty at
# Stage 0; Tier A migration (Stage 3) adds entries batch by batch.
REGISTRY: dict[str, dict[str, list[str]]] = {}


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
