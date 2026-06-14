#!/usr/bin/env python3
"""
Multi-league dashboard data builder — single-table (European) leagues.

Produces webapp/data/<league>.js with the SAME payload schema the MLS build emits
(scripts/build_dashboard_data.py), but with league-table semantics instead of
MLS's conferences + playoff bracket + cup:

  - standings outcomes are Title / Top-4 (UCL) / Relegation, not playoff/shield/spoon
  - the season Monte-Carlo simulates remaining fixtures into a SINGLE final table
    (no bracket), via the same Dixon-Coles pairing probabilities
  - an `outlook` config block tells the webapp which favorite-cards + table markers
    to render (WS4 reads this; MLS keeps its hard-coded conference view)

Single data source: the Understat adapter (matches + xG + fixtures all come from
one place — upcoming fixtures are the is_result=False rows). Team crests + colors
are read from the ESPN coming-soon stub already scaffolded by
scripts/fetch_league_teams.py. The model + features are the shared, league-
agnostic pipeline (research_model + scripts/eval/league_features), unchanged.

Usage:
    python scripts/build_league_data.py --league epl
    python scripts/build_league_data.py --league la-liga --season 2025 --sims 20000
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))  # repo root on sys.path

from data_pipeline.understat import BIG5, canonical_frame, espn_name
from models.research_model import (
    bag_proba, blend, calibrate_temperature, dc_predict_batch, fit_capped_blend,
    fit_dc, fit_xgb,
)
import models.research_model as rm
from scripts.eval.elo import compute_elo
from scripts.eval.league_features import LEAGUE_FEAT_BASE, build_league_features

# ── Per-league outlook: competition structure for the single table ───────────
# title = 1st; ucl = top `ucl` places (Champions League league phase); releg =
# bottom `releg` places (relegation zone — Bundesliga/Ligue 1 fold their 16th-
# place relegation playoff into the zone for a v1 outcome bucket). Counts are the
# stable, widely-understood values; UEFA-coefficient extra spots are out of scope.
OUTLOOK = {
    "epl":        {"name": "English Premier League", "n": 20, "ucl": 4, "releg": 3},
    "la-liga":    {"name": "La Liga",                "n": 20, "ucl": 4, "releg": 3},
    "serie-a":    {"name": "Serie A",                "n": 20, "ucl": 4, "releg": 3},
    "bundesliga": {"name": "Bundesliga",             "n": 18, "ucl": 4, "releg": 3},
    "ligue-1":    {"name": "Ligue 1",                "n": 18, "ucl": 4, "releg": 3},
}


def _stub_team_meta(league_id: str) -> dict[str, dict]:
    """Team-name → {logo, color} for crest/color lookup.

    Idempotent across rebuilds: reads the coming-soon stub's `teams[]` (keyed by
    ESPN displayName) AND, when the file is already a live payload, its
    `standings[]` (keyed by Understat title). The builder OVERWRITES this same
    file, so without the standings fallback a second run would lose every crest.
    """
    stub = Path(f"webapp/data/{league_id}.js")
    if not stub.exists():
        return {}
    txt = stub.read_text()
    payload = json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))
    meta: dict[str, dict] = {}
    for t in payload.get("teams", []):          # coming-soon stub: ESPN displayName
        if t.get("logo") or t.get("color"):
            meta[t["name"]] = {"logo": t.get("logo"), "color": t.get("color")}
    for s in payload.get("standings", []):      # live payload: Understat title
        if s.get("logo") and s["team"] not in meta:
            meta[s["team"]] = {"logo": s.get("logo"), "color": s.get("color")}
    return meta


def _stub_league_logo(league_id: str) -> str | None:
    stub = Path(f"webapp/data/{league_id}.js")
    if not stub.exists():
        return None
    txt = stub.read_text()
    payload = json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))
    return (payload.get("league") or {}).get("logo")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", required=True, choices=BIG5)
    ap.add_argument("--season", type=int, default=None,
                    help="target season (default: latest with played matches)")
    ap.add_argument("--sims", type=int, default=20000)
    args = ap.parse_args()
    lid = args.league
    cfg = OUTLOOK[lid]

    # ── Load + feature-build the full history (played only) ───────────────────
    frame = canonical_frame(lid)
    played_all = frame[frame["is_result"]].copy()
    played_all["home_goals"] = played_all["home_goals"].astype(int)
    played_all["away_goals"] = played_all["away_goals"].astype(int)
    played_all["label_result"] = played_all["label_result"].astype(int)
    ts = args.season or int(played_all["season"].max())
    df = build_league_features(played_all)
    feat = [c for c in LEAGUE_FEAT_BASE if c in df.columns]

    played = df[df["season"] == ts].dropna(subset=["home_goals", "away_goals"]).copy()
    upcoming = frame[(frame["season"] == ts) & (~frame["is_result"])].copy()
    print(f"[{lid}] season {ts}: {len(played)} played, {len(upcoming)} upcoming, "
          f"{len(df)} historical matches, {len(feat)} features")

    # Team-name resolution: model keys are Understat titles; ESPN crests keyed by
    # displayName. tname() = the display string; tmeta() = its logo/color.
    stub_meta = _stub_team_meta(lid)

    def tmeta(title: str) -> dict:
        return stub_meta.get(espn_name(lid, title)) or stub_meta.get(title) or {}

    def tname(title: str) -> str:
        return title  # display the Understat title (already clean club names)

    # ── Ensemble predictions for PLAYED games (in-season Brier + game cards) ───
    train = df[df["season"] < ts - 1].dropna(subset=["home_goals", "away_goals"])
    cal = df[df["season"] == ts - 1].dropna(subset=["home_goals", "away_goals"])
    pe = None
    if len(train) >= 200 and len(cal) >= 50 and len(played) >= 1:
        y_cal = cal["label_result"].values.astype(int); y_cal_oh = np.eye(3)[y_cal]
        atk0, dfd0, ha0, rho0 = fit_dc(train)
        dccal = calibrate_temperature(dc_predict_batch(cal, atk0, dfd0, ha0, rho0), y_cal,
                                      dc_predict_batch(cal, atk0, dfd0, ha0, rho0))
        dcte = calibrate_temperature(dc_predict_batch(cal, atk0, dfd0, ha0, rho0), y_cal,
                                     dc_predict_batch(played, atk0, dfd0, ha0, rho0))
        clfs, _ = fit_xgb(train, feat)
        xc = bag_proba(clfs, cal[feat].fillna(0).values)
        xt = bag_proba(clfs, played[feat].fillna(0).values)
        xgbcal = calibrate_temperature(xc, y_cal, xc)
        xgbte = calibrate_temperature(xc, y_cal, xt)
        w = fit_capped_blend(xgbcal, dccal, y_cal_oh)
        pe = blend(xgbte, dcte, w)
    played = played.reset_index(drop=True)

    in_season_brier = {"status": "pending", "n_games": int(len(played))}
    if pe is not None and len(played):
        y_played = played["label_result"].values.astype(int)
        brier_live = float(np.mean(np.sum((pe - np.eye(3)[y_played]) ** 2, axis=1)))
        _freq = np.bincount(train["label_result"].values.astype(int), minlength=3) / len(train)
        naive_live = float(np.mean(np.sum(
            (np.tile(_freq, (len(played), 1)) - np.eye(3)[y_played]) ** 2, axis=1)))
        in_season_brier = {"model": round(brier_live, 4), "naive": round(naive_live, 4),
                           "n_games": int(len(played)),
                           "improve_pct": round((naive_live - brier_live) / naive_live * 100, 2)}
        print(f"[{lid}] in-season {ts} Brier: model {brier_live:.4f} vs naive {naive_live:.4f}")

    # European analog of MLS market-Brier (Understat's own forecast) is a future
    # enhancement — stub it like MLS stubs odds before they accumulate.
    market_brier = {"status": "pending", "n_games": 0,
                    "note": "Understat-forecast baseline not yet wired."}

    # ── Dixon-Coles on ALL played-through-now (forward projection + pmatrix) ───
    allplayed = df.dropna(subset=["home_goals", "away_goals"])
    atk, dfd, ha, rho = fit_dc(allplayed)

    def dc_probs(h, a):
        return rm._dc_predict(h, a, atk, dfd, ha, rho)

    def dc_lam_mu(h, a):
        import math
        return (math.exp(atk.get(h, 0) + dfd.get(a, 0) + ha),
                math.exp(atk.get(a, 0) + dfd.get(h, 0)))

    # ── Current ELO (champion config) + standings from this season's results ──
    _elo_df, elo_now = compute_elo(allplayed.sort_values("date"), K=25, home_adv=80,
                                   regress=0.40, return_ratings=True)
    pts, gp, gf, ga, xgf, xga = {}, {}, {}, {}, {}, {}
    for _, r in played.iterrows():
        h, a = r["home_team"], r["away_team"]
        hg, ag = int(r["home_goals"]), int(r["away_goals"])
        hx, ax = float(np.nan_to_num(r["home_xg"])), float(np.nan_to_num(r["away_xg"]))
        for t in (h, a):
            gp[t] = gp.get(t, 0) + 1
        gf[h] = gf.get(h, 0) + hg; ga[h] = ga.get(h, 0) + ag
        gf[a] = gf.get(a, 0) + ag; ga[a] = ga.get(a, 0) + hg
        xgf[h] = xgf.get(h, 0) + hx; xga[h] = xga.get(h, 0) + ax
        xgf[a] = xgf.get(a, 0) + ax; xga[a] = xga.get(a, 0) + hx
        if hg > ag: pts[h] = pts.get(h, 0) + 3
        elif hg < ag: pts[a] = pts.get(a, 0) + 3
        else: pts[h] = pts.get(h, 0) + 1; pts[a] = pts.get(a, 0) + 1

    # ── Upcoming fixtures → game cards + remaining-sim inputs ──────────────────
    remaining, upcoming_cards = [], []
    for _, r in upcoming.sort_values("date").iterrows():
        h, a = r["home_team"], r["away_team"]
        pH, pD, pA = dc_probs(h, a)
        lam, mu = dc_lam_mu(h, a)
        upcoming_cards.append({"id": len(remaining), "date": r["date"].strftime("%Y-%m-%d"),
                               "home": tname(h), "away": tname(a),
                               "pH": round(pH, 3), "pD": round(pD, 3), "pA": round(pA, 3),
                               "lam": round(lam, 2), "mu": round(mu, 2),
                               "hg": None, "ag": None, "result": None,
                               "hlogo": tmeta(h).get("logo"), "alogo": tmeta(a).get("logo"),
                               "hcolor": tmeta(h).get("color"), "acolor": tmeta(a).get("color")})
        remaining.append((h, a))

    # universe = teams that appear in this season's results or remaining fixtures
    tids = sorted({t for t in pts} | {t for fx in remaining for t in fx})
    idx = {t: i for i, t in enumerate(tids)}; nT = len(tids)
    base_pts = np.array([pts.get(t, 0) for t in tids], dtype=float)
    base_gd = np.array([gf.get(t, 0) - ga.get(t, 0) for t in tids], dtype=float)

    # Pairing-probability matrix (powers the client what-if sim; row = host)
    PM = np.zeros((nT, nT, 3))
    for hi, th in enumerate(tids):
        for ai, ta in enumerate(tids):
            if hi != ai:
                PM[hi, ai] = dc_probs(th, ta)

    # ── Monte-Carlo: current pts + simulate remaining → SINGLE final table ────
    rng = np.random.default_rng(42)
    RP = np.array([dc_probs(h, a) for (h, a) in remaining]) if remaining else np.zeros((0, 3))
    RH = np.array([idx[h] for (h, a) in remaining], dtype=int)
    RA = np.array([idx[a] for (h, a) in remaining], dtype=int)
    N = args.sims
    ucl_n, releg_n = cfg["ucl"], cfg["releg"]
    title = np.zeros(nT); ucl = np.zeros(nT); releg = np.zeros(nT)
    proj = np.zeros(nT); rank_sum = np.zeros(nT)
    print(f"[{lid}] simulating {N:,} seasons · {len(remaining)} remaining · {nT} teams...")
    for _ in range(N):
        p = base_pts.copy()
        if len(remaining):
            u = rng.random(len(remaining))
            o = np.where(u < RP[:, 0], 0, np.where(u < RP[:, 0] + RP[:, 1], 1, 2))
            np.add.at(p, RH[o == 0], 3)
            np.add.at(p, RH[o == 1], 1); np.add.at(p, RA[o == 1], 1)
            np.add.at(p, RA[o == 2], 3)
        proj += p
        # Final ranking: points → current real GD → random (tie jitter)
        key = p * 10000 + base_gd * 10 + rng.random(nT) * 10
        order = np.argsort(-key)  # best first
        title[order[0]] += 1
        ucl[order[:ucl_n]] += 1
        releg[order[nT - releg_n:]] += 1
        rank_sum[order] += np.arange(1, nT + 1)

    standings = []
    for t in tids:
        i = idx[t]
        standings.append({"team": tname(t),
                          "pts": int(base_pts[i]), "gp": gp.get(t, 0),
                          "gd": int(round(gf.get(t, 0) - ga.get(t, 0))),
                          "xgd": round(xgf.get(t, 0) - xga.get(t, 0), 1),
                          "proj_pts": round(proj[i] / N, 1),
                          "proj_rank": round(rank_sum[i] / N, 1),
                          "title": round(title[i] / N * 100, 1),
                          "ucl": round(ucl[i] / N * 100, 1),
                          "releg": round(releg[i] / N * 100, 1),
                          "elo": int(round(elo_now.get(t, 1500))),
                          "logo": tmeta(t).get("logo"), "color": tmeta(t).get("color")})
    standings.sort(key=lambda s: (-s["pts"], -s["gd"], -s["proj_pts"]))

    # ── Per-team current model inputs (latest rolling snapshot) ───────────────
    team_inputs = {}
    _df_s = df.sort_values("date")
    _input_cols = {"xg_for": ("home_xg_roll_5", "away_xg_roll_5"),
                   "xg_against": ("home_xga_roll_5", "away_xga_roll_5"),
                   "form": ("home_form_5", "away_form_5")}
    for t in tids:
        _rows = _df_s[(_df_s["home_team"] == t) | (_df_s["away_team"] == t)]
        if _rows.empty:
            continue
        _last = _rows.iloc[-1]; _is_home = _last["home_team"] == t
        snap = {"elo": int(round(elo_now.get(t, 1500)))}
        for _lab, (_hc, _ac) in _input_cols.items():
            _v = _last.get(_hc if _is_home else _ac)
            snap[_lab] = round(float(_v), 3) if _v is not None and pd.notna(_v) else None
        team_inputs[tname(t)] = snap

    # ── ELO history (full Understat depth, 2014+) per team, downsampled ───────
    elo_hist = {}
    for t in tids:
        _hm = _elo_df[_elo_df["home_team"] == t][["date", "home_elo"]].rename(columns={"home_elo": "elo"})
        _aw = _elo_df[_elo_df["away_team"] == t][["date", "away_elo"]].rename(columns={"away_elo": "elo"})
        _ser = pd.concat([_hm, _aw]).sort_values("date")
        if _ser.empty:
            continue
        _step = max(1, len(_ser) // 120)
        elo_hist[tname(t)] = [[d.strftime("%Y-%m-%d"), int(round(e))]
                              for d, e in zip(_ser["date"].iloc[::_step], _ser["elo"].iloc[::_step])]

    # ── Game cards: played (ensemble if available, else DC) + upcoming ────────
    games = []
    for i, r in played.iterrows():
        h, a = r["home_team"], r["away_team"]
        res = "H" if r["home_goals"] > r["away_goals"] else "D" if r["home_goals"] == r["away_goals"] else "A"
        _lam, _mu = dc_lam_mu(h, a)
        if pe is not None:
            pH, pD, pA = float(pe[i, 0]), float(pe[i, 1]), float(pe[i, 2])
        else:
            pH, pD, pA = dc_probs(h, a)
        games.append({"date": r["date"].strftime("%Y-%m-%d"), "home": tname(h), "away": tname(a),
                      "pH": round(pH, 3), "pD": round(pD, 3), "pA": round(pA, 3),
                      "lam": round(_lam, 2), "mu": round(_mu, 2),
                      "hg": int(r["home_goals"]), "ag": int(r["away_goals"]), "result": res,
                      "hlogo": tmeta(h).get("logo"), "alogo": tmeta(a).get("logo"),
                      "hcolor": tmeta(h).get("color"), "acolor": tmeta(a).get("color")})
    games += upcoming_cards
    games.sort(key=lambda g: g["date"])

    # ── Per-year model vs naive vs market (walk-forward predictions + bookmaker odds) ──
    # Per-match model probs let us score the model, the base-rate naive, AND the
    # betting market on the SAME matched matches per season — a fair "are we beating
    # the bookies?" read. Market odds from football-data.co.uk (Pinnacle/market-avg).
    from models.research_model import walk_forward_predictions
    from data_pipeline.football_data import DIV as _FD_DIV, attach_market
    perf_by_year = []
    try:
        _pyears = [y for y in (2017, 2019, 2021, 2022, 2023, 2024, 2025) if y in set(df["season"])]
        _preds, _ = walk_forward_predictions(df, feat, _pyears, n_bags=1)
        if lid in _FD_DIV and not _preds.empty:
            _preds = attach_market(_preds, lid, _pyears)
        _has_mkt = "mkt_home" in _preds.columns
        for _y in _pyears:
            _g = _preds[_preds["season"] == _y]
            if _g.empty:
                continue
            _yoh = np.eye(3)[_g["label_result"].values.astype(int)]
            _model_b = float(np.mean(np.sum(
                (_g[["prob_home", "prob_draw", "prob_away"]].values - _yoh) ** 2, axis=1)))
            _tr = df[df["season"] < _y - 1].dropna(subset=["label_result"])
            _fq = np.bincount(_tr["label_result"].values.astype(int), minlength=3) / max(len(_tr), 1)
            _nb = float(np.mean(np.sum((np.tile(_fq, (len(_g), 1)) - _yoh) ** 2, axis=1)))
            _rec = {"year": _y, "model": round(_model_b, 4), "naive": round(_nb, 4),
                    "improve_pct": round((_nb - _model_b) / _nb * 100, 2)}
            if _has_mkt and int(_g["mkt_home"].notna().sum()) >= 20:
                _gm = _g[_g["mkt_home"].notna()]
                _ym = np.eye(3)[_gm["label_result"].values.astype(int)]
                _mkt_b = float(np.mean(np.sum(
                    (_gm[["mkt_home", "mkt_draw", "mkt_away"]].values - _ym) ** 2, axis=1)))
                _mm = float(np.mean(np.sum(  # model on the SAME matched matches (fair)
                    (_gm[["prob_home", "prob_draw", "prob_away"]].values - _ym) ** 2, axis=1)))
                _rec["market"] = round(_mkt_b, 4)
                _rec["edge_pct"] = round((_mkt_b - _mm) / _mkt_b * 100, 2)  # +ve = model beats market
            perf_by_year.append(_rec)
        print(f"[{lid}] perf by year: {[(p['year'], p['model'], p.get('market')) for p in perf_by_year]}")
    except Exception as _e:
        import traceback
        traceback.print_exc()
        print(f"[{lid}] perf_by_year failed: {_e}")

    # Headline league Brier = mean of the recent (2022+) walk-forward folds.
    _recent = [p for p in perf_by_year if p["year"] >= 2022]
    league_brier = round(float(np.mean([p["model"] for p in _recent])), 4) if _recent else None
    league_naive = round(float(np.mean([p["naive"] for p in _recent])), 4) if _recent else None
    _recent_mkt = [p for p in _recent if p.get("market") is not None]
    league_market = round(float(np.mean([p["market"] for p in _recent_mkt])), 4) if _recent_mkt else None
    if _recent_mkt:
        market_brier = {"status": "ok", "market": league_market, "model": league_brier,
                        "edge_pct": round(float(np.mean([p["edge_pct"] for p in _recent_mkt])), 2),
                        "n_years": len(_recent_mkt), "source": "football-data.co.uk (Pinnacle/avg)"}

    # ── Model-health block: league-agnostic feature families ──────────────────
    _FAMS = {"ELO": [c for c in feat if "elo" in c],
             "xG rolling": [c for c in feat if "xg" in c and "elo" not in c],
             "Form": [c for c in feat if "form" in c],
             "is_playoff": [c for c in feat if c == "is_playoff"]}
    _rows = df[df["season"] == ts]
    health = {"frame_file": f"understat:{lid}", "espn_ok": bool(stub_meta),
              "season_rows": int(len(_rows)), "played_rows": int(len(played)),
              "features": [{"family": fam, "cols": len(cols),
                            "complete_pct": round(float(_rows[cols].notna().mean().mean() * 100), 1),
                            "nondefault_pct": round(float((_rows[cols] != 0).mean().mean() * 100), 1)}
                           for fam, cols in _FAMS.items() if cols]}

    model_card = {
        "arch": ["Dixon-Coles", "Temperature", "XGBoost ×5 bag", "Capped-DC blend", "Temperature"],
        "config": {"ELO K": 25, "Home adv": 80, "Season regress": "40%", "DC decay": "120d",
                   "XGB weight ½-life": "6 seasons", "Seed bag": 5,
                   "xG / form windows": "3 · 5 · 10 · 15", "features": len(feat)},
        "per_class": {}, "n_test": None}

    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        git_commit = "unknown"

    pct = round(len([g for g in games if g["result"]]) / max(1, len(games)) * 100)
    data = {
        "league": {"id": lid, "name": cfg["name"], "logo": _stub_league_logo(lid),
                   "confederation": "UEFA", "status": "live", "pct_complete": pct},
        "outlook": {"mode": "table", "n_teams": cfg["n"], "ucl_slots": ucl_n,
                    "releg_slots": releg_n,
                    "cards": [{"key": "title", "label": "Title"},
                              {"key": "ucl", "label": f"Top {ucl_n} (UCL)"},
                              {"key": "releg", "label": "Relegation"}],
                    "columns": [{"key": "title", "label": "Title"},
                                {"key": "ucl", "label": "UCL"},
                                {"key": "releg", "label": "Releg"}]},
        "perf_by_year": perf_by_year,
        "season": ts, "in_season": len(upcoming_cards) > 0,
        "played": len(games) - len(upcoming_cards), "upcoming": len(upcoming_cards),
        "sim": {"teams": [tname(t) for t in tids],
                "pmatrix": [[None if hi == ai else
                             [int(round(PM[hi, ai, k] * 1000)) for k in range(3)]
                             for ai in range(nT)] for hi in range(nT)]},
        "in_season_brier": in_season_brier,
        "market_brier": market_brier,
        "team_inputs": team_inputs,
        "elo_history": elo_hist,
        "trophies": {},   # European trophy data is a future enhancement
        "health": health,
        "model_card": model_card,
        "model": {"best_brier": league_brier, "naive": league_naive, "market": league_market,
                  "improve_pct": round((league_naive - league_brier) / league_naive * 100, 2)
                  if league_brier and league_naive else None,
                  "edge_pct": market_brier.get("edge_pct") if market_brier.get("status") == "ok" else None,
                  "cal_err": None, "name": "research_model", "metric": "brier_sum_form"},
        "n_sims": N,
        "standings": standings, "games": games,
        "generated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
        "provenance": {"git_commit": git_commit, "model_file": "models/research_model.py",
                       "data_source": f"understat:{lid}",
                       "metric_convention": "brier_sum_form (range 0-2; random ~0.64); "
                                            "league avg = recent walk-forward folds"}}

    out = Path(f"webapp/data/{lid}.js")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("window.LEAGUE_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    print(f"[{lid}] wrote {out} ({out.stat().st_size/1024:.0f} KB) · "
          f"{data['played']} played + {data['upcoming']} upcoming · {len(standings)} teams")
    for s in standings[:4]:
        print(f"    {s['team']:<22} {s['pts']}pts/{s['gp']}gp  proj {s['proj_pts']}  "
              f"title {s['title']}%  UCL {s['ucl']}%")


if __name__ == "__main__":
    main()
