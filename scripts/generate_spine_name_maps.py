#!/usr/bin/env python3
"""Derive API-Football → canonical club-name maps by FIXTURE DIFF, per league.

This is the blocker on getting off ESPN, generalized. `config/api_football_
team_names.json` covers three leagues because MLS's map was worked out by hand
(commit dbbf1bd); routing the other seventy-five needs the same evidence, and
doing it by hand seventy-five times is how a wrong pair gets waved through.

## The rule this script exists to obey

**A name pair is proven by fixtures, never by name similarity.** Fuzzy matching
once proposed `Bristol City → Stoke City` during Stage 3 — a pairing that would
have attributed one club's results and xG to another and looked entirely
plausible in the payload. So a pair is accepted here only when the two clubs
play the same matches, on the same dates, with the same scorelines, and never
disagree.

Name similarity is used for exactly one thing: deciding which pairs are already
handled by the production token matcher and therefore do NOT need an override
entry. It never creates a pair.

## Why the coverage floor is 1.0 and not a share

An unmapped club is not a visibly missing club. Downstream it fails to resolve,
is discarded as "not in this league", and the payload still looks healthy —
short a team nobody counted. 29 of 30 is 96.7%, clears any sane percentage
floor, and silently drops every LA Galaxy fixture. A closed league has a known
club set, so the only honest floor is all of them.

Usage:
    python scripts/generate_spine_name_maps.py --league epl          # one
    python scripts/generate_spine_name_maps.py --all                 # every mapped league
    python scripts/generate_spine_name_maps.py --all --check         # verify, write nothing
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAYLOADS = ROOT / "webapp" / "data"
LEAGUE_MAP = ROOT / "config" / "api_football_league_map.json"
NAMES_PATH = ROOT / "config" / "api_football_team_names.json"

# A late kickoff lands on the next calendar day in UTC. The MLS validation hit
# exactly this: a 23:30 UTC fixture matched a day later at the same 2-1, and it
# was a timezone, not a discrepancy. One day either side, no wider — widening
# this is how two different matchdays start matching each other.
DATE_SLACK = dt.timedelta(days=1)

# A pair needs this much agreement before it is believed. One shared scoreline
# is a coincidence; several, with no contradiction anywhere, is evidence.
MIN_CORROBORATING_FIXTURES = 3

_SUFFIX = {"fc", "sc", "cf", "afc", "ac", "cd", "sv", "if", "fk", "bk"}


def _norm(name) -> str:
    """Lowercase, strip accents and punctuation. Mirrors build_dashboard_data._norm."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return "".join(c for c in text.lower() if c.isalnum() or c == " ").strip()


def _toks(normalized: str) -> tuple[str, ...]:
    """Token set with club-type suffixes removed. Mirrors build_dashboard_data._toks."""
    return tuple(sorted(t for t in normalized.split() if t not in _SUFFIX))


def token_match(a: str, b: str) -> bool:
    """True when production's matcher already resolves these two spellings.

    Used ONLY to decide whether a proven pair needs an override entry. A pair
    this returns True for is already handled and writing it down would be noise
    that later reads as a rule.
    """
    return _toks(_norm(a)) == _toks(_norm(b))


# ── our side ─────────────────────────────────────────────────────────────────

def read_payload(league_id: str) -> dict:
    path = PAYLOADS / f"{league_id}.js"
    if not path.exists():
        raise FileNotFoundError(f"no committed payload for {league_id}")
    source = path.read_text(errors="replace")
    match = re.search(r"=\s*(\{.*\})\s*;?\s*$", source, re.S)
    if not match:
        raise ValueError(f"{path.name} is not a readable payload")
    return json.loads(match.group(1))


def our_fixtures(payload: dict) -> list[dict]:
    """Played fixtures only — an unplayed match carries no scoreline to match on."""
    rows = []
    for game in payload.get("games") or []:
        if game.get("hg") is None or game.get("ag") is None:
            continue
        date = _date(game.get("date"))
        if date is None:
            continue
        rows.append({"date": date, "home": game["home"], "away": game["away"],
                     "hg": int(game["hg"]), "ag": int(game["ag"])})
    return rows


def our_clubs(payload: dict) -> set[str]:
    return {row["team"] for row in payload.get("standings") or [] if row.get("team")}


def _date(value) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# ── the spine side ───────────────────────────────────────────────────────────

def spine_fixtures(league_id: str, af_id: int, seasons: list[int]) -> list[dict]:
    """Played fixtures from API-Football, in the same shape as ours."""
    from data_pipeline import api_football

    frame = api_football._fetch_league(af_id, seasons)
    rows = []
    if frame is None or frame.empty:
        return rows
    for row in frame.itertuples():
        if not getattr(row, "is_result", False):
            continue
        date = _date(getattr(row, "date", None))
        if date is None:
            continue
        rows.append({"date": date,
                     "home": row.home_team, "away": row.away_team,
                     "hg": int(row.home_goals), "ag": int(row.away_goals)})
    return rows


# ── the diff ─────────────────────────────────────────────────────────────────

def _seed(ours: list[dict], theirs: list[dict]) -> dict[str, str]:
    """Pairs production's own token matcher already resolves.

    This is a seed, not a decision. Token matching is exact after normalisation
    and suffix-stripping — it is what production runs, not a fuzzy score — so it
    cannot pair `Bristol City` with `Stoke City`. Every seeded pair still has to
    survive fixture corroboration below; a seed that contradicts the fixtures is
    reported, not kept.
    """
    ours_names = {row[side] for row in ours for side in ("home", "away")}
    theirs_names = {row[side] for row in theirs for side in ("home", "away")}
    by_tokens: dict[tuple, list[str]] = defaultdict(list)
    for name in ours_names:
        by_tokens[_toks(_norm(name))].append(name)
    seed = {}
    for name in theirs_names:
        candidates = by_tokens.get(_toks(_norm(name)) , [])
        if len(candidates) == 1:                 # an ambiguous token set seeds nothing
            seed[name] = candidates[0]
    return seed


def _candidates(mine: dict, by_score: dict, known: dict[str, str]) -> list[dict]:
    """Our fixtures consistent with theirs, given what is already known.

    Scoreline and date alone are far too weak: consecutive matchdays repeat
    scorelines constantly (1-0 most of all), and with a day of slack they
    cross-match. What makes a fixture identifiable is its OPPONENTS — so a
    candidate must also agree on every endpoint already resolved.
    """
    out = []
    for row in by_score.get((mine["hg"], mine["ag"]), ()):
        if abs(row["date"] - mine["date"]) > DATE_SLACK:
            continue
        home, away = known.get(mine["home"]), known.get(mine["away"])
        if home is not None and home != row["home"]:
            continue
        if away is not None and away != row["away"]:
            continue
        out.append(row)
    return out


def derive_pairs(ours: list[dict], theirs: list[dict]) -> tuple[dict, list[str], list[str]]:
    """(their name → our name) proven by fixture agreement, plus contradictions.

    Seeded constraint propagation. Start from the pairs production's matcher
    already resolves, then repeatedly accept any fixture that a single one of
    ours can match given what is known — each acceptance resolves its remaining
    endpoint, which lets more fixtures become unambiguous on the next pass.

    A name whose fixtures corroborate two different clubs equally is dropped
    rather than guessed. That is the `Bristol City → Stoke City` case: a wrong
    pair attributes one club's results to another and looks entirely plausible
    in the payload, so refusing to answer is the correct answer.

    Returns (pairs, problems, unplaced). `unplaced` names spine clubs the
    fixtures never placed — reported separately because it is diagnostic, not
    an error: the spine legitimately carries clubs our table does not, and what
    actually has to hold is that every club in OUR standings resolved.
    """
    by_score: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in ours:
        by_score[(row["hg"], row["ag"])].append(row)

    known = _seed(ours, theirs)
    votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for _ in range(len(theirs) + 1):             # bounded; converges well before this
        learned = False
        votes = defaultdict(lambda: defaultdict(int))
        for mine in theirs:
            matches = _candidates(mine, by_score, known)
            if len(matches) != 1:
                continue                          # ambiguous this pass; may resolve next
            row = matches[0]
            votes[mine["home"]][row["home"]] += 1
            votes[mine["away"]][row["away"]] += 1
            for their_name, our_name in ((mine["home"], row["home"]),
                                         (mine["away"], row["away"])):
                if known.get(their_name) is None:
                    known[their_name] = our_name
                    learned = True
        if not learned:
            break

    pairs: dict[str, str] = {}
    problems: list[str] = []
    for their_name, our_name in known.items():
        tally = votes.get(their_name) or {}
        support = tally.get(our_name, 0)
        contradicting = {k: v for k, v in tally.items() if k != our_name}
        if contradicting:
            problems.append(
                f"{their_name!r}: ambiguous — {our_name!r} and "
                f"{max(contradicting, key=contradicting.get)!r} both supported")
            continue
        if support < MIN_CORROBORATING_FIXTURES:
            problems.append(
                f"{their_name!r}: only {support} corroborating fixture(s), "
                f"need {MIN_CORROBORATING_FIXTURES}")
            continue
        pairs[their_name] = our_name

    # One of ours must not be claimed by two of theirs.
    claimed: dict[str, list[str]] = defaultdict(list)
    for their_name, our_name in pairs.items():
        claimed[our_name].append(their_name)
    for our_name, theirs_names in claimed.items():
        if len(theirs_names) > 1:
            problems.append(f"{our_name!r} claimed by {sorted(theirs_names)}")
            for name in theirs_names:
                pairs.pop(name, None)

    spine_names = {row[side] for row in theirs for side in ("home", "away")}
    unplaced = sorted(spine_names - set(pairs) - {n for n in known if n in spine_names
                                                  and any(n in p for p in problems)})
    return pairs, problems, unplaced


def overrides_only(pairs: dict[str, str]) -> dict[str, str]:
    """Drop pairs production's token matcher already resolves."""
    return {their: our for their, our in pairs.items() if not token_match(their, our)}


def audit(league_id: str, ours: list[dict], theirs: list[dict],
          clubs: set[str]) -> dict:
    pairs, problems, unplaced = derive_pairs(ours, theirs)
    resolved = set(pairs.values())
    missing = sorted(clubs - resolved)
    return {
        "league_id": league_id,
        "our_fixtures": len(ours),
        "spine_fixtures": len(theirs),
        "clubs": len(clubs),
        "resolved": len(resolved & clubs),
        "missing": missing,
        "problems": problems,
        "unplaced": unplaced,
        "pairs": pairs,
        "overrides": overrides_only(pairs),
        # The floor is every club, not a share of them. See the module docstring.
        "ok": not missing and not problems,
    }


# ── driver ───────────────────────────────────────────────────────────────────

def mapped_leagues() -> dict:
    spec = json.loads(LEAGUE_MAP.read_text())
    return {k: v for k, v in spec.items() if isinstance(v, dict) and v.get("af_id")}


def run_league(league_id: str, entry: dict) -> dict:
    payload = read_payload(league_id)
    seasons = [entry.get("last_season")] if entry.get("last_season") else []
    theirs = spine_fixtures(league_id, entry["af_id"], [s for s in seasons if s])
    return audit(league_id, our_fixtures(payload), theirs, our_clubs(payload))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check", action="store_true",
                        help="report only; never write the map")
    args = parser.parse_args()

    spec = mapped_leagues()
    if args.league:
        targets = {args.league: spec.get(args.league)}
        if targets[args.league] is None:
            print(f"{args.league} is not in {LEAGUE_MAP.name}", file=sys.stderr)
            return 2
    elif args.all:
        targets = spec
    else:
        parser.error("pass --league <id> or --all")

    existing = json.loads(NAMES_PATH.read_text()) if NAMES_PATH.exists() else {}
    reports, writable = [], dict(existing)
    for league_id, entry in sorted(targets.items()):
        try:
            report = run_league(league_id, entry)
        except Exception as exc:                      # noqa: BLE001 — reported per league
            reports.append({"league_id": league_id, "ok": False,
                            "problems": [f"{type(exc).__name__}: {exc}"],
                            "missing": [], "overrides": {}})
            continue
        reports.append(report)
        if report["ok"]:
            writable[league_id] = report["overrides"]

    ok = [r for r in reports if r["ok"]]
    for report in reports:
        mark = "PASS" if report["ok"] else "HOLD"
        print(f"[{mark}] {report['league_id']:<28} "
              f"{report.get('resolved', 0)}/{report.get('clubs', 0)} clubs "
              f"· {len(report.get('overrides') or {})} override(s)")
        for problem in (report.get("problems") or [])[:4]:
            print(f"         ! {problem}")
        if report.get("missing"):
            print(f"         ! unresolved: {', '.join(report['missing'][:6])}")

    print(f"\n{len(ok)}/{len(reports)} leagues cleared the all-clubs floor")
    if args.check:
        print("--check: nothing written")
        return 0 if len(ok) == len(reports) else 1
    NAMES_PATH.write_text(json.dumps(writable, indent=2, sort_keys=True) + "\n")
    print(f"wrote {NAMES_PATH.relative_to(ROOT)} "
          f"({len(writable)} leagues; leagues on HOLD keep their previous entry)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
