#!/usr/bin/env python3
"""Harvest a global {team_name: logo_url} map from per-league webapp data files.

Continental competitions (UCL, Europa, Conference, Leagues Cup, Concacaf Champions)
ship their standings/field rows WITHOUT logos, even though almost every team in them
also appears in a domestic league file that DOES carry a logo. This script harvests
those logos into one lookup the webapp consults as a fallback, so continental brackets
and scattered domestic gaps render real crests instead of monogram placeholders.

Emits webapp/data/logos.js -> window.TEAM_LOGOS = {...}

Re-run whenever league data files are rebuilt:  python3 scripts/build_logo_map.py
"""
import json
import re
import glob
import os
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "webapp", "data")


def load(path):
    """Parse a `window.X = {...};` data file into a dict."""
    text = open(path, encoding="utf-8").read()
    text = re.sub(r"^[\s\S]*?=\s*", "", text).rstrip().rstrip(";")
    return json.loads(text)


# Common club-type tokens stripped during normalization so e.g. "FC Porto" ↔ "Porto",
# "AS Roma" ↔ "Roma", "SC Freiburg" ↔ "Freiburg" resolve to the same key.
_CLUB_TOKENS = {
    "fc", "afc", "ac", "sc", "ssc", "as", "cf", "cd", "ss", "sv", "fk", "nk", "sk",
    "bk", "if", "sd", "ca", "club", "deportivo", "calcio", "futbol", "football",
}


def norm(name):
    """Normalize a club name for fuzzy matching: drop diacritics, punctuation, and
    club-type tokens; lowercase; collapse whitespace."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-zA-Z0-9 ]", " ", s).lower()
    toks = [t for t in s.split() if t and t not in _CLUB_TOKENS]
    return " ".join(toks)


# Name aliases: continental payload name -> domestic-file name (only where they differ).
# Add entries here only for teams that exist under a different name in a domestic file.
ALIAS = {
    "Internazionale": "Inter Milan",
    "Inter": "Inter Milan",
    "Paris Saint-Germain": "PSG",
    "Atletico Madrid": "Atlético Madrid",
    "Atletico de Madrid": "Atlético Madrid",
    # MLS teams that appear in Leagues Cup / Concacaf under a shorter name
    "LAFC": "Los Angeles FC",
    "Red Bull New York": "New York Red Bulls",
}

# Manual supplement for teams absent from every league file AND from foreign_logos.json
# (ESPN's domestic roster snapshot omits them). IDs verified via ESPN team API. Format:
#   "Coventry City": "https://a.espncdn.com/i/teamlogos/soccer/500/<id>.png",
SUPPLEMENT = {
    "Mazatlán FC": "https://a.espncdn.com/i/teamlogos/soccer/500/20702.png",  # Liga MX; ESPN mex.1 snapshot stale
    "Le Mans": "https://a.espncdn.com/i/teamlogos/soccer/500/2697.png",
    "Troyes": "https://a.espncdn.com/i/teamlogos/soccer/500/170.png",
}


def main():
    logos = {}          # exact team name -> logo url (harvested from domestic files)
    all_names = set()   # every team name seen anywhere (incl. logo-less continental rows)
    for path in sorted(glob.glob(os.path.join(DATA, "*.js"))):
        if os.path.basename(path) in ("logos.js", "leagues.js"):
            continue
        try:
            d = load(path)
        except Exception:
            continue
        rows = (d.get("standings") or []) + (d.get("field") or [])
        for s in rows:
            name, logo = s.get("team"), s.get("logo")
            if not name:
                continue
            all_names.add(name)
            if logo and name not in logos:
                logos[name] = logo

    harvested = len(logos)

    # Merge ESPN foreign-league logos (scripts/foreign_logos.json, built by fetch_foreign_logos.py)
    # into the pool BEFORE building the fuzzy index, so continental clubs from leagues we don't
    # model domestically (Eredivisie, Primeira, Scottish, Concacaf domestics, …) get resolved.
    foreign_path = os.path.join(os.path.dirname(__file__), "foreign_logos.json")
    foreign_n = 0
    if os.path.exists(foreign_path):
        foreign = json.load(open(foreign_path, encoding="utf-8"))
        for name, url in foreign.items():
            if name and url and name not in logos:
                logos[name] = url
                foreign_n += 1

    # normalized index of teams that DO have a logo (key -> url); keep the shortest
    # source name per key as the canonical (usually the cleaner domestic name).
    norm_index = {}
    for name, url in logos.items():
        k = norm(name)
        if k and (k not in norm_index or len(name) < norm_index[k][1]):
            norm_index[k] = (url, len(name))

    def resolve(name):
        """Find a logo for a logo-less name via normalized exact then substring match."""
        k = norm(name)
        if not k:
            return None
        if k in norm_index:
            return norm_index[k][0]
        # substring containment in either direction, longest token-key wins, guard >=4 chars
        best = None
        for ik, (url, _) in norm_index.items():
            if len(ik) < 4:
                continue
            if (ik in k or k in ik):
                if best is None or len(ik) > best[1]:
                    best = (url, len(ik))
        return best[0] if best else None

    # apply explicit aliases first (authoritative for no-overlap cases)
    for alias, canon in ALIAS.items():
        if alias not in logos and canon in logos:
            logos[alias] = logos[canon]

    # resolve remaining logo-less names by fuzzy match (sorted for deterministic output)
    resolved = 0
    for name in sorted(all_names):
        if name in logos:
            continue
        url = resolve(name)
        if url:
            logos[name] = url
            resolved += 1

    # manual supplement (does not overwrite harvested/resolved logos)
    for name, url in SUPPLEMENT.items():
        logos.setdefault(name, url)

    out = os.path.join(DATA, "logos.js")
    with open(out, "w", encoding="utf-8") as f:
        f.write("window.TEAM_LOGOS=" + json.dumps(logos, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + ";\n")
    print(f"wrote {out}: {len(logos)} teams ({harvested} harvested, {foreign_n} foreign, {resolved} fuzzy-resolved)")
    # report names still unresolved (no logo anywhere we can reach)
    unresolved = sorted(n for n in all_names if n not in logos)
    print(f"unresolved: {len(unresolved)}")
    for n in unresolved:
        print("   ", n)


if __name__ == "__main__":
    main()
