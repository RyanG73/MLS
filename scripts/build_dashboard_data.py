#!/usr/bin/env python3
"""
Build real model data for the predictions dashboard (webapp/data.js).

IN-SEASON mode (default, for the current 2026 season):
  - Current standings from games already played (actual results).
  - Game-by-game: played games show the full ensemble prediction + actual result;
    upcoming games (from the live ESPN schedule) show the Dixon-Coles projection.
  - Season odds (playoff / top-4 home field / Supporters' Shield / wooden spoon) from
    Monte-Carlo: start at current points, simulate the REMAINING ESPN fixtures via DC.

Emits webapp/data.js as `window.MLS_DATA = {...}` (inlined to open over file://).
Usage: python scripts/build_dashboard_data.py [--season 2026] [--sims 20000]
"""

import argparse
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import urllib3

urllib3.disable_warnings()
sys.path.insert(0, str(Path(__file__).parent.parent))

_ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1"
_HDR = {"User-Agent": "Mozilla/5.0"}

# MLS 2026 conferences (30 teams; San Diego FC added 2025)
_EAST = {"atlanta united fc", "charlotte fc", "chicago fire fc", "fc cincinnati",
         "columbus crew", "dc united", "inter miami cf", "cf montreal", "nashville sc",
         "new england revolution", "new york city fc", "new york red bulls",
         "orlando city sc", "philadelphia union", "toronto fc"}
_WEST = {"austin fc", "colorado rapids", "fc dallas", "houston dynamo fc", "la galaxy",
         "los angeles fc", "minnesota united fc", "portland timbers fc", "real salt lake",
         "san diego fc", "san jose earthquakes", "seattle sounders fc",
         "sporting kansas city", "st louis city sc", "vancouver whitecaps fc"}
_PLAYOFF_SLOTS, _HFA_SLOTS = 9, 4
_SUFFIX = {"fc", "sc", "cf"}
_ALIAS = {"lafc": "los angeles fc", "red bull new york": "new york red bulls"}


def _norm(n):
    n = unicodedata.normalize("NFKD", str(n)).encode("ascii", "ignore").decode()
    return "".join(c for c in n.lower() if c.isalnum() or c == " ").strip()


def _conf(nn):
    return "East" if nn in _EAST else "West" if nn in _WEST else None


def _toks(nn):
    return tuple(t for t in nn.split() if t not in _SUFFIX)


def espn_schedule(season):
    """Return list of fixtures: (date, home_norm, away_norm, status, hg, ag)."""
    r = requests.get(f"{_ESPN}/scoreboard",
                     params={"dates": f"{season}0201-{season}1215", "limit": 1000},
                     headers=_HDR, verify=False, timeout=30).json()
    out = []
    for e in r.get("events", []):
        comp = e["competitions"][0]
        cs = {x["homeAway"]: x for x in comp["competitors"]}
        if "home" not in cs or "away" not in cs:
            continue
        state = e.get("status", {}).get("type", {}).get("state", "")
        hg = ag = None
        if state == "post":
            try:
                hg, ag = int(cs["home"]["score"]), int(cs["away"]["score"])
            except Exception:
                pass
        out.append((e["date"][:10], _norm(cs["home"]["team"]["displayName"]),
                    _norm(cs["away"]["team"]["displayName"]), state, hg, ag))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--sims", type=int, default=20000)
    args = ap.parse_args()
    ts = args.season

    meta = json.loads(Path(args.frame).with_suffix(".meta.json").read_text())
    feat_base = meta["feat_base"]
    # Frame may be parquet (if a parquet engine is installed) or pickle (fallback).
    _frame = Path(args.frame)
    if not _frame.exists() and _frame.with_suffix(".pkl").exists():
        _frame = _frame.with_suffix(".pkl")
    try:
        df = pd.read_parquet(_frame)
    except Exception:
        df = pd.read_pickle(_frame)
    df["date"] = pd.to_datetime(df["date"])

    from models.research_model import (fit_dc, dc_predict_batch, fit_xgb, bag_proba,
                                        calibrate_temperature, fit_capped_blend, blend)
    from itscalledsoccer.client import AmericanSoccerAnalysis
    import models.research_model as rm
    asa = AmericanSoccerAnalysis(); asa.session.verify = False
    teams = asa.get_teams(leagues="mls")
    id2name = {r.team_id: r.team_name for r in teams.itertuples()}
    # ESPN-normalized-name -> ASA team_id (suffix-tolerant + alias)
    tok2id = {_toks(_norm(r.team_name)): r.team_id for r in teams.itertuples()}

    def map_team(norm_name):
        nn = _ALIAS.get(norm_name, norm_name)
        return tok2id.get(_toks(nn))

    # ESPN team crest URL + brand colors, keyed by ASA team_id (public CDN; <img> ref)
    tmeta = {}
    try:
        tj = requests.get(f"{_ESPN}/teams", params={"limit": 50},
                          headers=_HDR, verify=False, timeout=25).json()
        for it in tj["sports"][0]["leagues"][0]["teams"]:
            tm = it["team"]; tid = map_team(_norm(tm["displayName"]))
            if not tid:
                continue
            tmeta[tid] = {"logo": (tm.get("logos") or [{}])[0].get("href"),
                          "color": "#" + (tm.get("color") or "8a93a6"),
                          "color2": "#" + (tm.get("alternateColor") or "44506a")}
    except Exception as e:
        print("team meta fetch failed:", e)

    def meta(tid):
        return tmeta.get(tid, {})

    feat = [c for c in feat_base if c in df.columns]
    played = df[(df["season"] == ts) & df["home_goals"].notna()].dropna(
        subset=["home_goals", "away_goals"]).copy()
    print(f"In-season {ts}: {len(played)} games played in the frame.")

    # ── Ensemble predictions for PLAYED games (game-by-game accuracy) ─────────
    train = df[df["season"] < ts - 1].dropna(subset=["home_goals", "away_goals"])
    cal = df[df["season"] == ts - 1].dropna(subset=["home_goals", "away_goals"])
    y_cal = cal["label_result"].values.astype(int); y_cal_oh = np.eye(3)[y_cal]
    atk0, dfd0, ha0, rho0 = fit_dc(train)
    dccal = calibrate_temperature(dc_predict_batch(cal, atk0, dfd0, ha0, rho0), y_cal,
                                  dc_predict_batch(cal, atk0, dfd0, ha0, rho0))
    dcte = calibrate_temperature(dc_predict_batch(cal, atk0, dfd0, ha0, rho0), y_cal,
                                 dc_predict_batch(played, atk0, dfd0, ha0, rho0))
    clfs, _ = fit_xgb(train, feat)
    xc = bag_proba(clfs, cal[feat].fillna(0).values)
    xt = bag_proba(clfs, played[feat].fillna(0).values)
    xgbcal = calibrate_temperature(xc, y_cal, xc); xgbte = calibrate_temperature(xc, y_cal, xt)
    w = fit_capped_blend(xgbcal, dccal, y_cal_oh)
    pe = blend(xgbte, dcte, w)
    played = played.reset_index(drop=True)

    # ── Dixon-Coles fit on ALL played-through-now (forward projection) ────────
    allplayed = df[df["home_goals"].notna()].dropna(subset=["home_goals", "away_goals"])
    atk, dfd, ha, rho = fit_dc(allplayed)

    def dc_probs(htid, atid):
        return rm._dc_predict(htid, atid, atk, dfd, ha, rho)   # (pH, pD, pA)

    # ── Current standings from played frame games (pts, GD, xGD) ─────────────
    pts, gp, gf, ga, xgf, xga = {}, {}, {}, {}, {}, {}
    for _, r in played.iterrows():
        h, a = r["home_team"], r["away_team"]
        if _conf(_norm(id2name.get(h, ""))) is None: continue
        hg, ag = r["home_goals"], r["away_goals"]
        hx, ax = float(np.nan_to_num(r["home_xg"])), float(np.nan_to_num(r["away_xg"]))
        for t in (h, a): gp[t] = gp.get(t, 0) + 1
        gf[h] = gf.get(h, 0) + hg; ga[h] = ga.get(h, 0) + ag
        gf[a] = gf.get(a, 0) + ag; ga[a] = ga.get(a, 0) + hg
        xgf[h] = xgf.get(h, 0) + hx; xga[h] = xga.get(h, 0) + ax
        xgf[a] = xgf.get(a, 0) + ax; xga[a] = xga.get(a, 0) + hx
        if hg > ag: pts[h] = pts.get(h, 0) + 3
        elif hg < ag: pts[a] = pts.get(a, 0) + 3
        else: pts[h] = pts.get(h, 0) + 1; pts[a] = pts.get(a, 0) + 1

    # ── ESPN schedule: played (for game cards) + remaining (for sim/cards) ────
    sched = espn_schedule(ts)
    remaining = []   # (htid, atid) for unplayed MLS fixtures
    upcoming_cards = []
    for date, hn, an, state, hg, ag in sched:
        htid, atid = map_team(hn), map_team(an)
        if not htid or not atid:        # non-MLS (All-Star game, etc.)
            continue
        if (_conf(_norm(id2name.get(htid, ""))) is None or
                _conf(_norm(id2name.get(atid, ""))) is None):
            continue
        if state != "post":
            pH, pD, pA = dc_probs(htid, atid)
            remaining.append((htid, atid))
            upcoming_cards.append({"date": date, "home": id2name.get(htid), "away": id2name.get(atid),
                                   "pH": round(pH, 3), "pD": round(pD, 3), "pA": round(pA, 3),
                                   "hg": None, "ag": None, "result": None,
                                   "hlogo": meta(htid).get("logo"), "alogo": meta(atid).get("logo"),
                                   "hcolor": meta(htid).get("color"), "acolor": meta(atid).get("color")})

    # universe = all teams with a conference that appear in standings or schedule
    tids = {t for t in pts} | {t for fx in remaining for t in fx}
    tids = [t for t in tids if _conf(_norm(id2name.get(t, ""))) ]
    idx = {t: i for i, t in enumerate(tids)}; nT = len(tids)
    confs = np.array([_conf(_norm(id2name.get(t, ""))) for t in tids])
    base_pts = np.array([pts.get(t, 0) for t in tids], dtype=float)

    # ── Monte-Carlo: current points + simulate remaining via DC ──────────────
    rng = np.random.default_rng(42)
    RP = np.array([dc_probs(h, a) for (h, a) in remaining]) if remaining else np.zeros((0, 3))
    RH = np.array([idx[h] for (h, a) in remaining]); RA = np.array([idx[a] for (h, a) in remaining])
    N = args.sims
    playoff = np.zeros(nT); hfa = np.zeros(nT); shield = np.zeros(nT); spoon = np.zeros(nT)
    confwin = np.zeros(nT); proj = np.zeros(nT)
    east_i = np.where(confs == "East")[0]; west_i = np.where(confs == "West")[0]
    print(f"Simulating {N:,} seasons · {len(remaining)} remaining fixtures · {nT} teams...")
    for _ in range(N):
        p = base_pts.copy()
        if len(remaining):
            u = rng.random(len(remaining))
            o = np.where(u < RP[:, 0], 0, np.where(u < RP[:, 0] + RP[:, 1], 1, 2))
            np.add.at(p, RH[o == 0], 3)
            np.add.at(p, RH[o == 1], 1); np.add.at(p, RA[o == 1], 1)
            np.add.at(p, RA[o == 2], 3)
        proj += p
        j = p + rng.random(nT) * 0.01
        for ci in (east_i, west_i):
            order = ci[np.argsort(-j[ci])]
            playoff[order[:_PLAYOFF_SLOTS]] += 1; hfa[order[:_HFA_SLOTS]] += 1
            confwin[order[0]] += 1
        shield[np.argmax(j)] += 1; spoon[np.argmin(j)] += 1

    standings = []
    for t in tids:
        i = idx[t]
        standings.append({"team": id2name.get(t, t), "conf": confs[i],
                          "pts": int(base_pts[i]), "gp": gp.get(t, 0),
                          "gd": int(round(gf.get(t, 0) - ga.get(t, 0))),
                          "xgd": round(xgf.get(t, 0) - xga.get(t, 0), 1),
                          "proj_pts": round(proj[i] / N, 1),
                          "playoff": round(playoff[i] / N * 100, 1),
                          "hfa": round(hfa[i] / N * 100, 1),
                          "shield": round(shield[i] / N * 100, 1),
                          "spoon": round(spoon[i] / N * 100, 1),
                          "conf_win": round(confwin[i] / N * 100, 1),
                          "logo": meta(t).get("logo"), "color": meta(t).get("color")})
    standings.sort(key=lambda s: (-s["pts"], -s["gd"], -s["proj_pts"]))

    # ── Game cards: played (ensemble) + upcoming (DC) ────────────────────────
    games = []
    for i, r in played.iterrows():
        h, a = r["home_team"], r["away_team"]
        if _conf(_norm(id2name.get(h, ""))) is None or _conf(_norm(id2name.get(a, ""))) is None:
            continue
        res = "H" if r["home_goals"] > r["away_goals"] else "D" if r["home_goals"] == r["away_goals"] else "A"
        games.append({"date": r["date"].strftime("%Y-%m-%d"), "home": id2name.get(h), "away": id2name.get(a),
                      "pH": round(float(pe[i, 0]), 3), "pD": round(float(pe[i, 1]), 3),
                      "pA": round(float(pe[i, 2]), 3), "hg": int(r["home_goals"]),
                      "ag": int(r["away_goals"]), "result": res,
                      "hlogo": meta(h).get("logo"), "alogo": meta(a).get("logo"),
                      "hcolor": meta(h).get("color"), "acolor": meta(a).get("color")})
    games += upcoming_cards
    games.sort(key=lambda g: g["date"])

    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        git_commit = "unknown"

    data = {"season": ts, "in_season": True,
            "played": len(games) - len(upcoming_cards), "upcoming": len(upcoming_cards),
            "model": {"best_brier": 0.6347, "naive": 0.6406, "improve_pct": 0.92,
                      "name": "research_model", "metric": "brier_sum_form"},
            "n_sims": N, "playoff_slots": _PLAYOFF_SLOTS, "hfa_slots": _HFA_SLOTS,
            "standings": standings, "games": games,
            "generated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "provenance": {"git_commit": git_commit,
                           "model_file": "models/research_model.py",
                           "metric_convention": "brier_sum_form (range 0-2; random ~0.6406)"}}
    out = Path("webapp/data.js")
    out.write_text("window.MLS_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    print(f"Wrote {out} · {data['played']} played + {data['upcoming']} upcoming · {len(standings)} teams")
    for s in standings[:3]:
        print(f"  {s['team']:<22} {s['conf']} {s['pts']}pts/{s['gp']}gp  proj {s['proj_pts']}  "
              f"PO {s['playoff']}%  Shield {s['shield']}%")


if __name__ == "__main__":
    main()
