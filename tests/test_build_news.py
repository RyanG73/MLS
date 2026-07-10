"""Curated news builder (E1, 2026-07-09 feedback round 3) — routing + filters.

No network: feeds are parsed from inline XML, keywords injected directly.
"""
from scripts.build_news import _iso, _parse_feed, is_gossip, route_item

KW = {
    "epl": ["premier league", "arsenal", "manchester united"],
    "serie-a": ["serie a", "internazionale", "ac milan"],
    "mls": ["mls", "inter miami cf", "inter miami"],
}


def test_route_by_league_alias():
    assert route_item("Premier League tactical review", "", KW) == {"epl"}


def test_route_by_club_name_case_insensitive():
    assert "epl" in route_item("ARSENAL press resistance analysed", "", KW)


def test_route_can_hit_multiple_leagues():
    got = route_item("How Inter Miami mirrors AC Milan's build-up", "", KW)
    assert got == {"mls", "serie-a"}


def test_route_uses_description_too():
    got = route_item("Weekend preview", "Manchester United's midfield shape", KW)
    assert got == {"epl"}


def test_no_match_routes_nowhere():
    assert route_item("Cricket world cup latest", "", KW) == set()


def test_gossip_filter():
    assert is_gossip("Star striker linked with big-money move")
    assert is_gossip("Transfer talk: ten deals that could happen")
    assert is_gossip("Done deal! Here we go for the winger")
    assert not is_gossip("Tactical analysis: how the press broke down")
    assert not is_gossip("Injury update ahead of the derby")


RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Feed</title>
<item><title>Story &amp; headline</title><link>https://x.test/a</link>
<description>&lt;p&gt;Some &lt;b&gt;html&lt;/b&gt; body&lt;/p&gt;</description>
<pubDate>Thu, 09 Jul 2026 10:00:00 GMT</pubDate></item>
<item><title></title><link>https://x.test/skip-no-title</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Feed</title>
<entry><title>Atom story</title><link href="https://x.test/b"/>
<summary>plain</summary><updated>2026-07-09T10:00:00Z</updated></entry>
</feed>"""


def test_parse_rss_strips_html_and_drops_titleless():
    items = _parse_feed(RSS, "Src")
    assert len(items) == 1
    it = items[0]
    assert it["title"] == "Story & headline"
    assert it["desc"] == "Some html body"
    assert it["link"] == "https://x.test/a"
    assert it["source"] == "Src"


def test_parse_atom():
    items = _parse_feed(ATOM, "Src")
    assert len(items) == 1
    assert items[0]["link"] == "https://x.test/b"


def test_parse_garbage_returns_empty():
    assert _parse_feed(b"not xml at all", "Src") == []


def test_iso_handles_rfc822_and_iso_and_garbage():
    assert _iso("Thu, 09 Jul 2026 10:00:00 GMT").startswith("2026-07-09T10:00")
    assert _iso("2026-07-09T10:00:00Z").startswith("2026-07-09T10:00")
    assert _iso("someday") == ""
    assert _iso("") == ""
