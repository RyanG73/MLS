"""Canonical MLS team metadata — single source of truth.

Consolidates team name normalisation maps, conference assignments, expansion
registry, stadium coordinates, and dome flags that were previously scattered
across asa_client.py, schedule_client.py, and scripts/eval_baseline.py.

All other modules should import from here rather than maintaining their own
copies.  asa_client and schedule_client re-export the maps they previously
owned so existing import paths keep working without changes.
"""

# ─── Name normalisation ────────────────────────────────────────────────────────

# ASA full names → internal 3-letter codes (used by asa_client)
TEAM_NAME_MAP: dict[str, str] = {
    "Atlanta United": "ATL",
    "Austin FC": "ATX",
    "Charlotte FC": "CLT",
    "Chicago Fire": "CHI",
    "FC Cincinnati": "CIN",
    "Colorado Rapids": "COL",
    "Columbus Crew": "CLB",
    "D.C. United": "DC",
    "FC Dallas": "DAL",
    "Houston Dynamo": "HOU",
    "Inter Miami CF": "MIA",
    "LA Galaxy": "LAG",
    "Los Angeles FC": "LAFC",
    "Minnesota United": "MIN",
    "CF Montréal": "MTL",
    "Nashville SC": "NSH",
    "New England Revolution": "NE",
    "New York City FC": "NYC",
    "New York Red Bulls": "NYRB",
    "Orlando City": "ORL",
    "Philadelphia Union": "PHI",
    "Portland Timbers": "POR",
    "Real Salt Lake": "RSL",
    "San Jose Earthquakes": "SJ",
    "Seattle Sounders": "SEA",
    "Sporting Kansas City": "SKC",
    "St. Louis City SC": "STL",
    "Toronto FC": "TOR",
    "Vancouver Whitecaps": "VAN",
    "San Diego FC": "SD",
}

# ESPN display names → internal codes (used by schedule_client / odds_client)
ESPN_TO_TEAM: dict[str, str] = {
    "Atlanta United FC": "ATL",
    "Austin FC": "ATX",
    "Charlotte FC": "CLT",
    "Chicago Fire FC": "CHI",
    "FC Cincinnati": "CIN",
    "Colorado Rapids": "COL",
    "Columbus Crew": "CLB",
    "D.C. United": "DC",
    "FC Dallas": "DAL",
    "Houston Dynamo FC": "HOU",
    "Inter Miami CF": "MIA",
    "LA Galaxy": "LAG",
    "Los Angeles FC": "LAFC",
    "Minnesota United FC": "MIN",
    "CF Montréal": "MTL",
    "Nashville SC": "NSH",
    "New England Revolution": "NE",
    "New York City FC": "NYC",
    "New York Red Bulls": "NYRB",
    "Orlando City SC": "ORL",
    "Philadelphia Union": "PHI",
    "Portland Timbers": "POR",
    "Real Salt Lake": "RSL",
    "San Jose Earthquakes": "SJ",
    "Seattle Sounders FC": "SEA",
    "Sporting Kansas City": "SKC",
    "St. Louis City SC": "STL",
    "Toronto FC": "TOR",
    "Vancouver Whitecaps FC": "VAN",
    "San Diego FC": "SD",
}

# ─── Conference assignments ────────────────────────────────────────────────────

CONFERENCE_MAP: dict[str, str] = {
    "ATL": "E", "CLT": "E", "CHI": "E", "CIN": "E", "CLB": "E",
    "DC": "E",  "MIA": "E", "MTL": "E", "NSH": "E", "NE": "E",
    "NYC": "E", "NYRB": "E", "ORL": "E", "PHI": "E", "TOR": "E",
    "ATX": "W", "COL": "W", "DAL": "W", "HOU": "W", "LAG": "W",
    "LAFC": "W", "MIN": "W", "POR": "W", "RSL": "W", "SJ": "W",
    "SEA": "W", "SKC": "W", "STL": "W", "VAN": "W", "SD": "W",
}

# ─── Expansion team registry ──────────────────────────────────────────────────
# Maps internal team code → first MLS season

FIRST_SEASON: dict[str, int] = {
    "ATL": 2017, "ATX": 2021, "CLT": 2022, "CIN": 2019, "MIA": 2020,
    "NSH": 2020, "STL": 2023, "SD": 2025,
}

# ─── Stadium coordinates (lat, lon) keyed by ASA team_id ─────────────────────
# Used for travel-distance and timezone-shift features in eval_baseline.py.
# ASA team IDs are opaque hex strings, not the short codes above.

TEAM_COORDS: dict[str, tuple[float, float]] = {
    "0KPqjA456v": (37.351, -121.925),   # San Jose
    "19vQ2095K6": (42.091,  -71.264),   # New England
    "4wM42l4qjB": (33.864, -118.261),   # LA Galaxy
    "9z5k7Yg5A3": (39.834,  -75.380),   # Philadelphia
    "APk5LGOMOW": (45.564,  -73.551),   # CF Montréal
    "EKXMeX3Q64": (38.868,  -77.013),   # D.C. United
    "KAqBN0Vqbg": (33.755,  -84.401),   # Atlanta United
    "NPqxKXZ59d": (35.226,  -80.853),   # Charlotte
    "NWMWlBK5lz": (39.109,  -84.521),   # FC Cincinnati
    "Vj58weDM8n": (40.829,  -73.926),   # NYCFC
    "WBLMvYAQxe": (45.521, -122.692),   # Portland
    "X0Oq66zq6D": (41.862,  -87.617),   # Chicago
    "YgOMngl5zy": (29.753,  -95.351),   # Houston
    "Z2vQ1xlqrA": (39.123,  -94.824),   # Sporting KC
    "a2lqR4JMr0": (40.583, -111.893),   # Real Salt Lake
    "a2lqRX2Mr0": (40.737,  -74.150),   # NY Red Bulls
    "eVq3ya6MWO": (34.013, -118.285),   # LAFC
    "gpMOLwl5zy": (30.387,  -97.719),   # Austin FC
    "jYQJ19EqGR": (47.595, -122.332),   # Seattle
    "jYQJ8EW5GR": (28.541,  -81.389),   # Orlando
    "kRQabn8MKZ": (43.633,  -79.419),   # Toronto
    "kRQand1MKZ": (44.953,  -93.165),   # Minnesota
    "kaDQ0wRqEv": (33.864, -118.261),   # LA Galaxy (alt ID)
    "lgpMOvnQzy": (49.277, -123.112),   # Vancouver
    "mKAqBBmqbg": (33.155,  -97.116),   # FC Dallas
    "mvzqoLZQap": (39.968,  -83.018),   # Columbus
    "pzeQZ6xQKw": (39.805, -104.892),   # Colorado
    "vzqoOgNqap": (36.130,  -86.766),   # Nashville
    "wvq9B9wQWn": (38.633,  -90.212),   # St. Louis
    "zeQZBOzQKw": (32.707, -117.120),   # San Diego
    "zeQZkL1MKw": (26.170,  -80.188),   # Inter Miami
}

# ─── Dome stadiums (weather not applicable) ────────────────────────────────────
# Retractable roof / climate-controlled — Open-Meteo data is irrelevant.
# Keys are ASA team IDs.

DOME_TEAM_IDS: frozenset = frozenset({
    "KAqBN0Vqbg",  # Atlanta United (Mercedes-Benz Stadium)
    "lgpMOvnQzy",  # Vancouver Whitecaps (BC Place)
})

