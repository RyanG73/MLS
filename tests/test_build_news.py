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


def test_nonfootball_story_with_club_alias_is_rejected():
    assert route_item("Arsenal cricket club wins county final", "", KW) == set()


def test_short_alias_does_not_match_inside_an_unrelated_word():
    assert route_item("New HTMLScriptElement browser API", "", KW) == set()


"""Regression: the three real items that reached the live home rail.

Observed on https://entenser.com 2026-08-01 under football league labels —
darts as "EFL League One", cricket as "Premier League", rugby league as
"Ligue 1". The router already rejected all three; the home payload was simply
never re-aggregated after build_news rewrote news/*.js (fixed in
daily_build.sh). These lock the routing half so a keyword change cannot
quietly re-admit them.
"""
LIVE_KW = {
    "epl": ["premier league", "arsenal", "chelsea"],
    "efl-league-one": ["efl league one", "barnsley", "bolton wanderers"],
    "ligue-1": ["ligue 1", "monaco", "paris saint germain"],
    "mls": ["mls", "chicago fire"],
}


def test_darts_headline_routes_nowhere():
    assert route_item(
        "Price to Littler: Don't underestimate me! | 'If I play my A game, "
        "I will win!", "", LIVE_KW) == set()


def test_cricket_headline_routes_nowhere():
    assert route_item(
        "SunRisers edge Brave as Ravindra dazzles for Fire against MI London",
        "", LIVE_KW) == set()


def test_rugby_league_headline_routes_nowhere():
    assert route_item(
        "England women ramp up Rugby League World Cup preparations with win "
        "in France", "", LIVE_KW) == set()


def test_darts_story_is_rejected_even_when_it_names_a_club():
    """The dangerous shape: a darts item that does mention a real club.

    Before darts joined NON_FOOTBALL_SIGNAL this routed to epl on "Arsenal".
    """
    assert route_item(
        "Littler wins the darts Matchplay as Arsenal players watch on",
        "", LIVE_KW) == set()


def test_football_story_survives_a_non_football_word():
    """The guard must not eat legitimate football coverage."""
    assert route_item(
        "Arsenal's new striker was a promising cricket player at school",
        "Premier League transfer window analysis", LIVE_KW) == {"epl"}


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
