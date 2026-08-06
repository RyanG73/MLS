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

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_pipeline.coefficients import _LEAGUE_COEFF  # noqa: E402
from scripts.build_league_data import OUTLOOK  # noqa: E402
from scripts.payload_utils import write_js_payload  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_REGISTRY = ROOT / "webapp" / "leagues.js"

# UEFA's own spelling where it differs from the league registry's country field.
# Everything else is READ from the registry — see _assoc(). This dict used to be
# the only source of association names, with `ASSOC.get(lid, lid)` as the
# fallback, so the ten leagues nobody had typed in rendered their LEAGUE ID in
# the association column: the table read "norway-eliteserien / Eliteserien"
# where England read "England / Premier League". Half the rows were labelled one
# way and half the other. (2026-08-05 feedback: "these should be listed with the
# country name on top in bold and then the primary league in that country
# below"; the layout was already that — the data was not.)
ASSOC_OVERRIDE = {
    "super-lig": "Türkiye",   # registry says "Turkey"; UEFA uses "Türkiye"
}


def _registry_countries() -> dict[str, str]:
    """{league_id: country} from webapp/leagues.js (window.LEAGUES = [...])."""
    txt = _REGISTRY.read_text(encoding="utf-8")
    rows = json.loads(txt.split("=", 1)[1].rstrip().rstrip(";"))
    return {r["id"]: r.get("country") or "" for r in rows}

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
    countries = _registry_countries()
    ranked = sorted(_LEAGUE_COEFF.items(), key=lambda kv: -kv[1])
    for rank, (lid, coeff) in enumerate(ranked, start=1):
        if lid not in OUTLOOK:
            continue
        assoc = ASSOC_OVERRIDE.get(lid) or countries.get(lid)
        if not assoc:
            # Never fall back to the league id: that is what produced the
            # half-country/half-slug column this replaces. A UEFA league with no
            # country in the registry is a registry bug, so say so loudly rather
            # than shipping a slug into a published table.
            raise SystemExit(
                f"no country in webapp/leagues.js for '{lid}' — add it there "
                f"rather than hand-listing it here"
            )
        rows.append({
            "league_id": lid,
            "league": OUTLOOK[lid]["name"],
            "assoc": assoc,
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
