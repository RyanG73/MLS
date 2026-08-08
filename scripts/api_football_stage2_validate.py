"""Stage-2 validation — one league from the spine, diffed column by column.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md §7 Stage 2.

League: brazil-serie-a (API-Football id 71, map-approved 2026-08-08). Chosen
because it sits fully inside the free key's 2022–2024 window, its current
source (football-data intl) carries real scorelines — a stronger diff than a
goals-only ESPN league — and its comparison frame loads from cached CSVs, so
validation never depends on ESPN's rate limiter.

Deliberately NOT a local payload rebuild: local rebuilds regress payloads (a
recorded failure mode; CI owns payload writes). The canonical frame is the
pipeline's entire interface (spec §6.3), so frame equivalence — same fixtures,
same scorelines, same standings, feature build accepted — is mechanism
equivalence. ~3 requests (one per season), cached and never re-spent.

Run: python -m scripts.api_football_stage2_validate
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

REPORT = Path("data/api_football/probe/stage2_report.json")
BRA_AF_ID = 71
SEASONS = [2022, 2023, 2024]

# API-Football club name → football-data-intl club name, for spellings the
# accent/punctuation normalizer cannot bridge. Exactly the six pairs measured
# from this script's own unmatched-names output on 2026-08-08 (26 clubs across
# three seasons; the other 20 spellings already agree).
SPINE_RENAME: dict[str, str] = {
    "Athletico Paranaense": "Athletico-PR",
    "Atletico Goianiense": "Atletico GO",
    "Atletico Mineiro": "Atletico-MG",
    "Botafogo": "Botafogo RJ",
    "Flamengo": "Flamengo RJ",
    "Fortaleza EC": "Fortaleza",
    # API-Football's own names vary BY SEASON for the same club (measured on
    # the second pass — the K-League TEAM_RENAME problem again): 2022 uses
    # these spellings, later seasons the ones above.
    "Atletico Paranaense": "Athletico-PR",
    "RB Bragantino": "Bragantino",
    "America Mineiro": "America MG",
    "Vasco DA Gama": "Vasco",
}


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFD", str(name))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def standings(frame: pd.DataFrame, season: int) -> dict[str, int]:
    """Team → points from played rows of one season (3/1/0)."""
    f = frame[(frame["season"] == season) & frame["is_result"]]
    pts: dict[str, int] = {}
    for _, r in f.iterrows():
        h, a = r["home_team"], r["away_team"]
        hg, ag = int(r["home_goals"]), int(r["away_goals"])
        pts.setdefault(h, 0)
        pts.setdefault(a, 0)
        if hg > ag:
            pts[h] += 3
        elif hg < ag:
            pts[a] += 3
        else:
            pts[h] += 1
            pts[a] += 1
    return pts


def join_and_diff(ours: pd.DataFrame, spine: pd.DataFrame,
                  spine_rename: dict[str, str] | None = None) -> dict:
    """Join played fixtures on (season, home, away) — unique in a round-robin —
    and compare scorelines. Dates are excluded from the key: sources disagree
    on the calendar day of evening kickoffs (timezone), and that is not a data
    error."""
    rename = spine_rename or {}
    ours = ours[ours["is_result"]].copy()
    spine = spine[spine["is_result"]].copy()
    for col in ("home_team", "away_team"):
        spine[col] = spine[col].map(lambda n: rename.get(n, n))

    def rows_by_key(df):
        out = {}
        for _, r in df.iterrows():
            out[(int(r["season"]), _norm(r["home_team"]),
                 _norm(r["away_team"]))] = r
        return out

    o_rows, s_rows = rows_by_key(ours), rows_by_key(spine)
    disagreements = []
    agree = matched = 0
    for k, o in o_rows.items():
        s = s_rows.get(k)
        if s is None:
            continue
        matched += 1
        if (int(o["home_goals"]), int(o["away_goals"])) == \
           (int(s["home_goals"]), int(s["away_goals"])):
            agree += 1
        else:
            disagreements.append({
                "season": int(o["season"]),
                "home_team": o["home_team"], "away_team": o["away_team"],
                "ours": [int(o["home_goals"]), int(o["away_goals"])],
                "spine": [int(s["home_goals"]), int(s["away_goals"])]})
    return {
        "matched": matched,
        "score_agree": agree,
        "disagreements": disagreements,
        "only_ours": [(r["home_team"], r["away_team"])
                      for k, r in o_rows.items() if k not in s_rows],
        "only_spine": [(r["home_team"], r["away_team"])
                       for k, r in s_rows.items() if k not in o_rows],
    }


def main() -> None:
    from data_pipeline import api_football
    from scripts.build_league_data import _load_frame, build_league_features

    spine = api_football._fetch_league(BRA_AF_ID, SEASONS)     # ≤3 requests
    ours = _load_frame("brazil-serie-a", "footballdata_intl")
    ours = ours[ours["season"].isin(SEASONS)]

    report: dict = {"league": "brazil-serie-a", "af_id": BRA_AF_ID,
                    "seasons": SEASONS, "per_season": {}}
    diff = join_and_diff(ours, spine, spine_rename=SPINE_RENAME)
    for s in SEASONS:
        o_n = int((ours["season"] == s).sum())
        s_n = int((spine["season"] == s).sum())
        po, ps = standings(ours, s), standings(
            spine.assign(**{c: spine[c].map(lambda n: SPINE_RENAME.get(n, n))
                            for c in ("home_team", "away_team")}), s)
        keymap = {_norm(k): k for k in po}
        pts_diff = {k: (po.get(keymap.get(_norm(k), k), None), v)
                    for k, v in ps.items()
                    if po.get(keymap.get(_norm(k), k)) != v}
        report["per_season"][s] = {
            "fixtures_ours": o_n, "fixtures_spine": s_n,
            "teams_ours": len(po), "teams_spine": len(ps),
            "standings_mismatches": pts_diff}
    report["join"] = {k: v for k, v in diff.items() if k != "disagreements"}
    report["join"]["disagreements"] = diff["disagreements"][:20]
    report["join"]["n_disagreements"] = len(diff["disagreements"])

    # End-to-end mechanism check: the champion feature builder accepts the
    # spine frame without modification.
    played = spine[spine["is_result"]].copy()
    for c in ("home_goals", "away_goals", "label_result"):
        played[c] = played[c].astype(int)
    feats = build_league_features(played, league_id="brazil-serie-a")
    report["feature_build"] = {"rows": int(len(feats)),
                               "cols": int(feats.shape[1])}

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False))

    j = report["join"]
    print(f"matched {j['matched']} fixtures; scorelines agree "
          f"{j['score_agree']}/{j['matched']}; "
          f"unmatched ours={len(j['only_ours'])} spine={len(j['only_spine'])}")
    for s in SEASONS:
        p = report["per_season"][s]
        print(f"  {s}: fixtures {p['fixtures_ours']} vs {p['fixtures_spine']}, "
              f"teams {p['teams_ours']} vs {p['teams_spine']}, "
              f"standings mismatches: {len(p['standings_mismatches'])}")
    if j["only_ours"] or j["only_spine"]:
        print("  only_ours:", j["only_ours"][:10])
        print("  only_spine:", j["only_spine"][:10])
    print(f"feature build: {report['feature_build']}")
    from data_pipeline import api_budget
    print("spend today:", api_budget.spend_today())


if __name__ == "__main__":
    main()
