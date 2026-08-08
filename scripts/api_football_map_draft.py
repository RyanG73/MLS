"""Draft the our-league → API-Football-id map from the cached Stage-1 catalogue.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md
§7 Stage 1 ("committed league map", gate: owner reviews mapping).

Zero requests: reads data/api_football/probe/leagues_catalogue.json (fetched
once by scripts/api_football_probe.py) and matches every live competition in
fetch_league_teams.REGISTRY against it by country + name similarity. Confirmed
ids from production (api_football.LEAGUE) and prior live lookups are anchors.

Output: config/api_football_league_map.json — a DRAFT for owner review, with
per-league confidence and runner-up candidates wherever the match is not
certain. Coverage metadata (season depth, statistics/lineups/events flags) is
extracted per matched league so Stage-4 scoping reads from measurement.

Run: python -m scripts.api_football_map_draft
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

CATALOGUE = Path("data/api_football/probe/leagues_catalogue.json")
OUT = Path("config/api_football_league_map.json")

# Confirmed live (production LEAGUE map + recorded lookups) — never re-derived.
ANCHORS: dict[str, int] = {
    "canadian-pl": 479,        # api_football.LEAGUE, confirmed 2026-07-11
    "k-league-1": 292,         # api_football.LEAGUE, confirmed 2026-07-14
    "finland-veikkausliiga": 244,   # find_league_id, 2026-07-11
    "poland-ekstraklasa": 106,      # find_league_id, 2026-07-11
    "leagues-cup": 772,        # find_league_id, 2026-08-08
}

# Our registry name → the name API-Football actually uses, where fuzzy matching
# alone would be ambiguous. Verified against the cached catalogue by the run
# summary — a hint that matches nothing is reported, never silently kept.
NAME_HINTS: dict[str, str] = {
    "mls": "Major League Soccer",
    "brazil-serie-a": "Serie A",
    "brazil-serie-b": "Serie B",
    "argentina-nacional": "Primera Nacional",
    "argentina-primera": "Liga Profesional Argentina",
    "liga-expansion-mx": "Liga de Expansión MX",
    "ucl": "UEFA Champions League",
    "europa": "UEFA Europa League",
    "conference": "UEFA Europa Conference League",
    "libertadores": "CONMEBOL Libertadores",
    "sudamericana": "CONMEBOL Sudamericana",
    "concacaf-champions": "CONCACAF Champions League",
    # Verified by direct catalogue inspection, 2026-08-08 (country-filtered
    # League-type rows) — every value below is a name that exists verbatim in
    # the cached catalogue; the HINT MISMATCH check enforces it on every run.
    "championship": "Championship",
    "league-one": "League One",
    "league-two": "League Two",
    "scottish-prem": "Premiership",
    "scottish-champ": "Championship",
    "scottish-league-one": "League One",
    "scottish-league-two": "League Two",
    "austria-bundesliga": "Bundesliga",
    "swiss-super-league": "Super League",
    "russia-premier": "Premier League",
    "china-super": "Super League",
    "saudi-pro": "Pro League",
    "greek-super": "Super League 1",
    "belgian-pro": "Jupiler Pro League",
    "south-africa-psl": "Premier Soccer League",
    "honduras-liga": "Liga Nacional",
    "guatemala-liga": "Liga Nacional",
    "elsalvador-primera": "Primera Division",
    "colombia-primera-a": "Primera A",
    "romania-liga1": "Liga I",
    "ireland-premier": "Premier Division",
    "chile-primera": "Primera División",
    "peru-liga1": "Primera División",
    "venezuela-primera": "Primera División",
    "costa-rica-primera": "Primera División",
    "bolivia-profesional": "Primera División",
    "nwsl": "NWSL Women",
    "wsl": "FA WSL",
    "liga-f": "Primera División Femenina",
    "france-premiere-ligue": "Feminine Division 1",
    "vrouwen-eredivisie": "Eredivisie Women",
    "paraguay-primera": "Division Profesional - Apertura",
}

# Mapping wrinkles the single-id format cannot express — carried on the entry
# so the owner review and the Stage-3 wiring both see them.
SPECIAL_NOTES: dict[str, str] = {
    "paraguay-primera": ("API-Football splits the season into two ids: "
                         "Apertura=250, Clausura=252. Both are needed to "
                         "cover our single paraguay-primera league."),
}

# Our country label → API-Football's, where they differ.
COUNTRY_ALIASES: dict[str, str] = {
    "united states": "usa",
    "ireland": "ireland",
    "south korea": "south-korea",
    # Continental competitions carry country "World" in the catalogue.
    "north america": "world",
    "europe": "world",
    "south america": "world",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _coverage(row: dict) -> dict:
    """Season depth + earliest season each capability flag is true."""
    seasons = row.get("seasons") or []
    years = sorted(int(s["year"]) for s in seasons)
    firsts: dict[str, int | None] = {}
    for key, path in (("statistics", ("fixtures", "statistics_fixtures")),
                      ("lineups", ("fixtures", "lineups")),
                      ("events", ("fixtures", "events")),
                      ("odds", ("odds",))):
        hit = None
        for s in seasons:
            cov = s.get("coverage") or {}
            v = cov
            for p in path:
                v = v.get(p) if isinstance(v, dict) else None
            if v:
                y = int(s["year"])
                hit = y if hit is None else min(hit, y)
        firsts[f"{key}_since"] = hit
    return {"first_season": years[0] if years else None,
            "last_season": years[-1] if years else None,
            "n_seasons": len(years),
            "reaches_2017": bool(years and years[0] <= 2017),
            **firsts}


def main() -> None:
    catalogue = json.loads(CATALOGUE.read_text())["response"]
    by_id = {int(r["league"]["id"]): r for r in catalogue}

    from scripts.fetch_league_teams import LEAGUE_INFO, REGISTRY

    draft: dict[str, dict] = {}
    review, missing_hints = [], []
    for lid, disp_name, _slug, _confed, status, _group in REGISTRY:
        if status != "live":
            continue
        country, _tier = LEAGUE_INFO.get(lid, (None, None))
        want_country = COUNTRY_ALIASES.get(_norm(country or ""), _norm(country or ""))
        want_name = _norm(NAME_HINTS.get(lid, disp_name))

        if lid in ANCHORS:
            af_id = ANCHORS[lid]
            row = by_id.get(af_id)
            draft[lid] = {"af_id": af_id, "af_name": row["league"]["name"] if row else None,
                          "af_country": row["country"]["name"] if row else None,
                          "confidence": "anchor",
                          **(_coverage(row) if row else {})}
            continue

        scored = []
        for r in catalogue:
            if _norm(r["country"]["name"]) != want_country:
                continue
            score = SequenceMatcher(None, want_name,
                                    _norm(r["league"]["name"])).ratio()
            scored.append((score, r))
        scored.sort(key=lambda t: -t[0])
        if not scored:
            draft[lid] = {"af_id": None, "confidence": "no_country_match",
                          "wanted": {"country": want_country, "name": want_name}}
            review.append(lid)
            continue
        best_score, best = scored[0]
        gap = best_score - (scored[1][0] if len(scored) > 1 else 0.0)
        confidence = ("high" if best_score >= 0.92 or (best_score >= 0.8 and gap >= 0.2)
                      else "review")
        entry = {"af_id": int(best["league"]["id"]),
                 "af_name": best["league"]["name"],
                 "af_country": best["country"]["name"],
                 "match_score": round(best_score, 3),
                 "confidence": confidence,
                 **_coverage(best)}
        if confidence != "high":
            entry["candidates"] = [
                {"af_id": int(r["league"]["id"]), "af_name": r["league"]["name"],
                 "score": round(sc, 3)} for sc, r in scored[:3]]
            review.append(lid)
        if lid in NAME_HINTS and _norm(best["league"]["name"]) != want_name:
            missing_hints.append((lid, NAME_HINTS[lid], best["league"]["name"]))
        if lid in SPECIAL_NOTES:
            entry["note"] = SPECIAL_NOTES[lid]
            entry["confidence"] = "review"      # a note always needs eyes
            review.append(lid) if lid not in review else None
        draft[lid] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(draft, indent=1, ensure_ascii=False) + "\n")

    high = sum(1 for v in draft.values() if v.get("confidence") in ("high", "anchor"))
    mapped = sum(1 for v in draft.values() if v.get("af_id"))
    r2017 = sum(1 for v in draft.values() if v.get("reaches_2017"))
    stats = sum(1 for v in draft.values() if v.get("statistics_since"))
    print(f"mapped {mapped}/{len(draft)} ({high} high/anchor, {len(review)} for review)")
    print(f"reach 2017: {r2017}/{mapped} · statistics flag somewhere: {stats}/{mapped}")
    if review:
        print("needs review:", ", ".join(sorted(review)))
    for lid, hint, got in missing_hints:
        print(f"HINT MISMATCH {lid}: wanted {hint!r}, matched {got!r}")


if __name__ == "__main__":
    main()
