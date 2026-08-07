#!/usr/bin/env python3
"""Build one global club-strength ladder from the domestic league payloads.

Every row uses the same published contract as league tables and team pages:
domestic ELO + the league/tier bridge + the Club World Cup confederation shift.
The raw domestic rating remains available for auditability, but ranking is
always by ``strength`` on the EPL-anchored global scale.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from data_pipeline import coefficients as co
from scripts.payload_utils import read_js_payload, write_js_payload

_DATA = Path("webapp/data")
_REGISTRY = Path("webapp/leagues.js")
_CONF_ORDER = ["UEFA", "CONMEBOL", "Concacaf", "AFC", "CAF", "OFC"]


def _load_league_payload(league_id: str) -> dict:
    payload = read_js_payload(_DATA / f"{league_id}.js")
    return payload if isinstance(payload, dict) else {}


def _load_standings(league_id: str) -> list[dict]:
    """Read a built league's standings rows."""
    return _load_league_payload(league_id).get("standings") or []


def _domestic_leagues() -> list[dict]:
    """Registry-backed competitions with evidence for a shared club scale.

    Women's competitions are intentionally excluded: no cross-gender match
    network exists to connect their otherwise-valid domestic ELO to the men's
    ladder. Leagues with only a generic confederation fallback are also omitted,
    except South Africa (the sole modeled CAF anchor). Their league pages still
    publish the best available translated rating with its evidence quality, but
    the global ranking does not pretend an unfitted league bridge is measured.
    """
    registry = read_js_payload(_REGISTRY)
    if not isinstance(registry, list):
        return []
    leagues = []
    for entry in registry:
        league_id = entry.get("id")
        if not league_id or entry.get("status") != "live":
            continue
        payload = _load_league_payload(league_id)
        if (payload.get("outlook") or {}).get("mode") not in {"table", "mls"}:
            continue
        standings = payload.get("standings") or []
        if not standings:
            continue
        quality = (payload.get("elo_scale") or {}).get("quality") \
                  or co.global_elo_quality(league_id)
        if entry.get("women"):
            continue
        if quality in {"confederation_anchor", "unanchored"} \
                and league_id != "south-africa-psl":
            continue
        leagues.append({
            "id": league_id,
            "name": entry.get("name") or (payload.get("league") or {}).get("name") or league_id,
            "confederation": entry.get("confederation") or "Other",
            "country": entry.get("country") or "",
            "tier": entry.get("tier") or 1,
            "women": bool(entry.get("women")),
            "n_teams": len(standings),
            "quality": quality,
            # The season this payload actually describes. A league page keeps
            # publishing last season's final table until the new one kicks off,
            # which is right for that page and wrong for a global ladder — see
            # _dedupe_clubs.
            "season": payload.get("season"),
        })
    return leagues


def _dedupe_clubs(rows: list[dict]) -> list[dict]:
    """One row per club, and a country on any name two real clubs share.

    Nine club names appeared twice on the ladder before this existed, and they
    were two different problems wearing one symptom. The country tells them
    apart, so the rule is a measurement rather than a hardcoded list:

    SAME country — one club, listed twice. Every case was a promoted side:
    Athletico-PR, Coritiba, Remo and Chapecoense won promotion from Brazil's
    Série B in 2025 and play Série A in 2026, and the Série B payload still
    describes the completed 2025 season. That is correct for the Série B page,
    which shows last season's final table until the new one kicks off, and wrong
    for a global ladder, which must rank a club where it plays NOW. Keep the
    most recent season; break a tie on the higher division.

    DIFFERENT countries — two clubs that happen to share a name, and both belong
    on the ladder. Liverpool of England and Liverpool of Montevideo; Santos of
    Brazil and Santos Laguna of Mexico. They get a `display` name carrying the
    country, because a reader seeing "Liverpool" 13th and "Liverpool" 673rd has
    no way to know those are different clubs — and neither did this repository:
    keying per-club analysis by name alone handed the English club's European
    record to the Uruguayan one, caught only by an absurd z-score.

    `team` is left alone. It is an identity key — club URLs, crest lookup and
    team ids are all built from it — so the country goes in a separate field
    that only the rendered name uses.
    """
    by_name: dict[str, list[dict]] = {}
    for row in rows:
        by_name.setdefault(row["team"], []).append(row)

    kept: list[dict] = []
    for name, group in by_name.items():
        if len(group) == 1:
            kept.append(group[0])
            continue
        countries = {r["_country"] for r in group}
        if len(countries) > 1:
            for row in group:
                row["display"] = f"{name} ({row['_country']})" if row["_country"] else name
            kept.extend(group)
            continue
        # One club: newest season wins, then the higher division (lower tier no.)
        group.sort(key=lambda r: ((r["_season"] if isinstance(r["_season"], int) else -1),
                                  -(r["tier"] or 9)), reverse=True)
        winner, dropped = group[0], group[1:]
        print(f"[power] {name}: keeping {winner['league']} "
              f"(season {winner['_season']}), dropping "
              + ", ".join(f"{r['league']} (season {r['_season']})" for r in dropped))
        kept.append(winner)
    for row in kept:
        row.pop("_season", None)
        row.pop("_country", None)
    return kept


def _rank_leagues(leagues: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for league in leagues:
        league_id = league["id"]
        offset = co.global_elo_offset(league_id)
        for standing in _load_standings(league_id):
            elo = standing.get("elo")
            if not isinstance(elo, (int, float)):
                continue
            # Prefer the rating the payload already publishes. This used to
            # recompute `elo + offset` here, which silently diverged the moment
            # the translation stopped being a pure shift: lower divisions now
            # also have their spread compressed (elo_scale.dispersion), so the
            # ladder was showing Burnley 45 points above what its own league
            # page showed for the same club. One transformation, applied once,
            # in apply_global_elo_scale. (2026-08-07)
            published = standing.get("global_elo")
            strength = (float(published) if isinstance(published, (int, float))
                        else float(elo) + offset)
            rows.append({
                "team": standing["team"],
                "league": league_id,
                "league_short": league["name"],
                "confederation": league["confederation"],
                "elo": int(round(float(elo))),
                "strength": round(strength, 1),
                "logo": standing.get("logo"),
                "color": standing.get("color"),
                "tier": league["tier"],
                "women": league["women"],
                "quality": league["quality"],
                # Both are internal to the dedupe pass and stripped before
                # writing — country is already implied by the league, and
                # carrying it on 958 rows cost 19KB of payload for nothing.
                "_country": league.get("country") or "",
                "_season": league.get("season"),
            })
    rows = _dedupe_clubs(rows)
    rows.sort(key=lambda row: (-row["strength"], row["team"], row["league"]))
    for rank, row in enumerate(rows, 1):
        row["global_rank"] = rank
        row["rank"] = rank  # compatibility for older clients; also global, never per-panel
    return rows


def _groups(teams: list[dict]) -> list[dict]:
    """Small confederation filter metadata; ranks live only in top-level teams."""
    order = {name: i for i, name in enumerate(_CONF_ORDER)}
    confederations = sorted(
        {team["confederation"] for team in teams},
        key=lambda name: (order.get(name, len(order)), name),
    )
    return [{
        "confederation": conf,
        "anchor": "EPL = 0",
        "n_leagues": len({team["league"] for team in teams
                          if team["confederation"] == conf}),
        "n_teams": sum(team["confederation"] == conf for team in teams),
    } for conf in confederations]


def build() -> dict:
    leagues = _domestic_leagues()
    teams = _rank_leagues(leagues)
    data = {
        "status": "live",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "anchor": "EPL = 0",
        "method": "domestic ELO + league/tier bridge + Club World Cup confederation shift",
        "cross_conf_matches": 60,
        "teams": teams,
        "leagues": leagues,
        "groups": _groups(teams),
    }
    out = _DATA / "power.js"
    write_js_payload(out, "POWER_DATA", data)
    if teams:
        top = teams[0]
        print(f"[power] {len(teams)} teams · {len(leagues)} leagues · "
              f"#{top['global_rank']} {top['team']} ({top['strength']})")
    print(f"[power] wrote {out} ({out.stat().st_size // 1024} KB)")
    return data


if __name__ == "__main__":
    build()
