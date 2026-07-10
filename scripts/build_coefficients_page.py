#!/usr/bin/env python3
"""UEFA-coefficients explainer payload → webapp/data/coefficients.js (I1).

Champions-League place counts vary by season with the association coefficient
ranking; the webapp's UCL columns already encode the current allocation per
league (OUTLOOK green_line / _TOP buckets). This page makes that visible:
each modeled UEFA league's 5-year coefficient, its rank among the modeled
set, and the European spots the site's simulation is using.

Data sources:
  - data_pipeline.coefficients._LEAGUE_COEFF (refreshed ~annually)
  - scripts.build_league_data.OUTLOOK (the sim's live slot config)

Usage: python3 scripts/build_coefficients_page.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_pipeline.coefficients import _LEAGUE_COEFF  # noqa: E402
from scripts.build_league_data import OUTLOOK  # noqa: E402
from scripts.payload_utils import write_js_payload  # noqa: E402

ASSOC = {
    "epl": "England", "la-liga": "Spain", "serie-a": "Italy",
    "bundesliga": "Germany", "ligue-1": "France", "eredivisie": "Netherlands",
    "primeira": "Portugal", "belgian-pro": "Belgium", "super-lig": "Türkiye",
    "greek-super": "Greece", "scottish-prem": "Scotland",
}

# 2025-26 season: England and Italy hold the two European Performance Spots
# (their clubs earned the best association coefficient the prior season), so
# their leagues send 5 to the Champions League instead of 4.
EPS_HOLDERS = {"epl", "serie-a"}


def _spots(lid: str) -> dict:
    """European spots as the sim uses them (from the league's OUTLOOK buckets)."""
    buckets = {b["key"]: b for b in OUTLOOK[lid]["buckets"]}
    out = {}
    if "ucl" in buckets:
        out["ucl"] = buckets["ucl"]["top"]
    for k in ("europa", "conf"):
        if k in buckets:
            band = buckets[k]["band"]
            out[k] = band[1] - band[0] + 1
    return out


def build() -> dict:
    rows = []
    ranked = sorted(_LEAGUE_COEFF.items(), key=lambda kv: -kv[1])
    for rank, (lid, coeff) in enumerate(ranked, start=1):
        if lid not in OUTLOOK:
            continue
        rows.append({
            "league_id": lid,
            "league": OUTLOOK[lid]["name"],
            "assoc": ASSOC.get(lid, lid),
            "coeff": coeff,
            "rank": rank,
            "eps": lid in EPS_HOLDERS,
            **_spots(lid),
        })
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "coeff_season": "2025-26",
        "note": ("Coefficients are UEFA's 5-year country ranking captured at the "
                 "end of 2025-26; ranks shown are within the leagues modeled on "
                 "this site. Domestic-cup-winner spots and qualifying paths are "
                 "not modeled — the table columns show league-position spots only."),
        "associations": rows,
    }


def main() -> int:
    data = build()
    write_js_payload(Path("webapp/data/coefficients.js"), "COEFF_DATA", data)
    print(f"Wrote webapp/data/coefficients.js ({len(data['associations'])} associations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
