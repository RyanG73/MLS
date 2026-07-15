#!/usr/bin/env python3
"""Cross-league edge board (B12) — the site's landing view.

Aggregates every upcoming match across all `live` league payloads into
webapp/data/edge-board.js (window.EDGE_BOARD_DATA), ranked by model edge over
the market. Continental knockouts and power rankings are excluded this cycle
(no odds source until the Odds API spend — user decision 2026-07-03).

Kelly sizing reuses bet_ledger.py's _quarter_kelly_units so the stake formula
lives in exactly one Python place (the JS mirror in webapp/index.html is the
other, per the devig+Kelly comment there).

Payload dates are day-granularity only (no kickoff time-of-day exists in the
current build), so the "next 48h" window and staleness framing below operate
at day resolution, not hour resolution — documented rather than faked.

Runs last in the CI build chain, after all league builds and bet_ledger.py:
    python scripts/build_edge_board.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.resolve()
_DATA = REPO_ROOT / "webapp" / "data"
_NON_PAYLOAD = {"logos.js", "ledger.js"}
_WINDOW_DAYS = 2   # "next 48h", day-granularity
EDGE_THRESH = 8.0  # CLAUDE.md edge threshold
KELLY_FRACTION = 0.25

from scripts.bet_ledger import _load_payload, _quarter_kelly_units  # noqa: E402
from scripts.payload_utils import write_js_payload  # noqa: E402


def _is_eligible(payload) -> bool:
    """Live table/conference leagues only — no continental knockouts, no power.
    Non-dict payloads (e.g. search-index.js is a JSON array) are never eligible
    — durable guard shared across every webapp/data/*.js consumer."""
    if not isinstance(payload, dict):
        return False
    if payload.get("status") != "live":
        return False
    return (payload.get("outlook") or {}).get("mode") != "knockout"


def _best_bet(g: dict) -> dict | None:
    """≥8% edge, draw-side suppressed (A11 not KEPT yet — mirrors bet_ledger.py)."""
    mkt_home, mkt_away = g.get("mkt_home"), g.get("mkt_away")
    if mkt_home is None or mkt_away is None:
        return None
    best = None
    for side, p, m in (("H", g["pH"], mkt_home), ("A", g["pA"], mkt_away)):
        edge = (p - m) * 100
        if edge < EDGE_THRESH or (best is not None and edge <= best["edge_pct"]):
            continue
        units = _quarter_kelly_units(p, m)
        if units > 0:
            best = {"side": side, "edge_pct": round(edge, 2), "units": units,
                    "model_p": round(p, 4), "mkt_p": round(m, 4)}
    return best


def _risk_flags(g: dict, bet: dict | None) -> list[str]:
    flags = []
    if g.get("mkt_home") is None or g.get("mkt_away") is None:
        flags.append("no_line")
    if g.get("pD") is not None and g["pD"] >= 0.30:
        flags.append("draw_heavy")
    if isinstance(g.get("lam"), (int, float)) and isinstance(g.get("mu"), (int, float)):
        if float(g["lam"]) + float(g["mu"]) < 2.4 and g.get("pD", 0) >= 0.28:
            flags.append("low_total_draw_setup")
    h, a = g.get("pH"), g.get("pA")
    if isinstance(h, (int, float)) and isinstance(a, (int, float)):
        if h <= 0.25 and a - h >= 0.15:
            flags.append("home_model_underdog")
        if a <= 0.25 and h - a >= 0.15:
            flags.append("away_model_underdog")
    if bet:
        flags.append("qualifying_market_edge")
    return flags


def _row(league_id: str, league_name: str, g: dict, generated: str | None) -> dict:
    bet = _best_bet(g)
    return {
        "league": league_id, "league_name": league_name,
        "date": g["date"], "home": g["home"], "away": g["away"],
        "hlogo": g.get("hlogo"), "alogo": g.get("alogo"),
        "hcolor": g.get("hcolor"), "acolor": g.get("acolor"),
        "pH": g["pH"], "pD": g["pD"], "pA": g["pA"],
        "lam": g.get("lam"), "mu": g.get("mu"),
        "has_market": bool(g.get("mkt_home") is not None),
        "bet": bet,
        "risk_flags": _risk_flags(g, bet),
        "built_at": generated,
    }


def _iter_live_payloads(data_dir: Path):
    for p in sorted(data_dir.glob("*.js")):
        if p.name in _NON_PAYLOAD:
            continue
        try:
            payload = _load_payload(p)
        except Exception as e:
            print(f"[edge-board] skip {p.name}: {e}", file=sys.stderr)
            continue
        if _is_eligible(payload):
            yield p.stem, payload


def collect_rows(payloads: dict[str, dict], now: pd.Timestamp | None = None,
                 window_days: int = _WINDOW_DAYS) -> tuple[list[dict], list[dict]]:
    """Returns (priced, no_line) from {league_id: payload}. Matches without a
    market line are listed below a divider rather than hidden (an edge product
    should show what it can't yet price, not pretend it doesn't exist)."""
    priced, no_line = [], []
    today = (now or pd.Timestamp.now(tz="UTC")).normalize()
    cutoff = today + pd.Timedelta(days=window_days)
    for league_id, payload in payloads.items():
        if not _is_eligible(payload):
            continue
        league_name = (payload.get("league") or {}).get("name", league_id)
        generated = payload.get("generated")
        for g in payload.get("games") or []:
            if g.get("result") is not None:
                continue
            try:
                d = pd.Timestamp(g["date"], tz="UTC")
            except Exception:
                continue
            if not (today <= d < cutoff):
                continue
            row = _row(league_id, league_name, g, generated)
            (priced if row["has_market"] else no_line).append(row)
    priced.sort(key=lambda r: -(r["bet"]["edge_pct"] if r["bet"] else -999.0))
    no_line.sort(key=lambda r: r["date"])
    return priced, no_line


def next_kickoffs(payloads: dict[str, dict], n: int = 8) -> list[dict]:
    """Nearest upcoming matches regardless of edge — the empty-state fallback."""
    rows = []
    for league_id, payload in payloads.items():
        if not _is_eligible(payload):
            continue
        league_name = (payload.get("league") or {}).get("name", league_id)
        for g in payload.get("games") or []:
            if g.get("result") is None:
                rows.append({"league": league_id, "league_name": league_name,
                            "date": g["date"], "home": g["home"], "away": g["away"]})
    rows.sort(key=lambda r: r["date"])
    return rows[:n]


def upcoming_summary(payloads: dict[str, dict], now: pd.Timestamp | None = None,
                     window_days: int = 7) -> dict:
    """Count upcoming matches across the broader command-center window."""
    today = (now or pd.Timestamp.now(tz="UTC")).normalize()
    cutoff = today + pd.Timedelta(days=window_days)
    rows = []
    leagues = set()
    for league_id, payload in payloads.items():
        if not _is_eligible(payload):
            continue
        league_name = (payload.get("league") or {}).get("name", league_id)
        for g in payload.get("games") or []:
            if g.get("result") is not None:
                continue
            try:
                d = pd.Timestamp(g["date"], tz="UTC")
            except Exception:
                continue
            if today <= d < cutoff:
                rows.append({"league": league_id, "league_name": league_name,
                             "date": g["date"], "home": g["home"], "away": g["away"]})
                leagues.add(league_name)
    rows.sort(key=lambda r: r["date"])
    return {
        "window_days": window_days,
        "match_count": len(rows),
        "league_count": len(leagues),
        "first_kickoff": rows[0] if rows else None,
        "next": rows[:10],
    }


def season_races(payloads: dict[str, dict], limit: int = 18) -> list[dict]:
    """Always-populated cross-league season-race cards for the landing page."""
    preferred = ["title", "shield", "cup", "ucl", "promoted", "promotion", "playoff", "releg"]
    rows = []
    for league_id, payload in payloads.items():
        if not _is_eligible(payload):
            continue
        standings = payload.get("standings") or []
        if not standings:
            continue
        league_name = (payload.get("league") or {}).get("name", league_id)
        card_labels = {
            c.get("key"): c.get("label", c.get("key"))
            for c in (payload.get("outlook") or {}).get("cards") or []
        }
        available = []
        for key in preferred:
            vals = [r.get(key) for r in standings if isinstance(r.get(key), (int, float))]
            if vals:
                available.append((key, card_labels.get(key, key.replace("_", " ").title())))
        for key, label in available[:3]:
            contenders = [
                {
                    "team": r.get("team"),
                    "prob": round(float(r.get(key)), 1),
                    "logo": r.get("logo"),
                    "color": r.get("color"),
                }
                for r in standings
                if isinstance(r.get(key), (int, float))
            ]
            contenders.sort(key=lambda r: r["prob"], reverse=True)
            if not contenders:
                continue
            leader = contenders[0]
            second = contenders[1]["prob"] if len(contenders) > 1 else 0.0
            rows.append({
                "league": league_id,
                "league_name": league_name,
                "race": key,
                "label": label,
                "leader": leader,
                "contenders": contenders[1:4],
                "uncertainty": round(100.0 - leader["prob"], 1),
                "margin": round(leader["prob"] - second, 1),
                "generated": payload.get("generated"),
            })
    rows.sort(key=lambda r: (-r["uncertainty"], r["margin"], r["league_name"]))
    return rows[:limit]


def risk_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for flag in row.get("risk_flags") or []:
            counts[flag] = counts.get(flag, 0) + 1
    return dict(sorted(counts.items()))


def _load_live_payloads(data_dir: Path) -> dict[str, dict]:
    return dict(_iter_live_payloads(data_dir))


def main() -> int:
    payloads = _load_live_payloads(_DATA)
    priced, no_line = collect_rows(payloads)
    out = {
        "status": "live",
        "priced": priced,
        "no_line": no_line,
        "next_kickoffs": [] if (priced or no_line) else next_kickoffs(payloads),
        "upcoming_7d": upcoming_summary(payloads),
        "season_races": season_races(payloads),
        "risk_counts": risk_counts(priced + no_line),
        "edge_threshold_pct": EDGE_THRESH,
        "kelly_fraction": KELLY_FRACTION,
        "window_days": _WINDOW_DAYS,
        "note": ("Edge % and quarter-Kelly sizing need forward market odds, which "
                 "currently only accrue via the ODDS_API_KEY-gated MLS log (B10) — "
                 "most rows below the divider have no line yet. Continental "
                 "competitions are excluded this cycle (no odds source)."),
        "generated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
    }
    write_js_payload(_DATA / "edge-board.js", "EDGE_BOARD_DATA", out)
    n_edges = sum(1 for r in priced if r["bet"])
    print(f"[edge-board] {len(priced)} priced ({n_edges} >= {EDGE_THRESH}% edge), "
          f"{len(no_line)} no-line, window={_WINDOW_DAYS}d")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
