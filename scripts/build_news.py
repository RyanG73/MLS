#!/usr/bin/env python3
"""Bake per-league curated news feeds → webapp/data/news/<league>.js.

RSS is CORS-blocked in the browser, so the client can only live-fetch ESPN's
open API; every other source is fetched here at build time and merged
client-side (webapp/index.html renderNews). Curated for news / tactical
analysis / analytics — transfer-gossip items are dropped by keyword.

Routing: an item lands in a league's feed when its title+description mention
the league by name or any club currently in that league's payload standings
(so the keyword set maintains itself as payloads rebuild).

Failure policy: a dead feed is a warning, never a fatal — the nightly build
must not fail because one paper changed its RSS path.

Usage: python3 scripts/build_news.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from scripts.payload_utils import write_js_payload  # noqa: E402

# Full browser UA: several outlets (GFFN et al.) 403 anything with "bot" in it.
_HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
OUT_DIR = Path("webapp/data/news")

# English-language, analysis-leaning sources: four global/England outlets plus
# one per big European country (2026-07-09 feedback round).
FEEDS = [
    {"name": "The Athletic",   "url": "https://www.nytimes.com/athletic/rss/football/"},
    {"name": "The Guardian",   "url": "https://www.theguardian.com/football/rss"},
    {"name": "BBC Sport",      "url": "https://feeds.bbci.co.uk/sport/football/rss.xml"},
    {"name": "Sky Sports",     "url": "https://www.skysports.com/rss/12040"},
    {"name": "Football Italia", "url": "https://football-italia.net/feed/"},
    {"name": "Get French Football News", "url": "https://www.getfootballnewsfrance.com/feed/"},
    {"name": "DW Sports", "url": "https://rss.dw.com/xml/rss-en-sports"},
    {"name": "Football España", "url": "https://www.football-espana.net/feed/"},
]

# Not gossip-bait: drop items that are transfer-rumour churn rather than news.
GOSSIP = re.compile(
    r"rumou?rs?|gossip|linked with|transfer news live|transfer talk|paper talk"
    r"|reportedly (?:eyeing|keen|interested|targeting)|here we go|done deal",
    re.I)

# League-name aliases (lowercase substring match). Club names are added from
# the live payloads at runtime — see _league_keywords().
LEAGUE_ALIASES: dict[str, list[str]] = {
    "epl": ["premier league"],
    "championship": ["efl championship"],
    "league-one": ["league one"],
    "league-two": ["league two"],
    "la-liga": ["la liga", "laliga"],
    "segunda": ["segunda división", "laliga 2"],
    "serie-a": ["serie a"],
    "serie-b": ["serie b"],
    "bundesliga": ["bundesliga"],
    "bundesliga-2": ["2. bundesliga"],
    "ligue-1": ["ligue 1"],
    "ligue-2": ["ligue 2"],
    "eredivisie": ["eredivisie"],
    "primeira": ["primeira liga", "liga portugal"],
    "super-lig": ["süper lig", "super lig"],
    "scottish-prem": ["scottish premiership"],
    "belgian-pro": ["belgian pro league", "jupiler"],
    "greek-super": ["greek super league"],
    "mls": ["mls", "major league soccer"],
    "liga-mx": ["liga mx"],
    "nwsl": ["nwsl"],
    "usl-championship": ["usl championship"],
    "ucl": ["champions league"],
    "europa": ["europa league"],
    "conference": ["conference league"],
}

_STOP_CLUBS = {"arsenal", "chelsea"}  # none — placeholder kept empty on purpose


def is_gossip(title: str, desc: str = "") -> bool:
    return bool(GOSSIP.search(f"{title} {desc}"))


def _payload_teams(path: Path) -> list[str]:
    try:
        txt = path.read_text()
        d = json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))
        return [s["team"] for s in d.get("standings", []) if s.get("team")]
    except Exception:
        return []


def _league_keywords(webapp_data: Path = Path("webapp/data")) -> dict[str, list[str]]:
    """League id → lowercase keywords (aliases + current club names ≥5 chars).

    Club names shorter than 5 chars ("Roma" is 4) are kept only when they are
    multi-word — single short tokens false-positive too easily in headlines.
    """
    kw: dict[str, list[str]] = {}
    for lid, aliases in LEAGUE_ALIASES.items():
        words = list(aliases)
        for team in _payload_teams(webapp_data / f"{lid}.js"):
            t = team.lower().strip()
            if len(t) >= 5 or " " in t:
                words.append(t)
        kw[lid] = words
    return kw


def route_item(title: str, desc: str, keywords: dict[str, list[str]]) -> set[str]:
    """League ids whose keywords appear in the item's title+description."""
    hay = f" {title} {desc} ".lower()
    return {lid for lid, words in keywords.items()
            if any(w in hay for w in words)}


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _parse_feed(content: bytes, source: str) -> list[dict]:
    """Parse RSS 2.0 or Atom into unified item dicts. Bad XML → []."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    # RSS 2.0 (bare <item>) and RSS 1.0/RDF (namespaced item, e.g. DW)
    rss_items = [el for el in root.iter()
                 if el.tag == "item" or el.tag.endswith("}item")]
    for it in rss_items:
        # RSS 1.0 children carry the same namespace as the item itself
        pre = it.tag[:-4] if it.tag.endswith("}item") else ""
        _txt = lambda name: it.findtext(pre + name)  # noqa: E731
        items.append({
            "title": _strip_html(_txt("title") or ""),
            "link": (_txt("link") or "").strip(),
            "desc": _strip_html(_txt("description") or "")[:300],
            "published": _txt("pubDate")
                         or it.findtext("{http://purl.org/dc/elements/1.1/}date") or "",
            "source": source})
    for it in root.iter("{http://www.w3.org/2005/Atom}entry"):   # Atom
        link_el = it.find("atom:link", ns)
        items.append({
            "title": _strip_html(it.findtext("atom:title", default="", namespaces=ns)),
            "link": (link_el.get("href") if link_el is not None else "") or "",
            "desc": _strip_html(it.findtext("atom:summary", default="", namespaces=ns))[:300],
            "published": it.findtext("atom:updated", default="", namespaces=ns),
            "source": source})
    return [i for i in items if i["title"] and i["link"]]


def _iso(published: str) -> str:
    """RFC822/ISO date → ISO-8601 UTC; unparseable → '' (sorts oldest)."""
    if not published:
        return ""
    try:
        return parsedate_to_datetime(published).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(published.replace("Z", "+00:00")) \
                       .astimezone(timezone.utc).isoformat()
    except ValueError:
        return ""


def _registry_ids() -> set[str]:
    """All league ids in webapp/leagues.js — every one gets a news file (an
    empty one beats a 404 in the console for 'soon' leagues)."""
    try:
        txt = Path("webapp/leagues.js").read_text()
        return {l["id"] for l in json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))}
    except Exception:
        return set()


def main() -> int:
    keywords = _league_keywords()
    per_league: dict[str, list[dict]] = {lid: [] for lid in set(keywords) | _registry_ids()}
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    for feed in FEEDS:
        try:
            r = requests.get(feed["url"], headers=_HDR, timeout=25)
            r.raise_for_status()
            items = _parse_feed(r.content, feed["name"])
        except Exception as exc:                     # noqa: BLE001 — per-feed isolation
            print(f"[warn] {feed['name']}: {exc}")
            continue
        routed = 0
        for it in items:
            if is_gossip(it["title"], it["desc"]):
                continue
            it["published"] = _iso(it["published"])
            for lid in route_item(it["title"], it["desc"], keywords):
                per_league[lid].append(it)
                routed += 1
        print(f"  {feed['name']:28s} {len(items):3d} items · {routed} league-routings")

    n_files = 0
    for lid, items in per_league.items():
        items.sort(key=lambda i: i["published"], reverse=True)
        # dedupe within a league (same story routed from multiple feeds keeps
        # the freshest copy per source; identical titles collapse)
        seen, uniq = set(), []
        for it in items:
            k = re.sub(r"[^a-z0-9]+", " ", it["title"].lower()).strip()[:80]
            if k not in seen:
                seen.add(k)
                uniq.append(it)
        write_js_payload(OUT_DIR / f"{lid}.js", "NEWS_DATA",
                         {"league": lid, "generated": generated, "items": uniq[:30]})
        n_files += 1
    print(f"Wrote {n_files} league news files → {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
