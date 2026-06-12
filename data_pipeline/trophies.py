#!/usr/bin/env python3
"""
MLS trophy winners 2013–2025 for the dashboard History tab annotations.

Verified against Wikipedia (MLS Cup, Supporters' Shield, U.S. Open Cup, MLS Cup
finalists). "Conference" = a year's two MLS Cup finalists (each won its
conference championship). Keyed by a normalized team name so it survives the
"FC"/"SC"/punctuation variation between sources and the ASA team registry.
"""

import re

# year -> winner (MLS Cup, Shield, US Open Cup)
MLS_CUP = {
    2013: "Sporting Kansas City", 2014: "LA Galaxy", 2015: "Portland Timbers",
    2016: "Seattle Sounders FC", 2017: "Toronto FC", 2018: "Atlanta United FC",
    2019: "Seattle Sounders FC", 2020: "Columbus Crew", 2021: "New York City FC",
    2022: "Los Angeles FC", 2023: "Columbus Crew", 2024: "LA Galaxy",
    2025: "Inter Miami CF",
}
SHIELD = {
    2013: "New York Red Bulls", 2014: "Seattle Sounders FC", 2015: "New York Red Bulls",
    2016: "FC Dallas", 2017: "Toronto FC", 2018: "New York Red Bulls",
    2019: "Los Angeles FC", 2020: "Philadelphia Union", 2021: "New England Revolution",
    2022: "Los Angeles FC", 2023: "FC Cincinnati", 2024: "Inter Miami CF",
    2025: "Philadelphia Union",
}
US_OPEN_CUP = {  # 2020, 2021 not held (COVID)
    2013: "D.C. United", 2014: "Seattle Sounders FC", 2015: "Sporting Kansas City",
    2016: "FC Dallas", 2017: "Sporting Kansas City", 2018: "Houston Dynamo FC",
    2019: "Atlanta United FC", 2022: "Orlando City SC", 2023: "Houston Dynamo FC",
    2024: "Los Angeles FC", 2025: "Nashville SC",
}
# year -> (winner, runner-up) — both are conference champions
_CUP_FINALISTS = {
    2013: ("Sporting Kansas City", "Real Salt Lake"),
    2014: ("LA Galaxy", "New England Revolution"),
    2015: ("Portland Timbers", "Columbus Crew"),
    2016: ("Seattle Sounders FC", "Toronto FC"),
    2017: ("Toronto FC", "Seattle Sounders FC"),
    2018: ("Atlanta United FC", "Portland Timbers"),
    2019: ("Seattle Sounders FC", "Toronto FC"),
    2020: ("Columbus Crew", "Seattle Sounders FC"),
    2021: ("New York City FC", "Portland Timbers"),
    2022: ("Los Angeles FC", "Philadelphia Union"),
    2023: ("Columbus Crew", "Los Angeles FC"),
    2024: ("LA Galaxy", "New York Red Bulls"),
    2025: ("Inter Miami CF", "Vancouver Whitecaps FC"),
}


def _norm(name: str) -> str:
    """Lowercase, drop punctuation and the FC/SC/CF qualifiers, strip spaces."""
    n = re.sub(r"[^a-z0-9 ]", "", (name or "").lower())
    n = re.sub(r"\b(fc|sc|cf)\b", "", n)
    return re.sub(r"\s+", "", n)


# Build normalized name -> list of {year, type}
_TROPHIES: dict = {}
def _add(name, year, kind):
    _TROPHIES.setdefault(_norm(name), []).append({"year": year, "type": kind})

for _y, _t in MLS_CUP.items():
    _add(_t, _y, "MLS Cup")
for _y, _t in SHIELD.items():
    _add(_t, _y, "Supporters' Shield")
for _y, _t in US_OPEN_CUP.items():
    _add(_t, _y, "US Open Cup")
for _y, (_w, _r) in _CUP_FINALISTS.items():
    _add(_w, _y, "Conference")
    _add(_r, _y, "Conference")


def trophies_for(team_name: str) -> list:
    """All trophies for a team (matched by normalized name), year-sorted."""
    return sorted(_TROPHIES.get(_norm(team_name), []),
                  key=lambda t: (t["year"], t["type"]))
