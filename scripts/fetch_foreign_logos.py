#!/usr/bin/env python3
"""Fetch team→logo URLs from ESPN for foreign leagues we don't model domestically.

Continental competitions (UCL/Europa/Conference/Concacaf) include clubs from leagues
outside our 17 tracked competitions — Eredivisie, Primeira Liga, Scottish, Turkish, Greek,
Concacaf domestic leagues, etc. Those clubs render as monograms because no logo exists in
any `webapp/data/*.js` file. This script harvests their logos from ESPN's public teams API
into `scripts/foreign_logos.json`, which `build_logo_map.py` then merges into its logo pool
(so the existing fuzzy matcher resolves our payload names against them).

Network, run occasionally:  python3 scripts/fetch_foreign_logos.py
The committed JSON keeps `build_logo_map.py` offline and deterministic.
"""
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "scripts", "foreign_logos.json")

# ESPN soccer league slugs covering the foreign clubs that appear in our continental comps.
# Unknown/invalid slugs are skipped gracefully, so an over-broad list is safe.
LEAGUES = [
    # Continental competitions — their own team endpoints list every participant WITH a logo,
    # which is the most direct source for the foreign clubs in our continental payloads.
    "uefa.champions", "uefa.europa", "uefa.europa.conf",
    "concacaf.champions", "concacaf.leagues.cup",
    # Liga MX (covers Mazatlán, which liga-mx.js itself omits)
    "mex.1",
    # UEFA — major non-Big-5 leagues (cover most UCL/Europa/Conference clubs)
    "ned.1", "por.1", "sco.1", "tur.1", "gre.1", "bel.1", "aut.1", "sui.1",
    "ukr.1", "cze.1", "pol.1", "den.1", "nor.1", "swe.1", "cro.1", "srb.1",
    "rou.1", "hun.1", "rus.1", "isr.1", "bul.1", "cyp.1", "irl.1", "fin.1",
    "isl.1", "slo.1", "svk.1", "aze.1", "kaz.1", "arm.1", "bih.1", "mlt.1",
    "gib.1", "mkd.1", "wal.1", "ksv.1", "mne.1", "lva.1", "ltu.1", "est.1",
    "lux.1", "alb.1", "geo.1", "fra.2", "esp.2",
    # Domestic leagues we DO model. The original assumption was that their own data
    # files always carry inline logos — but clubs that change divisions between
    # builds ship logo:null (2026-07-09 audit: West Ham in championship.js, St. Pauli
    # in bundesliga-2.js, Girona in segunda.js, …), so harvest these directly too.
    "eng.1", "eng.2", "eng.3", "eng.4", "eng.5",
    "ger.1", "ger.2", "esp.1", "ita.1", "ita.2", "fra.1", "por.2",
    "usa.1", "usa.nwsl", "usa.usl.1", "ned.2",
    # Concacaf domestic leagues (Leagues Cup / Champions Cup participants)
    "crc.1", "hon.1", "gua.1", "jam.1", "pan.1", "slv.1", "nca.1", "can.1",
    "dom.1", "tri.1", "hai.1", "crb.1",
]

UA = {"User-Agent": "Mozilla/5.0 (logo-fetch)"}


def fetch(slug):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/teams?limit=200"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def main():
    logos = {}
    ok, fail = [], []
    for slug in LEAGUES:
        try:
            d = fetch(slug)
            teams = d["sports"][0]["leagues"][0]["teams"]
        except Exception as e:
            fail.append(f"{slug} ({type(e).__name__})")
            continue
        n = 0
        for t in teams:
            tm = t.get("team", {})
            href = (tm.get("logos") or [{}])[0].get("href")
            if not href:
                continue
            # index under several name variants so build_logo_map's fuzzy matcher has anchors
            for key in (tm.get("displayName"), tm.get("shortDisplayName"), tm.get("name"), tm.get("nickname")):
                if key and key not in logos:
                    logos[key] = href
                    n += 1
        ok.append(f"{slug}:{len(teams)}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(logos.items())), f, ensure_ascii=False, indent=0)
    print(f"wrote {OUT}: {len(logos)} name→logo entries")
    print(f"fetched: {', '.join(ok)}")
    if fail:
        print(f"skipped (no data): {', '.join(fail)}")


if __name__ == "__main__":
    main()
