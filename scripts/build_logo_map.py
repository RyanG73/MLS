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


def _league_meta():
    """{league_id: {country, confederation, women}} from the registry."""
    reg = load(os.path.join(ROOT, "webapp", "leagues.js"))
    return {r["id"]: r for r in reg}


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
    # Women's side of a men's club already in the pool, where the only source
    # name is a single token and therefore no longer substring-matchable
    # (2026-07-25, see _sub_match). Same club, same crest — safe to alias.
    "OL Lyonnes": "Lyon",
    # Spelling variant the token-boundary prefix rule cannot bridge
    # ("sheffield wed" vs "sheffield weds"). Unambiguous: one English club.
    "Sheffield Weds": "Sheffield Wednesday",
}

# Manual supplement for teams absent from every league file AND from foreign_logos.json
# (ESPN's domestic roster snapshot omits them). IDs verified via ESPN team API. Format:
#   "Coventry City": "https://a.espncdn.com/i/teamlogos/soccer/500/<id>.png",
SUPPLEMENT = {
    "Mazatlán FC": "https://a.espncdn.com/i/teamlogos/soccer/500/20702.png",  # Liga MX; ESPN mex.1 snapshot stale
    "Le Mans": "https://a.espncdn.com/i/teamlogos/soccer/500/2697.png",
    "Troyes": "https://a.espncdn.com/i/teamlogos/soccer/500/170.png",
    # 2026-07-09 coverage audit: short-name aliases used by power.js / league files
    # whose ESPN art exists under a different key or id.
    "NAC Breda": "https://a.espncdn.com/i/teamlogos/soccer/500/141.png",
    "Volendam": "https://a.espncdn.com/i/teamlogos/soccer/500/2727.png",   # FC Volendam
    "Heracles": "https://a.espncdn.com/i/teamlogos/soccer/500/3708.png",   # Heracles Almelo
    "Dender": "https://a.espncdn.com/i/teamlogos/soccer/500/7878.png",
    "Livingston": "https://a.espncdn.com/i/teamlogos/soccer/500/259.png",
    # ESPN has no art for these (404 at /i/teamlogos/soccer/500/<id>.png) —
    # Wikipedia crest thumbnails, verified 200 on 2026-07-09.
    "Lommel SK": "https://upload.wikimedia.org/wikipedia/en/thumb/e/e6/Lommel_SK_logo.svg/500px-Lommel_SK_logo.svg.png",
    "Energie Cottbus": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Logo_Energie_Cottbus.svg/500px-Logo_Energie_Cottbus.svg.png",
    "Defense Force FC": "https://upload.wikimedia.org/wikipedia/en/1/12/Defence_Force_FC_%28Trinidad_%26_Tobago%29.png",
    "Forge FC": "https://upload.wikimedia.org/wikipedia/en/thumb/b/bf/Forge_FC_logo.svg/500px-Forge_FC_logo.svg.png",
    "Mount Pleasant FA": "https://upload.wikimedia.org/wikipedia/en/1/19/Mount_Pleasant_Football_Academy_Logo.png",
    "Académico de Viseu": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9f/A.C._Viseu.svg/500px-A.C._Viseu.svg.png",
    # Celta B side — Wikipedia's page image is a stadium photo; use the parent club crest.
    "RC Celta Fortuna": "https://a.espncdn.com/i/teamlogos/soccer/500/85.png",
    # Relegated out of por.1 whose por.2 endpoint 404s — pinned from the pre-refresh map.
    "AVS": "https://a.espncdn.com/i/teamlogos/soccer/500/22064.png",
    "Tondela": "https://a.espncdn.com/i/teamlogos/soccer/500/12706.png",
    # "Universidad O&M": no crest on en/es Wikipedia or ESPN — initials fallback stays.
}


def main():
    logos = {}          # exact team name -> logo url (harvested from domestic files)
    all_names = set()   # every team name seen anywhere (incl. logo-less continental rows)
    # Where each name was seen, so resolution can be scoped instead of global.
    # origin_conf[name] = set of confederations, origin_country[name] = set of countries.
    origin_conf = {}
    origin_country = {}
    league_meta = _league_meta()

    for path in sorted(glob.glob(os.path.join(DATA, "*.js"))):
        base = os.path.basename(path)
        if base in ("logos.js", "leagues.js"):
            continue
        try:
            d = load(path)
        except Exception:
            continue
        # Skip non-league-payload data files (e.g. search-index.js is a JSON
        # array, not a payload dict) — same recurring guard as
        # archive_odds_snapshot.py / validate_payloads.py.
        if not isinstance(d, dict):
            continue
        file_lid = base[:-3]
        file_meta = league_meta.get(file_lid, {})
        rows = (d.get("standings") or []) + (d.get("field") or [])
        for s in rows:
            name, logo = s.get("team"), s.get("logo")
            if not name:
                continue
            # Continental payloads tag each club with its DOMESTIC league
            # (Libertadores rows carry league="ecuador-ligapro"). That is the
            # only thing that separates Barcelona SC from FC Barcelona, so it
            # wins over the file's own metadata whenever it is present.
            row_meta = league_meta.get(s.get("league")) or file_meta
            if row_meta.get("confederation"):
                origin_conf.setdefault(name, set()).add(row_meta["confederation"])
            if row_meta.get("country"):
                origin_country.setdefault(name, set()).add(row_meta["country"])
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
    # Built three ways — by country, by confederation, and globally — because a
    # flat global index is exactly what made lower-league clubs wear big clubs'
    # crests: norm() strips "SC"/"CD"/"FC", so "Barcelona SC" (Ecuador) collapsed
    # onto "barcelona" and inherited FC Barcelona's badge. Same for Everton CD
    # (Chile) -> Everton FC, Liverpool FC (Uruguay) -> Liverpool FC, and
    # "Athletic" (Brazil Série B) -> Athletic Club Bilbao.
    norm_index = {}
    by_country = {}
    by_conf = {}
    for name, url in logos.items():
        k = norm(name)
        if not k:
            continue
        if k not in norm_index or len(name) < norm_index[k][1]:
            norm_index[k] = (url, len(name))
        for c in origin_country.get(name, ()):
            d_ = by_country.setdefault(c, {})
            if k not in d_ or len(name) < d_[k][1]:
                d_[k] = (url, len(name))
        for f in origin_conf.get(name, ()):
            d_ = by_conf.setdefault(f, {})
            if k not in d_ or len(name) < d_[k][1]:
                d_[k] = (url, len(name))

    # A normalized key claimed by clubs in more than one country is ambiguous:
    # resolving it globally is a coin flip, and the loser wears the wrong crest.
    ambiguous = set()
    key_countries = {}
    for name in all_names:
        k = norm(name)
        if k:
            key_countries.setdefault(k, set()).update(origin_country.get(name, ()))
    for k, cs in key_countries.items():
        if len(cs) > 1:
            ambiguous.add(k)

    def _sub_match(k, index, multi_token_query=False):
        """Longest-key substring containment within one scoped index.

        Two constraints, both load-bearing:

        1. the matched INDEX key must be at least two tokens. The old rule was
           a bare ">= 4 characters", and short-name aliases in the pool are
           single generic words — "United", "Sporting", "Atlético", "Union",
           "América", "Orlando" — so "united" matched straight into Bangkok
           United, Buriram United, Chippa United and ten more, all of which
           then wore Carlisle United's crest.

        2. containment must be a whole-token PREFIX. Interior and suffix hits
           are almost always different clubs that merely end the same way:
           "albion" sits inside "west bromwich albion" (Albion FC of Uruguay
           wore West Brom's crest) and "adt" inside "darmstadt 98" (ADT of Peru
           wore Darmstadt's). Requiring the prefix to end on a token boundary
           additionally rejects "port" -> "portland timbers" (Port FC of
           Thailand wore the Timbers' crest) while keeping "oxford" ->
           "oxford united".

        Anything these two rules cost is recoverable by hand in ALIAS, which is
        human-verified; a wrong crest rendered confidently is not recoverable.
        """
        def _tok_prefix(a, b):
            """True when `a` is a whole-token prefix of `b`."""
            return b.startswith(a) and (len(b) == len(a) or b[len(a)] == " ")

        # Unscoped (global) matching additionally refuses a single-token QUERY.
        # A bare "port" prefix-matches "port vale" and a bare "athletic"
        # matches "athletic club" — fine inside one country, a cross-border
        # error out of it. Single-token names still resolve through the
        # country and confederation passes, which run first.
        if multi_token_query and " " not in k:
            return None

        best = None
        for ik, (url, _) in index.items():
            if len(ik) < 4 or " " not in ik:
                continue
            if _tok_prefix(k, ik) or _tok_prefix(ik, k):
                if best is None or len(ik) > best[1]:
                    best = (url, len(ik))
        return best[0] if best else None

    def resolve(name):
        """Resolve a logo-less name, narrowest scope first.

        country -> confederation -> global, and the global step is skipped for
        ambiguous keys. Substring matching never runs globally: it was the
        biggest false-positive source (a >=4-char containment test happily
        matched "america" into "america mineiro").
        """
        k = norm(name)
        if not k:
            return None
        countries = origin_country.get(name, set())
        confs = origin_conf.get(name, set())

        for c in countries:                      # 1. same country, exact
            hit = by_country.get(c, {}).get(k)
            if hit:
                return hit[0]
        for f in confs:                          # 2. same confederation, exact
            hit = by_conf.get(f, {}).get(k)
            if hit:
                return hit[0]
        if k in norm_index and k not in ambiguous:   # 3. global, unambiguous only
            return norm_index[k][0]
        for c in countries:                      # 4. same country, substring
            hit = _sub_match(k, by_country.get(c, {}))
            if hit:
                return hit
        # 5. same confederation, substring — ONLY for names with no known
        #    country. A confederation is not a country: England and Scotland are
        #    both UEFA, so this pass let "queens park" prefix-match "queens park
        #    rangers" and drew Scotland's Queens Park in QPR's crest (caught by
        #    test_countries_do_not_share_a_crest after the 2026-08-08 rebuild
        #    brought scottish-champ back in). If a club's country IS known and
        #    step 4 found nothing in it, then a cross-border prefix hit here is a
        #    false positive by construction — the two clubs are in different
        #    countries and merely start the same way. The pass still earns its
        #    place for continental rows, which carry a confederation and no
        #    country. (2026-08-08)
        if not countries:
            for f in confs:
                hit = _sub_match(k, by_conf.get(f, {}))
                if hit:
                    return hit
        # 6. global substring, last resort — and, like step 5, only for names
        #    with no known country. Its own purpose says so: it exists for the
        #    ~600 entries from foreign_logos.json, which carry no country or
        #    confederation at all because they never appear in a payload row.
        #    A club whose country IS known has already had that country searched
        #    exactly (step 1) and by substring (step 4); reaching here means no
        #    club in its own country matches, so a global prefix hit is a
        #    different club that merely starts the same way. That is how
        #    Scotland's Queens Park — logo-less in the scottish-champ payload —
        #    reached "queens park rangers" and wore QPR's crest. (2026-08-08)
        if countries:
            return None
        return _sub_match(k, norm_index, multi_token_query=True)

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
