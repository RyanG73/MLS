"""Resolve a continental ESPN club to (modeled league id, domestic frame key).

Extracted so both sides can use it without an import cycle: `league_bridge`
(calibration) already imports `build_continental_data`, so the production build
cannot import `league_bridge` back. Neither module owns the resolver; this one does.

Why ids and not names — names are NOT sufficient in CONMEBOL. Across the 12
modeled South American leagues, 45 of 408 normalized club names collide. Most
are the same club either side of a promotion, but four are genuinely different
clubs sharing a name, and they meet in these very competitions:

    River Plate  Argentina  vs  Uruguay
    Guaraní      Paraguay   vs  Brazil (Série B)
    Portuguesa   Brazil     vs  Venezuela
    Llaneros     Colombia   vs  Venezuela

Resolving River Plate to the wrong country hands a continental heavyweight a
minor side's rating. ESPN team ids are shared between the continental feed and
each league's /teams endpoint, so they settle club identity exactly.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

_log = logging.getLogger(__name__)

_ROSTER_JSON = Path("data/espn_continental/league_rosters.json")
_ROSTERS: dict[str, dict[str, str]] | None = None
_NAME_INDEX: dict[str, dict[str, str]] = {}


def league_rosters(refresh: bool = False) -> dict[str, dict[str, str]]:
    """{league_id: {espn_team_id: displayName}} for every league with an ESPN slug.

    Cached to disk. ESPN's per-league /teams endpoint only returns the CURRENT
    season's members, which is enough to pin a club to a COUNTRY — the thing the
    four genuine name collisions need. Tier moves are handled by the caller.
    """
    global _ROSTERS
    if _ROSTERS is not None and not refresh:
        return _ROSTERS
    if _ROSTER_JSON.exists() and not refresh:
        _ROSTERS = json.loads(_ROSTER_JSON.read_text())
        return _ROSTERS

    from data_pipeline.espn_fixtures import SLUGS
    from data_pipeline.http import espn_get
    out: dict[str, dict[str, str]] = {}
    for lid, slug in SLUGS.items():
        try:
            payload = espn_get(
                f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/teams", {})
            teams = payload["sports"][0]["leagues"][0]["teams"]
            out[lid] = {str(t["team"]["id"]): t["team"].get("displayName", "")
                        for t in teams}
        except Exception as e:  # noqa: BLE001
            _log.warning("league_rosters: %s (%s) failed: %s", lid, slug, e)
    _ROSTER_JSON.parent.mkdir(parents=True, exist_ok=True)
    _ROSTER_JSON.write_text(json.dumps(out, indent=2, sort_keys=True))
    _ROSTERS = out
    return out


def norm_team(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = re.sub(r"\b(fc|cf|sk|afc|ac|sc|1\.)\b", "", s, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def team_name_index(league_id: str) -> dict[str, str]:
    """{normalized_name: frame_key} for a modeled league's domestic frame."""
    if league_id not in _NAME_INDEX:
        from scripts.build_league_data import OUTLOOK, _load_frame
        cfg = OUTLOOK.get(league_id, {})
        frame = _load_frame(league_id, cfg.get("source", "espn"), cfg.get("asa_key"))
        names = set(frame["home_team"]) | set(frame["away_team"])
        _NAME_INDEX[league_id] = {norm_team(t): t for t in names if isinstance(t, str)}
    return _NAME_INDEX[league_id]


def match_name_in_league(espn_name: str, league_id: str) -> str | None:
    """Frame key for `espn_name` within ONE league, or None.

    Scoped to a single league on purpose: once the league is pinned by ESPN id,
    the loose substring/fuzzy tiers cannot cross-match two different clubs, so
    they can safely absorb source-name drift.
    """
    idx = team_name_index(league_id)
    key = norm_team(espn_name)
    if not key:
        return None
    # Tier 0 — the production ESPN→source name maps. footballdata / _intl leagues
    # key their frames on the SOURCE's names: ESPN "Estudiantes de La Plata" vs
    # football-data "Estudiantes L.P." share no substring and fall under the fuzzy
    # cutoff, while a looser cutoff would grab "Estudiantes Rio Cuarto" — a
    # different club in the same league.
    from scripts.build_league_data import FDI_ESPN, FD_ESPN
    for m in (FDI_ESPN.get(league_id), FD_ESPN.get(league_id)):
        if not m:
            continue
        for frame_key, espn_key in m.items():
            if norm_team(espn_key) == key and frame_key in idx.values():
                return frame_key
    if key in idx:
        return idx[key]
    for nk, actual in idx.items():
        if len(nk) >= 5 and (nk in key or key in nk):
            return actual
    import difflib
    close = difflib.get_close_matches(key, list(idx.keys()), n=1, cutoff=0.85)
    return idx[close[0]] if close else None


def resolve(espn_id, espn_name: str, leagues: list[str],
            tie_break=None) -> tuple[str, str] | None:
    """(league_id, frame_key) for a continental club, or None if unresolved.

    1. ESPN id → candidate leagues (exact club identity).
    2. Name-derived candidates when the id is in no current roster.
    3. More than one candidate means the club moved TIER; `tie_break(cands, name)`
       decides (the calibration path passes a date-aware chooser; the build path
       leaves it None and takes the first resolvable candidate).
    """
    rosters = league_rosters()
    cands: list[str] = []
    if espn_id:
        cands = [lid for lid in leagues if str(espn_id) in rosters.get(lid, {})]
    if not cands:
        key = norm_team(espn_name)
        cands = [lid for lid in leagues if key and key in team_name_index(lid)]
    if not cands:
        return None
    if len(cands) > 1 and tie_break is not None:
        picked = tie_break(cands, espn_name)
        if picked:
            return picked
    for lid in cands:
        k = match_name_in_league(espn_name, lid)
        if k:
            return (lid, k)
    return None
