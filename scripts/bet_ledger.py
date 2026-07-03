#!/usr/bin/env python3
"""Build-time paper-bet ledger (B11b) — the live validation of the edge product.

After each build:
  LOG    — every upcoming match with market odds where edge ≥ 8% becomes a paper
           bet at the FIRST build that recommends it (no repricing on later
           builds — that's what CLV measures). Draw-side bets are SUPPRESSED
           until A11 lands a draw-structure KEEP (the model's known-worst class).
  SETTLE — decided matches get result + units P/L; CLV pp is filled where
           closers exist (data_pipeline/market.py:clv_pp) — None until the
           odds_log closers accrue.
  SURFACE— a cross-league summary is written to webapp/data/ledger.js
           (window.LEDGER_DATA), one source for the B5 market view and the
           B12 edge board's ledger strip.

Stakes are quarter-Kelly at fair (de-vigged) odds, expressed in units
(1u = 1% bankroll). Ledger: data/bet_ledger.parquet, append-only, deduped on
league+match_key+side.

Usage:
    python scripts/bet_ledger.py            # log + settle + surface, all payloads
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.resolve()
_DATA = REPO_ROOT / "webapp" / "data"
_LEDGER = REPO_ROOT / "data" / "bet_ledger.parquet"
_NON_PAYLOAD = {"logos.js", "ledger.js"}

EDGE_THRESH = 8.0        # CLAUDE.md edge threshold
KELLY_FRACTION = 0.25    # quarter-Kelly (user decision 2026-07-03)
_SIDES = [("H", "pH", "mkt_home"), ("A", "pA", "mkt_away")]  # draw suppressed (A11)

_DEDUP = ["league", "match_key", "side"]


def _quarter_kelly_units(p: float, mkt_p: float) -> float:
    """Quarter-Kelly stake in units (1u = 1% bankroll) at fair odds 1/mkt_p."""
    if not (0.0 < mkt_p < 1.0):
        return 0.0
    b = 1.0 / mkt_p - 1.0
    f = (p * (b + 1.0) - 1.0) / b
    return round(f * KELLY_FRACTION * 100, 1) if f > 0 else 0.0


def candidate_bets(league_id: str, payload: dict,
                   thresh: float = EDGE_THRESH) -> list[dict]:
    """Paper bets for a payload's upcoming matches with market odds attached."""
    bets = []
    for g in payload.get("games") or []:
        if g.get("result") is not None or g.get("mkt_home") is None:
            continue
        for side, pk, mk in _SIDES:
            p, m = float(g[pk]), float(g[mk])
            edge = (p - m) * 100
            if edge < thresh:
                continue
            units = _quarter_kelly_units(p, m)
            if units <= 0:
                continue
            bets.append({
                "league": league_id,
                "match_key": f"{g['date']}|{g['home']}|{g['away']}",
                "date": g["date"], "home": g["home"], "away": g["away"],
                "side": side, "model_p": round(p, 4), "mkt_p": round(m, 4),
                "dec_odds": round(1.0 / m, 3), "edge_pct": round(edge, 2),
                "units": units, "logged_at": payload.get("generated"),
                "result": None, "won": None, "pnl": None, "clv_pp": None,
            })
    return bets


def log_bets(bets: list[dict], path: Path = _LEDGER) -> int:
    """Append new bets; a bet is logged once (first build that recommends it)."""
    if not bets:
        return 0
    new = pd.DataFrame(bets)
    n_old = 0
    if path.exists():
        old = pd.read_parquet(path)
        n_old = len(old)
        new = pd.concat([old, new], ignore_index=True)
    combined = new.drop_duplicates(subset=_DEDUP, keep="first")
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False)
    return len(combined) - n_old


def settle_bets(path: Path, results: dict[tuple, str]) -> int:
    """Fill result/won/pnl for decided matches. results keys:
    (league, date, home, away) → 'H'|'D'|'A'. Returns bets settled."""
    if not path.exists():
        return 0
    df = pd.read_parquet(path)
    n = 0
    for i, r in df.iterrows():
        if r["result"] is not None and not pd.isna(r["result"]):
            continue
        res = results.get((r["league"], r["date"], r["home"], r["away"]))
        if res is None:
            continue
        won = r["side"] == res
        df.at[i, "result"] = res
        df.at[i, "won"] = won
        df.at[i, "pnl"] = (r["units"] * (r["dec_odds"] - 1.0)) if won else -r["units"]
        n += 1
    if n:
        df.to_parquet(path, index=False)
    return n


def ledger_summary(df: pd.DataFrame) -> dict:
    """Cross-league summary block for the UI (P/L, hit rate, drawdown, CLV)."""
    settled = df[df["result"].notna()] if len(df) else df
    out = {
        "n_bets": int(len(df)),
        "n_settled": int(len(settled)),
        "units_pnl": round(float(settled["pnl"].sum()), 2) if len(settled) else 0.0,
        "hit_rate": round(float(settled["won"].mean()), 3) if len(settled) else None,
        "clv_mean_pp": (round(float(settled["clv_pp"].mean()), 2)
                        if len(settled) and settled["clv_pp"].notna().any() else None),
        "max_drawdown": 0.0,
        "by_league": {},
    }
    if len(settled):
        cum = settled["pnl"].astype(float).cumsum()
        out["max_drawdown"] = round(float((cum.cummax() - cum).max()), 2)
        for lg, g in settled.groupby("league"):
            out["by_league"][lg] = {"n": int(len(g)),
                                    "units_pnl": round(float(g["pnl"].sum()), 2),
                                    "hit_rate": round(float(g["won"].mean()), 3)}
    return out


def _load_payload(path: Path) -> dict:
    txt = path.read_text(encoding="utf-8")
    m = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$", txt, re.DOTALL)
    if not m:
        raise ValueError(f"{path.name}: no JS assignment pattern")
    return json.loads(m.group(1))


def main() -> int:
    all_results: dict[tuple, str] = {}
    n_logged = 0
    for p in sorted(_DATA.glob("*.js")):
        if p.name in _NON_PAYLOAD:
            continue
        try:
            payload = _load_payload(p)
        except Exception as e:
            print(f"[ledger] skip {p.name}: {e}", file=sys.stderr)
            continue
        if payload.get("status") == "placeholder":
            continue
        n_logged += log_bets(candidate_bets(p.stem, payload))
        for g in payload.get("games") or []:
            if g.get("result") in ("H", "D", "A"):
                all_results[(p.stem, g["date"], g["home"], g["away"])] = g["result"]
    n_settled = settle_bets(_LEDGER, all_results)

    df = pd.read_parquet(_LEDGER) if _LEDGER.exists() else pd.DataFrame(
        columns=["league", "units", "won", "pnl", "result", "clv_pp"])
    summary = ledger_summary(df)
    out = {"status": "live", "summary": summary,
           "bets": (df.sort_values("date", ascending=False).head(200)
                    .where(df.notna(), None).to_dict("records") if len(df) else []),
           "note": ("paper ledger — quarter-Kelly at fair (de-vigged) odds; a bet "
                    "is logged at the first build that recommends it; draw-side "
                    "suppressed pending A11"),
           "generated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC")}
    (_DATA / "ledger.js").write_text(
        "window.LEDGER_DATA = " + json.dumps(out, allow_nan=False) + ";\n")
    print(f"[ledger] +{n_logged} logged, {n_settled} settled · "
          f"{summary['n_bets']} total ({summary['n_settled']} settled, "
          f"P/L {summary['units_pnl']}u)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
