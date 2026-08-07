"""Contract tests for scripts/build_static_pages.py (launch plan C4).

Runs the real generator against the committed payloads into a tmp tree
(data/ symlinked, never written), then asserts the SEO contract: unique
titles, valid JSON-LD, canonical/directory agreement, well-formed sitemap,
and escaping of payload-sourced strings.
"""
from __future__ import annotations

import json
import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.build_static_pages import club_slug, main as build_main, pct
from scripts.build_share_cards import card_og
from scripts.payload_utils import read_js_payload
from server.surface_contract import club_surface_contract

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


def _club_pages(built: Path) -> dict[tuple[str, str], str]:
    return {
        (p.parents[2].name, p.parent.name): p.read_text()
        for p in sorted((built / "leagues").glob("*/clubs/*/index.html"))
    }


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


def test_every_forecasted_club_has_a_competition_scoped_page(built):
    pages = _club_pages(built)
    expected = set()
    for lid in _pages(built):
        payload = read_js_payload(built / "data" / f"{lid}.js")
        expected.update(
            (lid, club_slug(row["team"]))
            for row in payload.get("standings") or [] if row.get("team")
        )
        expected.update(
            (lid, club_slug(team))
            for game in payload.get("games") or []
            for team in (game.get("home"), game.get("away")) if team
        )
    assert set(pages) == expected
    assert len(pages) > 1_000


def test_club_pages_have_unique_metadata_and_self_canonicals(built):
    titles = set()
    for (lid, slug), html_txt in _club_pages(built).items():
        title = re.search(r"<title>([^<]+)</title>", html_txt).group(1)
        assert title not in titles, f"duplicate club title: {title}"
        titles.add(title)
        desc = re.search(r'name="description" content="([^"]+)"', html_txt)
        assert desc and len(desc.group(1)) > 60, f"{lid}/{slug}: thin description"
        canon = re.search(r'rel="canonical" href="([^"]+)"', html_txt).group(1)
        assert canon == f"{SITE}/leagues/{lid}/clubs/{slug}/"


def test_club_pages_are_useful_and_structured(built):
    inter_miami = _club_pages(built)[("mls", "inter-miami-cf")]
    payload = read_js_payload(built / "data" / "mls.js")
    row = next(
        item for item in payload["standings"]
        if item["team"] == "Inter Miami CF")
    artifact_path = (
        REPO / "data" / "team_intelligence" / "mls"
        / f"{row['team_id'].replace(':', '_')}.json"
    )
    contract = club_surface_contract(json.loads(artifact_path.read_text()))
    assert contract["team_id"] == row["team_id"]
    assert contract["team"] == row["team"]
    assert contract["generated"] == payload["generated"]
    assert contract["current_probability_pct"] == row[
        contract["target_metric"]]
    assert "Expected finish" in inter_miami
    assert "Upcoming matches" in inter_miami
    assert "Recent results" in inter_miami
    assert "Track Inter Miami CF with Club Watch" in inter_miami
    assert "Open the free interactive Inter Miami CF dashboard" in inter_miami
    assert "club_page_view" in inter_miami
    assert "track_club" in inter_miami
    assert row["team_id"] in inter_miami
    assert payload["generated"][:10] in inter_miami
    assert html.escape(pct(row["playoff"])) in inter_miami
    blocks = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>',
        inter_miami, re.DOTALL)
    graph = json.loads(blocks[0])["@graph"]
    assert {"BreadcrumbList", "SportsTeam", "Dataset"} <= {
        node["@type"] for node in graph
    }


def test_league_tables_link_to_club_canonicals(built):
    mls = _pages(built)["mls"]
    assert 'href="/leagues/mls/clubs/inter-miami-cf/"' in mls
    epl = _pages(built)["epl"]
    assert 'href="/leagues/epl/clubs/manchester-city/"' in epl


def test_club_slug_is_readable_and_normalized():
    assert club_slug("CF Montréal") == "cf-montreal"
    assert club_slug("St. Patrick's Athletic") == "st-patrick-s-athletic"
    assert club_slug("  Adelaide United ") == "adelaide-united"


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
    # Every league page is present; the weekly recap, open-data, and World Cup
    # on-ramp pages are included when their inputs exist (they do here). Every
    # generated club page is present too.
    league_locs = {f"{SITE}/leagues/{lid}/" for lid in _pages(built)}
    assert league_locs <= set(locs[2:])
    club_locs = {
        f"{SITE}/leagues/{lid}/clubs/{slug}/"
        for lid, slug in _club_pages(built)
    }
    assert club_locs <= set(locs[2:])
    dated_weekly = re.compile(rf"^{re.escape(SITE)}/weekly/\d{{4}}-\d{{2}}-\d{{2}}/$")
    non_league = {loc for loc in set(locs[2:]) - league_locs - club_locs
                  if not dated_weekly.match(loc)}
    assert non_league <= {
        f"{SITE}/weekly/", f"{SITE}/open-data/", f"{SITE}/global-elo/",
        f"{SITE}/after-the-world-cup/", f"{SITE}/football-forecasts/"}
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


def test_static_pages_use_honest_data_state_labels(built):
    all_html = list(_pages(built).values()) + list(_club_pages(built).values())
    assert all('class="badge">live</span>' not in page for page in all_html)
    assert any('class="badge">full forecast</span>' in page for page in all_html)
    assert any('class="badge">pre-season</span>' in page for page in all_html)


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
    for key, html_txt in _club_pages(built).items():
        assert len(html_txt) < 80_000, f"{key}: club page too heavy"


def test_no_spa_scripts_leak_into_static_pages(built):
    for lid, html_txt in _pages(built).items():
        assert "document.write" not in html_txt
        assert "LEAGUE_DATA" not in html_txt
    for key, html_txt in _club_pages(built).items():
        assert "document.write" not in html_txt, key
        assert "LEAGUE_DATA" not in html_txt, key


def test_open_data_page_and_csv_exports(built):
    idx = built / "open-data" / "index.html"
    assert idx.exists()
    txt = idx.read_text()
    assert "Please credit" in txt            # attribution terms present
    assert "DataCatalog" in txt              # JSON-LD
    csvs = list((built / "exports").glob("*.csv"))
    assert csvs, "expected per-league CSV exports"
    # every download link resolves to a generated file
    hrefs = re.findall(r'href="(/exports/[^"]+\.csv)"', txt)
    assert hrefs
    for h in hrefs:
        assert (built / h.lstrip("/")).exists(), f"missing export: {h}"
    header = csvs[0].read_text().splitlines()[0]
    assert header.startswith("rank,team,played,points,proj_points")


def test_data_dir_payloads_untouched_by_generator(built):
    # The generator must never write into webapp/data/ (the SPA payloads);
    # the open-data index lives at /open-data/, not /data/.
    assert not (built / "data" / "index.html").exists()


def test_public_acquisition_pages_and_rss_are_forecast_only(built):
    paths = (
        list((built / "leagues").glob("*/index.html"))
        + [built / "leagues" / "index.html",
           built / "open-data" / "index.html",
           built / "football-forecasts" / "index.html",
           built / "weekly" / "index.html"]
    )
    banned = re.compile(
        r"\b(odds|bet|betting|edge|kelly|stake|staking|bookmaker|sportsbook|"
        r"wager|roi|clv|market)\b", re.IGNORECASE)
    for path in paths:
        if path.exists():
            assert not banned.search(path.read_text()), path

    feed = built / "forecast-feed.xml"
    assert feed.exists()
    root = ET.parse(feed).getroot()
    assert root.tag == "rss"
    assert root.find("./channel/title").text == "Entenser football forecasts"
    assert not banned.search(feed.read_text())


def test_local_league_names_support_european_search(built):
    segunda = built / "leagues" / "segunda" / "index.html"
    if segunda.exists():
        assert "Segunda División" in segunda.read_text()
    forecast = built / "football-forecasts" / "index.html"
    assert forecast.exists()
    assert "Eerste Divisie" in forecast.read_text()
    assert "National League" in forecast.read_text()


def test_default_og_card_copy_is_forecast_only():
    html_txt = card_og("")
    banned = re.compile(
        r"\b(odds|bet|betting|edge|kelly|stake|staking|bookmaker|sportsbook|"
        r"wager|roi|clv|market)\b", re.IGNORECASE)
    assert not banned.search(html_txt)
    assert "70+ competitions" in html_txt


# ── roadmap 1.5: dated /weekly/<date>/ recap pages from the F-3 archive ─────────

def test_dated_weekly_pages_built_from_archive(tmp_path):
    """Each archived recap becomes /weekly/<date>/, is in the sitemap with a
    canonical matching its directory, and the latest /weekly/ links to it."""
    root = tmp_path / "site"
    root.mkdir()
    (root / "leagues.js").write_text((WEBAPP / "leagues.js").read_text())
    (root / "data").symlink_to(WEBAPP / "data")
    archive = tmp_path / "weekly-archive"
    archive.mkdir()
    recap = {"status": "ok", "generated": "2026-07-12 10:00 UTC",
             "week_label": "Week of Jul 12", "headline": "Test week recap"}
    (archive / "2026-07-12.json").write_text(json.dumps(recap))

    assert build_main(["--out", str(root), "--site", SITE,
                       "--weekly-archive", str(archive)]) == 0

    dated = root / "weekly" / "2026-07-12" / "index.html"
    assert dated.exists()
    html_txt = dated.read_text()
    canon = re.search(r'rel="canonical" href="([^"]+)"', html_txt).group(1)
    assert canon == f"{SITE}/weekly/2026-07-12/"

    root_xml = ET.parse(root / "sitemap.xml").getroot()
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [u.find(f"{ns}loc").text for u in root_xml]
    assert f"{SITE}/weekly/2026-07-12/" in locs

    # the latest /weekly/ page links to the dated archive entry
    latest = (root / "weekly" / "index.html").read_text()
    assert "/weekly/2026-07-12/" in latest


# ── Club Watch paths (P4, 2026-08-01) ────────────────────────────────────────
# The acquisition layer's door into the paid product. Before this, club pages
# carried a CTA only after ~260 words of tables (y=1650 at 375px) and league
# pages — the higher-volume search surface — carried none and never named the
# product.

def test_league_pages_with_standings_offer_a_club_watch_path(built):
    pages = _pages(built)
    with_rows = {lid: h for lid, h in pages.items() if 'id="cwChips"' in h}
    # Knockout competitions with no standings degrade cleanly to no row.
    assert len(with_rows) >= len(pages) - 2, (
        f"only {len(with_rows)} of {len(pages)} league pages carry the row")
    epl = pages["epl"]
    assert "Follow a club through the season" in epl
    assert 'class="cw-chip"' in epl
    assert "league=intel" in epl and "track=1" in epl


def test_club_pages_carry_the_watch_cta_before_the_tables(built):
    for (lid, slug), page in list(_club_pages(built).items())[:40]:
        assert 'id="clubWatchTop"' in page, f"{lid}/{slug} missing above-fold CTA"
        assert 'id="clubWatchCTA"' in page, f"{lid}/{slug} missing footer CTA"
        top_at = page.index('id="clubWatchTop"')
        table_at = page.find("<table")
        if table_at != -1:
            assert top_at < table_at, (
                f"{lid}/{slug}: watch CTA renders after the first table")


def test_club_watch_paths_use_one_tracking_url_shape(built):
    """Both CTAs on a club page must point at the same intent URL."""
    page = _club_pages(built)[("epl", "arsenal")]
    hrefs = re.findall(r'id="clubWatch(?:Top|CTA)" href="([^"]+)"', page)
    assert len(hrefs) == 2 and hrefs[0] == hrefs[1], hrefs


def test_club_watch_copy_obeys_the_claim_matrix(built):
    """Free boundary stated; no alerts, email, or profit promise anywhere."""
    epl = _pages(built)["epl"]
    assert "stay free" in epl
    banned = ["in your inbox", "email alert", "guaranteed", "profit",
              "beat the market", "picks"]
    lowered = epl.lower()
    for phrase in banned:
        assert phrase not in lowered, f"banned claim {phrase!r} on league page"


# ── /global-elo/ — the named cross-league strength scale (P6) ─────────────────
# Naming a number creates a claim surface. These lock the page to what the
# grading record actually supports, and keep its figures derived from the live
# payloads rather than written down where they can silently go stale.
# Shipped as /crossbar/ on 2026-08-01, renamed 2026-08-06.


def test_retired_crossbar_url_still_resolves_to_global_elo(built):
    """The old URL must not 404 — it shipped everywhere for five days.

    /crossbar/ was in every league-page footer, every club page, the sitemap and
    the RSS feed while the scale carried that name. GitHub Pages serves this
    site, so there is no server-side redirect to configure and the forward has
    to be a page. It carries a canonical to the new URL so the indexed one
    consolidates rather than competing, and it must stay OUT of the sitemap —
    a sitemap lists destinations, not forwarding addresses.
    """
    page = (built / "crossbar" / "index.html").read_text()
    assert re.search(r'rel="canonical" href="([^"]+)"', page).group(1) == \
        f"{SITE}/global-elo/"
    assert 'http-equiv="refresh"' in page and "/global-elo/" in page
    assert "noindex" in page
    assert '<a href="/global-elo/">' in page, "needs a followable link, not only a meta refresh"
    root = ET.parse(built / "sitemap.xml").getroot()
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [u.find(f"{ns}loc").text for u in root]
    assert f"{SITE}/crossbar/" not in locs, "a redirect stub must not be in the sitemap"

def test_global_elo_page_is_built_and_self_canonical(built):
    page = (built / "global-elo" / "index.html").read_text()
    canon = re.search(r'rel="canonical" href="([^"]+)"', page).group(1)
    assert canon == f"{SITE}/global-elo/"
    assert "<h1>Global ELO</h1>" in page
    ld = json.loads(re.search(
        r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
    assert ld["@type"] == "DefinedTerm" and ld["name"] == "Global ELO"


def test_global_elo_page_is_in_the_sitemap(built):
    root = ET.parse(built / "sitemap.xml").getroot()
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [u.find(f"{ns}loc").text for u in root]
    assert f"{SITE}/global-elo/" in locs


def test_global_elo_figures_are_derived_from_the_payloads(built):
    """The headline count and the table must match what the site publishes."""
    page = (built / "global-elo" / "index.html").read_text()
    rated = []
    for p in sorted((built / "data").glob("*.js")):
        payload = read_js_payload(p)
        if not isinstance(payload, dict):
            continue
        rated += [s["global_elo"] for s in (payload.get("standings") or [])
                  if s.get("global_elo") is not None]
    assert rated, "no rated clubs found in payloads"
    assert f"{len(rated):,} clubs" in page
    assert f"{max(rated):,}" in page


def test_global_elo_table_is_sorted_by_the_scale(built):
    page = (built / "global-elo" / "index.html").read_text()
    vals = [int(v.replace(",", "")) for v in
            re.findall(r'<td class="tm">[^<]*</td><td class="tm">[^<]*</td><td>([\d,]+)</td>', page)]
    assert len(vals) >= 4, vals
    assert vals == sorted(vals, reverse=True), vals


def test_global_elo_page_makes_no_accuracy_or_betting_claim(built):
    """docs/paid-claim-matrix.md: no profit, edge, picks or staking language,
    and no accuracy assertion the public grading record does not support."""
    text = re.sub(r"<[^>]+>", " ", (built / "global-elo" / "index.html").read_text()).lower()
    for banned in ("guaranteed", "profit", "beat the market", "picks", "staking",
                   "most accurate", "best model", "sharp", "value bet"):
        assert banned not in text, f"global elo page makes a banned claim: {banned!r}"
    # And it must state the market-blind invariant plainly — that is the point.
    assert "not built from bookmaker odds" in text


def test_global_elo_page_states_its_own_limits(built):
    text = (built / "global-elo" / "index.html").read_text().lower()
    assert "where it is weakest" in text
    assert "between confederations" in text


def test_club_pages_name_and_link_the_scale(built):
    for (lid, slug), page in list(_club_pages(built).items())[:30]:
        if "global_elo" not in page and 'class="k">Global ELO<' not in page:
            continue
        assert 'class="k">Global ELO<' in page, f"{lid}/{slug} still labels the metric Global ELO"
        assert 'href="/global-elo/"' in page, f"{lid}/{slug} does not link the explainer"
