"""
News monitoring pipeline.
1. Poll RSS feeds for MLS news every 6 hours.
2. Filter for injury/lineup-relevant articles via keyword matching.
3. Call Claude API to summarize and estimate impact on team strength.
4. Store results in `news_items` table for dashboard review.
"""

import os
import hashlib
import logging
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser
import anthropic
import pandas as pd

from config import SETTINGS
from data_pipeline import db_utils

logger = logging.getLogger(__name__)

_NEWS_CFG = SETTINGS["news"]
_CLAUDE_MODEL = _NEWS_CFG["claude_model"]
_KEYWORDS = [k.lower() for k in _NEWS_CFG["keywords"]]
_MAX_IMPACT = _NEWS_CFG["impact_magnitude_max"]

_IMPACT_PROMPT = """You are an expert MLS soccer analyst. Analyze the following news article headline and determine its impact on match predictions.

Headline: {headline}

Source: {source}

Article snippet: {snippet}

Respond with a JSON object containing:
{{
  "teams_mentioned": ["team1", "team2"],
  "summary": "One sentence plain-English summary of what happened",
  "estimated_impact_home_atk": <float between -{max} and {max}>,
  "estimated_impact_home_def": <float between -{max} and {max}>,
  "estimated_impact_away_atk": <float between -{max} and {max}>,
  "estimated_impact_away_def": <float between -{max} and {max}>,
  "impact_confidence": "high" | "medium" | "low",
  "is_relevant": true | false
}}

Notes:
- Negative values mean the team gets WEAKER (e.g., star striker injured → home_atk = -0.12)
- Positive values mean the team gets STRONGER (e.g., star player returns → home_atk = +0.08)
- If the article is not relevant to match outcomes (e.g., transfer rumor, off-field story), set is_relevant=false
- Only use home/away labels if the match context is clear; otherwise apply to the affected team
- Impact should be proportional to the player's importance (star DP = larger impact)
"""


def _item_id(url: str, published: str) -> str:
    return hashlib.md5(f"{url}_{published}".encode()).hexdigest()[:20]


def _is_relevant(entry: feedparser.FeedParserDict) -> bool:
    text = (
        (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    )
    return any(kw in text for kw in _KEYWORDS)


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("CLAUDE_API_KEY environment variable not set.")
    return anthropic.Anthropic(api_key=api_key)


def _call_claude(headline: str, source: str, snippet: str) -> Optional[dict]:
    """Call Claude API to analyze a news item. Returns parsed JSON or None."""
    client = _get_client()
    prompt = _IMPACT_PROMPT.format(
        headline=headline,
        source=source,
        snippet=snippet[:800],
        max=_MAX_IMPACT,
    )
    try:
        message = client.messages.create(
            model=_CLAUDE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Extract JSON from response
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as exc:
        logger.error("Claude API error: %s", exc)
    return None


def poll_feeds() -> list[dict]:
    """Poll all configured RSS feeds and return relevant unprocessed items."""
    seen_ids = _get_seen_ids()
    new_items = []

    for feed_cfg in _NEWS_CFG["rss_feeds"]:
        url = feed_cfg["url"]
        source = feed_cfg["source"]
        try:
            feed = feedparser.parse(url)
        except Exception as exc:
            logger.warning("Failed to parse feed %s: %s", url, exc)
            continue

        for entry in feed.entries:
            item_id = _item_id(entry.get("link", ""), entry.get("published", ""))
            if item_id in seen_ids:
                continue
            if not _is_relevant(entry):
                continue

            published_raw = entry.get("published", "")
            snippet = entry.get("summary", entry.get("description", ""))[:500]

            new_items.append({
                "item_id": item_id,
                "headline": entry.get("title", ""),
                "url": entry.get("link", ""),
                "source": source,
                "published_raw": published_raw,
                "snippet": snippet,
            })

    logger.info("Found %d new relevant news items.", len(new_items))
    return new_items


def _get_seen_ids() -> set[str]:
    """Return item_ids already in the DB to avoid reprocessing."""
    try:
        df = db_utils.query("SELECT item_id FROM news_items")
        return set(df["item_id"].tolist())
    except Exception:
        return set()


def process_item(item: dict) -> Optional[dict]:
    """Run a single news item through Claude and return DB row dict."""
    analysis = _call_claude(item["headline"], item["source"], item["snippet"])
    if not analysis:
        return None
    if not analysis.get("is_relevant", True):
        logger.debug("Claude marked item as not relevant: %s", item["headline"])
        return None

    published_at = _parse_date(item["published_raw"])

    return {
        "item_id": item["item_id"],
        "published_at": published_at,
        "source": item["source"],
        "headline": item["headline"],
        "url": item["url"],
        "teams_mentioned": analysis.get("teams_mentioned", []),
        "claude_summary": analysis.get("summary", ""),
        "estimated_impact_home_atk": float(analysis.get("estimated_impact_home_atk", 0.0)),
        "estimated_impact_home_def": float(analysis.get("estimated_impact_home_def", 0.0)),
        "estimated_impact_away_atk": float(analysis.get("estimated_impact_away_atk", 0.0)),
        "estimated_impact_away_def": float(analysis.get("estimated_impact_away_def", 0.0)),
        "impact_confidence": analysis.get("impact_confidence", "low"),
        "confirmed_by_user": False,
        "applied_to_match_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def run_pipeline() -> int:
    """Full news pipeline: poll → filter → Claude → store. Returns count processed."""
    items = poll_feeds()
    processed = 0
    rows = []
    for item in items:
        row = process_item(item)
        if row:
            rows.append(row)
            processed += 1

    if rows:
        df = pd.DataFrame(rows)
        db_utils.upsert_dataframe(df, "news_items", ["item_id"])
        logger.info("Stored %d news items to DuckDB.", processed)

    return processed


def get_pending_items() -> pd.DataFrame:
    """Return news items awaiting user confirmation."""
    return db_utils.query(
        """
        SELECT * FROM news_items
        WHERE confirmed_by_user = FALSE
        ORDER BY published_at DESC
        LIMIT 50
        """
    )


def apply_news_override(item_id: str, match_id: str, home_adj: float, away_adj: float) -> None:
    """Mark a news item as confirmed and write an override to the overrides table."""
    import uuid
    now = datetime.now(timezone.utc).isoformat()

    headline_row = db_utils.query(
        "SELECT headline FROM news_items WHERE item_id = ?", [item_id]
    )
    desc = headline_row["headline"].iloc[0] if not headline_row.empty else ""

    db_utils.execute(
        """
        INSERT INTO overrides (override_id, match_id, applied_at, description,
                               home_strength_adj, away_strength_adj, source, news_item_id)
        VALUES (?, ?, ?, ?, ?, ?, 'news', ?)
        """,
        [str(uuid.uuid4())[:16], match_id, now, desc, home_adj, away_adj, item_id],
    )
    db_utils.execute(
        "UPDATE news_items SET confirmed_by_user = TRUE, applied_to_match_id = ? WHERE item_id = ?",
        [match_id, item_id],
    )
    logger.info("Applied override from news item %s to match %s.", item_id, match_id)


def _parse_date(raw: str) -> str:
    """Try to parse various RSS date formats; fallback to now."""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(raw).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()
