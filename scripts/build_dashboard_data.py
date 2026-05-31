#!/usr/bin/env python3
"""
Build real model-derived data for the predictions dashboard (webapp/data.js).

- Fits the validated model (models/research_model.py) on 2017-2023, predicts every
  2024 match (home/draw/away probabilities).
- Monte-Carlo simulates the 2024 season from those match probabilities (N sims) to
  produce, per team: playoff odds (top 9 in conference), top-4 home-field odds,
  Supporters' Shield odds (best overall record), wooden-spoon odds (worst overall).
- Emits webapp/data.js as `window.MLS_DATA = {...}` (inlined so it opens over file://).

Usage: python scripts/build_dashboard_data.py [--season 2024] [--sims 20000]
"""

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── MLS 2024 conference map (by normalized ASA team_name) ─────────────────────
_EAST = {
    "atlanta united fc", "charlotte fc", "chicago fire fc", "fc cincinnati",
    "columbus crew", "dc united", "inter miami cf", "cf montreal", "nashville sc",
    "new england revolution", "new york city fc", "new york red bulls",
    "orlando city sc", "philadelphia union", "toronto fc",
}
_WEST = {
    "austin fc", "colorado rapids", "fc dallas", "houston dynamo fc", "la galaxy",
    "los angeles fc", "minnesota united fc", "portland timbers fc", "real salt lake",
    "san jose earthquakes", "seattle sounders fc", "sporting kansas city",
    "st louis city sc", "vancouver whitecaps fc",
}
_PLAYOFF_SLOTS = 9   # top N per conference make the playoffs (2024 format)
_HFA_SLOTS = 4       # top N per conference host round 1


def _norm(n):
    n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode()
    return "".join(c for c in n.lower() if c.isalnum() or c == " ").strip()


def _conf(name):
    nn = _norm(name)
    if nn in _EAST:
        return "East"
    if nn in _WEST:
        return "West"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--season", type=int, default=2024)
    ap.add_argument("--sims", type=int, default=20000)
    args = ap.parse_args()

    frame = Path(args.frame)
    meta = json.loads(frame.with_suffix(".meta.json").read_text())
    feat_base = meta["feat_base"]
    df = pd.read_parquet(frame)
    df["date"] = pd.to_datetime(df["date"])
    ts = args.season

    from models.research_model import (
        fit_dc, dc_predict_batch, fit_xgb, calibrate_temperature,
        fit_capped_blend, blend,
    )
    from itscalledsoccer.client import AmericanSoccerAnalysis
    asa = AmericanSoccerAnalysis(); asa.session.verify = False
    teams = asa.get_teams(leagues="mls")
    id2name = {r.team_id: r.team_name for r in teams.itertuples()}

    # ── Fit model on <2023, calibrate on 2023, predict the target season ──────
    feat = [c for c in feat_base if c in df.columns]
    train = df[df["season"] < ts - 1].dropna(subset=["home_goals", "away_goals"])
    cal = df[df["season"] == ts - 1].dropna(subset=["home_goals", "away_goals"])
    test = df[df["season"] == ts].dropna(subset=["home_goals", "away_goals"]).copy()
    y_cal = cal["label_result"].values.astype(int)
    y_cal_oh = np.eye(3)[y_cal]

    print(f"Fitting model: train={len(train)} cal={len(cal)} test({ts})={len(test)}")
    atk, dfd, ha, rho = fit_dc(train)
    dc_cal = calibrate_temperature(dc_predict_batch(cal, atk, dfd, ha, rho), y_cal,
                                   dc_predict_batch(cal, atk, dfd, ha, rho))
    dc_te = calibrate_temperature(dc_predict_batch(cal, atk, dfd, ha, rho), y_cal,
                                  dc_predict_batch(test, atk, dfd, ha, rho))
    clf, _ = fit_xgb(train, feat)
    xc = clf.predict_proba(cal[feat].fillna(0).values)
    xt = clf.predict_proba(test[feat].fillna(0).values)
    xgb_cal = calibrate_temperature(xc, y_cal, xc)
    xgb_te = calibrate_temperature(xc, y_cal, xt)
    w = fit_capped_blend(xgb_cal, dc_cal, y_cal_oh)
    probs = blend(xgb_te, dc_te, w)   # N x 3 (home, draw, away) for season `ts`
    test = test.reset_index(drop=True)

    # ── Games list (only teams with a known conference = MLS regular season) ──
    games = []
    sim_rows = []   # (home_id, away_id, pH, pD, pA)
    for i, r in test.iterrows():
        h, a = r["home_team"], r["away_team"]
        hn, an = id2name.get(h, h), id2name.get(a, a)
        if _conf(hn) is None or _conf(an) is None:
            continue
        pH, pD, pA = float(probs[i, 0]), float(probs[i, 1]), float(probs[i, 2])
        actual = (None if pd.isna(r["home_goals"]) else
                  ("H" if r["home_goals"] > r["away_goals"]
                   else "D" if r["home_goals"] == r["away_goals"] else "A"))
        games.append({
            "date": r["date"].strftime("%Y-%m-%d"),
            "home": hn, "away": an,
            "pH": round(pH, 3), "pD": round(pD, 3), "pA": round(pA, 3),
            "hg": None if pd.isna(r["home_goals"]) else int(r["home_goals"]),
            "ag": None if pd.isna(r["away_goals"]) else int(r["away_goals"]),
            "result": actual,
        })
        sim_rows.append((hn, an, pH, pD, pA))
    games.sort(key=lambda g: g["date"])

    team_names = sorted({g["home"] for g in games} | {g["away"] for g in games})
    idx = {t: i for i, t in enumerate(team_names)}
    nT = len(team_names)
    confs = np.array([_conf(t) for t in team_names])

    # ── Monte-Carlo season simulation ────────────────────────────────────────
    rng = np.random.default_rng(42)
    P = np.array([[r[2], r[3], r[4]] for r in sim_rows])
    HI = np.array([idx[r[0]] for r in sim_rows])
    AI = np.array([idx[r[1]] for r in sim_rows])
    N = args.sims
    playoff = np.zeros(nT); hfa = np.zeros(nT); shield = np.zeros(nT); spoon = np.zeros(nT)
    proj_pts = np.zeros(nT)
    east_i = np.where(confs == "East")[0]
    west_i = np.where(confs == "West")[0]
    print(f"Simulating {N:,} seasons over {len(sim_rows)} matches, {nT} teams...")
    for _ in range(N):
        u = rng.random(len(sim_rows))
        outc = np.where(u < P[:, 0], 0, np.where(u < P[:, 0] + P[:, 1], 1, 2))
        pts = np.zeros(nT)
        np.add.at(pts, HI[outc == 0], 3)               # home win
        np.add.at(pts, HI[outc == 1], 1); np.add.at(pts, AI[outc == 1], 1)  # draw
        np.add.at(pts, AI[outc == 2], 3)               # away win
        proj_pts += pts
        jitter = pts + rng.random(nT) * 0.01           # break ties randomly
        for conf_idx in (east_i, west_i):
            order = conf_idx[np.argsort(-jitter[conf_idx])]
            playoff[order[:_PLAYOFF_SLOTS]] += 1
            hfa[order[:_HFA_SLOTS]] += 1
        shield[np.argmax(jitter)] += 1
        spoon[np.argmin(jitter)] += 1

    standings = []
    for t in team_names:
        i = idx[t]
        standings.append({
            "team": t, "conf": confs[i],
            "proj_pts": round(proj_pts[i] / N, 1),
            "playoff": round(playoff[i] / N * 100, 1),
            "hfa": round(hfa[i] / N * 100, 1),
            "shield": round(shield[i] / N * 100, 1),
            "spoon": round(spoon[i] / N * 100, 1),
        })
    standings.sort(key=lambda s: -s["proj_pts"])

    data = {
        "season": ts,
        "model": {"best_brier": 0.6344, "naive": 0.6406, "improve_pct": 0.97},
        "n_sims": N,
        "playoff_slots": _PLAYOFF_SLOTS, "hfa_slots": _HFA_SLOTS,
        "standings": standings,
        "games": games,
        "generated": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }
    out = Path("webapp/data.js")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("window.MLS_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    print(f"Wrote {out}  ({len(games)} games, {len(standings)} teams)")
    # quick sanity print
    top = standings[:3]
    for s in top:
        print(f"  {s['team']:<24} {s['conf']} proj {s['proj_pts']}  "
              f"PO {s['playoff']}%  Shield {s['shield']}%")


if __name__ == "__main__":
    main()
