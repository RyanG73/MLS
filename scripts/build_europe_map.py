#!/usr/bin/env python3
"""One-off generator: real European country borders (Natural Earth 110m,
public domain, no attribution required) -> SVG paths for the homepage's
country-shaped Europe explorer. Fetches the source GeoJSON fresh each run
(not vendored — ~800KB, low-detail 110m resolution, stable public URL).
Rerun only if the country list changes; output is committed as
webapp/data/europe-map.js as a static asset, not part of the nightly
data-refresh pipeline (scripts/build_all.sh)."""
import json
import urllib.request
from pathlib import Path

SRC_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
           "master/geojson/ne_110m_admin_0_countries.geojson")
OUT = Path(__file__).resolve().parent.parent / "webapp" / "data" / "europe-map.js"

EUROPE_COUNTRIES = [
    "Albania", "Austria", "Belarus", "Belgium", "Bosnia and Herz.", "Bulgaria",
    "Croatia", "Cyprus", "Czechia", "Denmark", "Estonia", "Finland", "France",
    "Germany", "Greece", "Hungary", "Iceland", "Ireland", "Italy", "Kosovo",
    "Latvia", "Lithuania", "Luxembourg", "Moldova", "Montenegro", "Netherlands",
    "North Macedonia", "Norway", "Poland", "Portugal", "Romania", "Russia",
    "Serbia", "Slovakia", "Slovenia", "Spain", "Sweden", "Switzerland",
    "Turkey", "Ukraine", "United Kingdom",
]

# Map bounds (lon/lat) -> the visible viewBox. Russia/Turkey extend further
# east than the box; their paths are still emitted in full and simply clip at
# the SVG boundary (overflow:hidden), which is the standard way to show a
# transcontinental country's western edge without it dominating the frame.
LON_MIN, LON_MAX = -11.0, 45.0
LAT_MIN, LAT_MAX = 34.0, 71.0
W, H = 1000, 760


def project(lon, lat):
    x = (lon - LON_MIN) / (LON_MAX - LON_MIN) * W
    y = (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * H
    return round(x, 1), round(y, 1)


def ring_to_path(ring):
    pts = [project(lon, lat) for lon, lat in ring]
    d = f"M{pts[0][0]},{pts[0][1]} " + " ".join(f"L{x},{y}" for x, y in pts[1:]) + " Z"
    return d


def geometry_to_path(geom):
    t = geom["type"]
    if t == "Polygon":
        return " ".join(ring_to_path(r) for r in geom["coordinates"])
    if t == "MultiPolygon":
        return " ".join(ring_to_path(r) for poly in geom["coordinates"] for r in poly)
    raise ValueError(t)


def main():
    with urllib.request.urlopen(SRC_URL, timeout=20) as r:
        data = json.loads(r.read())
    by_name = {f["properties"]["NAME"]: f for f in data["features"]}
    missing = [n for n in EUROPE_COUNTRIES if n not in by_name]
    if missing:
        raise SystemExit(f"Missing from source data: {missing}")
    paths = {}
    for name in EUROPE_COUNTRIES:
        paths[name] = geometry_to_path(by_name[name]["geometry"])
    payload = {"viewBox": f"0 0 {W} {H}", "paths": paths}
    OUT.write_text("window.EUROPE_MAP = " + json.dumps(payload, separators=(",", ":")) + ";\n")
    sizes = {k: len(v) for k, v in paths.items()}
    print(f"wrote {OUT} · {len(paths)} countries · "
          f"{sum(sizes.values())} path chars total · "
          f"largest: {max(sizes, key=sizes.get)} ({max(sizes.values())} chars)")


if __name__ == "__main__":
    main()
