"""Contract tests for scripts/build_static_pages.py (launch plan C4).

Runs the real generator against the committed payloads into a tmp tree
(data/ symlinked, never written), then asserts the SEO contract: unique
titles, valid JSON-LD, canonical/directory agreement, well-formed sitemap,
and escaping of payload-sourced strings.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.build_static_pages import main as build_main, pct
from scripts.payload_utils import read_js_payload

REPO = Path(__file__).resolve().parent.parent
WEBAPP = REPO / "webapp"
SITE = "https://entenser.com"


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    """Generator output in an isolated tree (real payloads, symlinked)."""
    root = tmp_path_factory.mktemp("static_pages")
    (root / "leagues.js").write_text((WEBAPP / "leagues.js").read_text())
    (root / "data").symlink_to(WEBAPP / "data")
    assert build_main(["--out", str(root), "--site", SITE]) == 0
    return root


def _pages(built: Path) -> dict[str, str]:
    return {p.parent.name: p.read_text()
            for p in sorted((built / "leagues").glob("*/index.html"))}


def test_every_nonplaceholder_league_has_a_page(built):
    registry = read_js_payload(built / "leagues.js")
    expected = set()
    for lg in registry:
        d = read_js_payload(built / "data" / f"{lg['id']}.js")
        if d is not None and d.get("status") != "placeholder":
            expected.add(lg["id"])
    assert set(_pages(built)) == expected
    assert (built / "leagues" / "index.html").exists()


def test_titles_unique_and_descriptions_present(built):
    titles: dict[str, str] = {}
    for lid, html_txt in _pages(built).items():
        title = re.search(r"<title>([^<]+)</title>", html_txt).group(1)
        assert title not in titles.values(), f"duplicate title: {title}"
        titles[lid] = title
        desc = re.search(r'name="description" content="([^"]+)"', html_txt)
        assert desc and len(desc.group(1)) > 40, f"{lid}: thin description"


def test_canonical_matches_directory(built):
    for lid, html_txt in _pages(built).items():
        canon = re.search(r'rel="canonical" href="([^"]+)"', html_txt).group(1)
        assert canon == f"{SITE}/leagues/{lid}/"


def test_jsonld_parses_and_has_breadcrumb_and_dataset(built):
    for lid, html_txt in _pages(built).items():
        blocks = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            html_txt, re.DOTALL)
        assert blocks, f"{lid}: no JSON-LD"
        graph = json.loads(blocks[0])["@graph"]
        types = {node["@type"] for node in graph}
        assert {"BreadcrumbList", "Dataset"} <= types, f"{lid}: {types}"
        for node in graph:
            if node["@type"] == "SportsEvent":
                assert node.get("startDate"), f"{lid}: SportsEvent w/o date"


def test_payload_strings_are_escaped(built):
    # Raw & in a club name (e.g. "Brighton & Hove Albion") must arrive as
    # &amp;; a bare "& " sequence outside entities means escaping was missed.
    bare_amp = re.compile(r"& ")
    for lid, html_txt in _pages(built).items():
        assert not bare_amp.search(html_txt), f"{lid}: unescaped ampersand"


def test_sitemap_wellformed_and_complete(built):
    root = ET.parse(built / "sitemap.xml").getroot()
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [u.find(f"{ns}loc").text for u in root]
    assert locs[0] == f"{SITE}/"
    assert locs[1] == f"{SITE}/leagues/"
    # Every league page is present; the weekly recap page is included when
    # webapp/data/weekly.js exists (it does in the committed tree).
    league_locs = {f"{SITE}/leagues/{lid}/" for lid in _pages(built)}
    assert league_locs <= set(locs[2:])
    assert set(locs[2:]) - league_locs <= {f"{SITE}/weekly/"}
    for u in root:
        lm = u.find(f"{ns}lastmod")
        assert lm is not None and re.fullmatch(r"\d{4}-\d{2}-\d{2}", lm.text)


def test_data_status_notes_present_on_exception_leagues(built):
    pages = _pages(built)
    for lid, needle in [("canadian-pl", "Archive"),
                        ("k-league-1", "Archive"),
                        ("poland-ekstraklasa", "Results only"),
                        ("finland-veikkausliiga", "Results only")]:
        if lid in pages:
            assert needle in pages[lid], f"{lid}: missing '{needle}' note"


def test_pct_formatting():
    assert pct(45.2) == "45.2%"
    assert pct(45.0) == "45%"
    assert pct(0.4) == "<1%"
    assert pct(99.96) == ">99%"
    assert pct(0) == "0%"
    assert pct(None) == "–"


def test_pages_are_lightweight(built):
    for lid, html_txt in _pages(built).items():
        assert len(html_txt) < 80_000, f"{lid}: page too heavy"


def test_no_spa_scripts_leak_into_static_pages(built):
    for lid, html_txt in _pages(built).items():
        assert "document.write" not in html_txt
        assert "LEAGUE_DATA" not in html_txt
