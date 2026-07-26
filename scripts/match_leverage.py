#!/usr/bin/env python3
"""DRAFT — "Matches to Watch": rank fixtures by how much they move the table.

Prototype for the Intel-hub feature. Not wired into any build; run it by hand.

The idea
--------
A match's *leverage* is how much the season's outcome probabilities move
depending on how it ends. A top-of-the-table clash where both sides are already
safe has low leverage; a mid-table game that decides a relegation place has
high leverage even though nobody outside the two cities cares about the badge.

Method: condition on the result.
  1. Simulate the rest of the season N times from the payload's own fixture
     probabilities -> baseline P(bucket) for every club (title, playoff, releg…).
  2. For each candidate fixture, re-simulate three times with that fixture
     PINNED to home / draw / away -> P(bucket | outcome).
  3. leverage = sum over outcomes of  P(outcome) x  the total absolute change in
     bucket probability across the two clubs involved.

That is a proper expected-swing figure, not a heuristic: it is the expected
L1 movement of the table odds attributable to this one match.

Everything comes from the built payload (`webapp/data/<league>.js`), which
already carries per-fixture pH/pD/pA — the same numbers the client what-if uses
— so this needs no model refit and no network.

Usage:
    python3 scripts/match_leverage.py --league mls --days 7
    python3 scripts/match_leverage.py --all --days 3 --sims 4000
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "webapp" / "data"

# Buckets worth weighting, and how much a point of movement in each is "worth"
# to a reader. Title and relegation are what people follow; a playoff berth sits
# between. Tune with real engagement data — these are opening priors.
BUCKET_WEIGHT = {
    "title": 1.0, "releg": 1.0, "playoff": 0.8, "playoffs": 0.8,
    "liguilla": 0.8, "promoted": 0.9, "promo": 0.9, "ucl": 0.6,
    "continental": 0.5, "europa": 0.4, "conf": 0.3, "shield": 0.5,
    "premiers": 0.5, "spoon": 0.2,
}


def load(lid: str) -> dict | None:
    p = DATA / f"{lid}.js"
    if not p.exists():
        return None
    m = re.match(r"window\.\w+\s*=\s*(.*?);?\s*$", p.read_text(encoding="utf-8"), re.DOTALL)
    try:
        d = json.loads(m.group(1)) if m else None
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def _sim(base_pts, base_gd, H, A, P, n_teams, N, rng, pin=None):
    """N season simulations. Returns the finishing ORDER matrix (N, n_teams).

    `pin` = (fixture_index, outcome) forces one result in every simulation.
    Vectorised over simulations: one uniform draw per (sim, fixture).
    """
    nf = len(H)
    order = np.empty((N, n_teams), dtype=np.int32)
    pts = np.tile(base_pts.astype(np.float64), (N, 1))
    if nf:
        u = rng.random((N, nf))
        cumH = P[:, 0]
        cumHD = P[:, 0] + P[:, 1]
        res = np.where(u < cumH, 0, np.where(u < cumHD, 1, 2))
        if pin is not None:
            res[:, pin[0]] = pin[1]
        for f in range(nf):
            r = res[:, f]
            np.add.at(pts, (np.where(r == 0)[0], H[f]), 3)
            d = np.where(r == 1)[0]
            np.add.at(pts, (d, H[f]), 1)
            np.add.at(pts, (d, A[f]), 1)
            np.add.at(pts, (np.where(r == 2)[0], A[f]), 3)
    # points, then current GD, then jitter — mirrors the builder's ranking key
    key = pts * 10000.0 + base_gd * 10.0 + rng.random((N, n_teams)) * 10.0
    order = np.argsort(-key, axis=1)
    return order


def _bucket_probs(order, columns, n_teams):
    """{bucket_key: array(n_teams) of probability} from finishing orders."""
    N = order.shape[0]
    out = {}
    for c in columns:
        k = c.get("key")
        cnt = np.zeros(n_teams)
        if c.get("top") is not None:
            idx = order[:, :min(int(c["top"]), n_teams)]
        elif c.get("bottom") is not None:
            idx = order[:, max(0, n_teams - int(c["bottom"])):]
        elif c.get("band"):
            lo, hi = c["band"]
            idx = order[:, lo - 1:min(hi, n_teams)]
        elif c.get("promo_top") is not None:
            idx = order[:, :min(int(c["promo_top"]), n_teams)]
        elif c.get("champ_playoff") is not None:
            # Approximation for ranking purposes only: treat the bracket as the
            # seeded field. The real champion sim lives in build_league_data.
            idx = order[:, :1]
        else:
            continue
        np.add.at(cnt, idx.ravel(), 1)
        out[k] = cnt / N
    return out


def leverage_for_league(lid: str, horizon_days: int, N: int, seed: int = 7):
    d = load(lid)
    if not d or d.get("status") not in ("live", "preseason"):
        return []
    st = d.get("standings") or []
    cols = ((d.get("outlook") or {}).get("columns")) or []
    if not st or not cols:
        return []
    teams = [r["team"] for r in st]
    tidx = {t: i for i, t in enumerate(teams)}
    n_teams = len(teams)
    base_pts = np.array([r.get("pts", 0) or 0 for r in st], dtype=float)
    base_gd = np.array([r.get("gd", 0) or 0 for r in st], dtype=float)

    games = [g for g in (d.get("games") or [])
             if g.get("result") is None and g.get("pH") is not None
             and g.get("home") in tidx and g.get("away") in tidx]
    if not games:
        return []
    H = np.array([tidx[g["home"]] for g in games])
    A = np.array([tidx[g["away"]] for g in games])
    P = np.array([[g["pH"], g["pD"], g["pA"]] for g in games], dtype=float)
    P /= P.sum(axis=1, keepdims=True)

    rng = np.random.default_rng(seed)
    base_order = _sim(base_pts, base_gd, H, A, P, n_teams, N, rng)
    base_probs = _bucket_probs(base_order, cols, n_teams)

    today = date.today()
    cutoff = today + timedelta(days=horizon_days)
    cands = [i for i, g in enumerate(games)
             if g.get("date") and today <= _d(g["date"]) <= cutoff]

    rows = []
    for i in cands:
        g = games[i]
        hi, ai = H[i], A[i]
        swing = 0.0
        detail = {}
        for outcome in (0, 1, 2):
            rng_o = np.random.default_rng(seed + 1 + outcome)
            o_order = _sim(base_pts, base_gd, H, A, P, n_teams, N, rng_o, pin=(i, outcome))
            o_probs = _bucket_probs(o_order, cols, n_teams)
            p_o = P[i, outcome]
            for k, w in ((c.get("key"), BUCKET_WEIGHT.get(c.get("key"), 0.3)) for c in cols):
                if k not in o_probs or k not in base_probs:
                    continue
                for t in (hi, ai):
                    delta = abs(o_probs[k][t] - base_probs[k][t])
                    swing += p_o * w * delta
                    if delta > detail.get(k, (0, None))[0]:
                        detail[k] = (delta, teams[t])
        top = max(detail.items(), key=lambda kv: kv[1][0], default=(None, (0, None)))
        rows.append({
            "league": lid, "date": g["date"], "home": g["home"], "away": g["away"],
            "leverage": round(swing * 100, 2),
            "driver": top[0], "driver_team": top[1][1],
            "driver_swing_pp": round(top[1][0] * 100, 1),
            "pH": g["pH"], "pD": g["pD"], "pA": g["pA"],
        })
    rows.sort(key=lambda r: -r["leverage"])
    return rows


def _d(s: str) -> date:
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--sims", type=int, default=3000)
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()

    lids = ([p.stem for p in sorted(DATA.glob("*.js"))] if a.all
            else [a.league])
    rows = []
    for lid in lids:
        try:
            rows += leverage_for_league(lid, a.days, a.sims)
        except Exception as e:
            print(f"  [skip] {lid}: {type(e).__name__}: {e}")
    rows.sort(key=lambda r: -r["leverage"])
    print(f"\nMatches to watch — next {a.days} day(s), {len(rows)} fixture(s) scored\n")
    print(f"{'date':11} {'league':20} {'fixture':46} {'lev':>6}  what turns on it")
    print("-" * 122)
    for r in rows[:a.top]:
        fx = f"{r['home']} v {r['away']}"
        drv = (f"{r['driver_team']} {r['driver']} ±{r['driver_swing_pp']}pp"
               if r["driver"] else "")
        print(f"{r['date']:11} {r['league']:20} {fx:46} {r['leverage']:6.2f}  {drv}")


if __name__ == "__main__":
    main()
