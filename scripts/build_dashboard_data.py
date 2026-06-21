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

from scripts.payload_utils import write_js_payload, health_feature_stats  # noqa: E402

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
    from scripts.eval.elo import compute_elo
    from itscalledsoccer.client import AmericanSoccerAnalysis
    import math
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

    # ── In-season Brier (sum-form, matches the champion convention) ───────────
    y_played = played["label_result"].values.astype(int)
    brier_live = float(np.mean(np.sum((pe - np.eye(3)[y_played]) ** 2, axis=1)))
    _freq = np.bincount(train["label_result"].values.astype(int), minlength=3) / len(train)
    naive_live = float(np.mean(np.sum(
        (np.tile(_freq, (len(played), 1)) - np.eye(3)[y_played]) ** 2, axis=1)))
    in_season_brier = {
        "model": round(brier_live, 4), "naive": round(naive_live, 4),
        "n_games": int(len(played)),
        "improve_pct": round((naive_live - brier_live) / naive_live * 100, 2),
    }

    # ── Market (opening-line) Brier on the subset of played games with a logged
    #    opener. Self-populates over the season once ODDS_API_KEY logging runs;
    #    "pending" until model-predicted played games overlap logged openers. ───
    market_brier = {"status": "pending", "n_games": 0,
                    "note": "Add ODDS_API_KEY and run `make odds-log` daily; "
                            "opening lines accumulate for future games."}
    _olog = Path("data/odds_log.parquet")
    if _olog.exists():
        try:
            _od = pd.read_parquet(_olog)
            # de-vig per fixture → market implied [home,draw,away]
            _mkt = {}
            for _fk, _g in _od.groupby("fixture_key"):
                _imp = {r.outcome: 1.0 / r.decimal_odds for r in _g.itertuples()
                        if r.decimal_odds and r.decimal_odds > 1}
                if {"home", "draw", "away"} <= set(_imp):
                    _s = _imp["home"] + _imp["draw"] + _imp["away"]
                    # key: (home_id, away_id, YYYY-MM-DD)
                    _hn, _an = _g.iloc[0]["home_team"], _g.iloc[0]["away_team"]
                    _hid, _aid = map_team(_norm(_hn)), map_team(_norm(_an))
                    _dt = str(_g.iloc[0]["commence_time"])[:10]
                    if _hid and _aid:
                        _mkt[(_hid, _aid, _dt)] = np.array(
                            [_imp["home"], _imp["draw"], _imp["away"]]) / _s
            # overlap with model-predicted played games
            _mp, _mk, _yy = [], [], []
            for _i, _r in played.iterrows():
                _k = (_r["home_team"], _r["away_team"], _r["date"].strftime("%Y-%m-%d"))
                if _k in _mkt:
                    _mp.append(pe[_i]); _mk.append(_mkt[_k]); _yy.append(int(_r["label_result"]))
            if len(_yy) >= 10:
                _yoh = np.eye(3)[np.array(_yy)]
                _bm = float(np.mean(np.sum((np.array(_mk) - _yoh) ** 2, axis=1)))
                _bmod = float(np.mean(np.sum((np.array(_mp) - _yoh) ** 2, axis=1)))
                market_brier = {"status": "ok", "n_games": len(_yy),
                                "market": round(_bm, 4), "model": round(_bmod, 4),
                                "edge_pct": round((_bm - _bmod) / _bm * 100, 2)}
        except Exception as _e:
            market_brier = {"status": "error", "n_games": 0, "note": str(_e)}
    print(f"Market Brier: {market_brier.get('status')} "
          f"(n={market_brier.get('n_games', 0)})")

    print(f"In-season {ts} Brier: model {brier_live:.4f} vs naive {naive_live:.4f} "
          f"(n={len(played)})")

    # ── Dixon-Coles fit on ALL played-through-now (forward projection) ────────
    allplayed = df[df["home_goals"].notna()].dropna(subset=["home_goals", "away_goals"])
    atk, dfd, ha, rho = fit_dc(allplayed)

    def dc_probs(htid, atid):
        return rm._dc_predict(htid, atid, atk, dfd, ha, rho)   # (pH, pD, pA)

    def dc_lam_mu(htid, atid):
        """Raw DC expected goals (home λ, away μ) — projected scoreline."""
        return (math.exp(atk.get(htid, 0) + dfd.get(atid, 0) + ha),
                math.exp(atk.get(atid, 0) + dfd.get(htid, 0)))

    # ── Current ELO ratings (champion config; post-latest-match values) ───────
    _elo_df, elo_now = compute_elo(allplayed.sort_values("date"), K=25, home_adv=80,
                                   regress=0.40, return_ratings=True)

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
            lam, mu = dc_lam_mu(htid, atid)
            # CONTRACT: "id" = index into the remaining/RP sim arrays (assignment
            # order here), NOT display order — games are re-sorted by date below.
            # The client what-if sim must key fixtures by id, never by position.
            upcoming_cards.append({"id": len(remaining),
                                   "date": date, "home": id2name.get(htid), "away": id2name.get(atid),
                                   "pH": round(pH, 3), "pD": round(pD, 3), "pA": round(pA, 3),
                                   "lam": round(lam, 2), "mu": round(mu, 2),
                                   "hg": None, "ag": None, "result": None,
                                   "hlogo": meta(htid).get("logo"), "alogo": meta(atid).get("logo"),
                                   "hcolor": meta(htid).get("color"), "acolor": meta(atid).get("color")})
            remaining.append((htid, atid))

    # universe = all teams with a conference that appear in standings or schedule
    tids = {t for t in pts} | {t for fx in remaining for t in fx}
    tids = [t for t in tids if _conf(_norm(id2name.get(t, ""))) ]
    idx = {t: i for i, t in enumerate(tids)}; nT = len(tids)
    confs = np.array([_conf(_norm(id2name.get(t, ""))) for t in tids])
    base_pts = np.array([pts.get(t, 0) for t in tids], dtype=float)

    # ── Pairing-probability matrix (powers the cup sim here AND the client
    #    what-if sim — shipped in data.js as sim.pmatrix, ints x1000, row=host) ──
    PM = np.zeros((nT, nT, 3))
    for hi, th in enumerate(tids):
        for ai, ta in enumerate(tids):
            if hi != ai:
                PM[hi, ai] = dc_probs(th, ta)

    def _pwin_pk(hi, ai):
        """Host win prob, PK rounds (wild card + Bo3 round one: straight to PKs
        after 90'; PKs modeled 50/50)."""
        ph, pd_, _pa = PM[hi, ai]
        return ph + 0.5 * pd_

    def _pwin_et(hi, ai):
        """Host win prob, ET rounds (semis/final/Cup: extra time favors the
        better side → proportional draw split)."""
        ph, pd_, pa = PM[hi, ai]
        return ph + (pd_ * ph / (ph + pa) if (ph + pa) > 1e-9 else 0.5 * pd_)

    # ════════════════════════════════════════════════════════════════════════
    # SIM PORTING CONTRACT (Python here ↔ JS in webapp/index.html — any rule
    # change must be made in BOTH places):
    #  1. Regular season: start from current pts; each remaining fixture sampled
    #     from its DC [pH,pD,pA]; W=3/D=1/L=0. (Client: forced fixtures are
    #     deterministic.)
    #  2. Seeding key: pts*10000 + current_real_GD*10 + U(0,10), descending per
    #     conference. Playoffs = top 9; HFA = top 4; conf winner = #1;
    #     Shield = best key overall; Spoon = worst key overall.
    #  3. Bracket: wild card 8 hosts 9 (pW = pH + 0.5*pD); round one Bo3
    #     1v8/2v7/3v6/4v5, higher seed hosts G1+G3, lower hosts G2, each game
    #     pW = pH + 0.5*pD, first to 2; semis W(1v8)vW(4v5) and W(2v7)vW(3v6),
    #     then conf final — single match, higher seed hosts,
    #     pW = pH + pD*pH/(pH+pA); MLS Cup hosted by the finalist with the
    #     higher seeding key.
    #  4. All pairing probs from the same 30x30 pmatrix (row = host).
    #  5. Acceptance: unforced client sim @10k within ±1.5pp of server @20k.
    # ════════════════════════════════════════════════════════════════════════

    def _conf_bracket(seeds, rng):
        """seeds: 9 team indices, best first. Returns conference champion idx."""
        wc = seeds[7] if rng.random() < _pwin_pk(seeds[7], seeds[8]) else seeds[8]
        r1 = [(seeds[0], wc), (seeds[1], seeds[6]), (seeds[2], seeds[5]),
              (seeds[3], seeds[4])]
        rank = {t: i for i, t in enumerate(seeds)}
        winners = []
        for hi, lo in r1:                      # best-of-3, G1+G3 at hi, G2 at lo
            w_hi = w_lo = 0
            for g in range(3):
                host, guest = (hi, lo) if g != 1 else (lo, hi)
                host_won = rng.random() < _pwin_pk(host, guest)
                if (host_won and host == hi) or (not host_won and host == lo):
                    w_hi += 1
                else:
                    w_lo += 1
                if w_hi == 2 or w_lo == 2:
                    break
            winners.append(hi if w_hi == 2 else lo)

        def _single(t1, t2):                   # higher seed hosts, ET rules
            host, guest = (t1, t2) if rank[t1] < rank[t2] else (t2, t1)
            return host if rng.random() < _pwin_et(host, guest) else guest

        return _single(_single(winners[0], winners[3]),
                       _single(winners[1], winners[2]))

    # ── Monte-Carlo: current points + simulate remaining via DC + playoffs ───
    rng = np.random.default_rng(42)
    RP = np.array([dc_probs(h, a) for (h, a) in remaining]) if remaining else np.zeros((0, 3))
    RH = np.array([idx[h] for (h, a) in remaining]); RA = np.array([idx[a] for (h, a) in remaining])
    N = args.sims
    base_gd = np.array([gf.get(t, 0) - ga.get(t, 0) for t in tids], dtype=float)
    playoff = np.zeros(nT); hfa = np.zeros(nT); shield = np.zeros(nT); spoon = np.zeros(nT)
    confwin = np.zeros(nT); proj = np.zeros(nT); cup = np.zeros(nT)
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
        # Tiebreak per the porting contract: points → current real GD → random
        j = p * 10000 + base_gd * 10 + rng.random(nT) * 10
        finalists = []
        for ci in (east_i, west_i):
            order = ci[np.argsort(-j[ci])]
            playoff[order[:_PLAYOFF_SLOTS]] += 1; hfa[order[:_HFA_SLOTS]] += 1
            confwin[order[0]] += 1
            finalists.append(_conf_bracket(list(order[:9]), rng))
        shield[np.argmax(j)] += 1; spoon[np.argmin(j)] += 1
        # MLS Cup: hosted by the finalist with the higher seeding key
        f1, f2 = finalists
        host, guest = (f1, f2) if j[f1] >= j[f2] else (f2, f1)
        cup[host if rng.random() < _pwin_et(host, guest) else guest] += 1

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
                          "cup": round(cup[i] / N * 100, 1),
                          "elo": int(round(elo_now.get(t, 1500))),
                          "logo": meta(t).get("logo"), "color": meta(t).get("color")})
    standings.sort(key=lambda s: (-s["pts"], -s["gd"], -s["proj_pts"]))

    # ── Per-team current model inputs (latest rolling feature snapshot) ───────
    # For each team, the most recent match's own-side rolling features — the
    # actual quantities the model consumes. Drawn from the frozen feature frame.
    _team_inputs = {}
    _df_s = df.sort_values("date")
    _input_cols = {  # display label -> (home_col, away_col)
        "xg_for": ("home_xg_roll_5", "away_xg_roll_5"),
        "xg_against": ("home_xga_roll_5", "away_xga_roll_5"),
        "form": ("home_form_5", "away_form_5"),
        "gk_z": ("home_gk_z", "away_gk_z"),
        "avail": ("home_avail_share", "away_avail_share"),
    }
    for _t in tids:
        _name = id2name.get(_t, _t)
        _rows = _df_s[(_df_s["home_team"] == _t) | (_df_s["away_team"] == _t)]
        if _rows.empty:
            continue
        _last = _rows.iloc[-1]
        _is_home = _last["home_team"] == _t
        _snap = {"elo": int(round(elo_now.get(_t, 1500)))}
        for _lab, (_hc, _ac) in _input_cols.items():
            _col = _hc if _is_home else _ac
            _v = _last.get(_col)
            _snap[_lab] = round(float(_v), 3) if _v is not None and pd.notna(_v) else None
        _team_inputs[_name] = _snap

    # ── ELO history (per-team trajectory, downsampled) + trophy annotations ───
    # Computed over the FULL ASA game history (2013+, deeper than the 2017+ model
    # frame) so the chart shows the complete trajectory under each trophy.
    try:
        _gh = asa.get_games(leagues="mls")
        _gh = _gh.rename(columns={"date_time_utc": "date", "home_team_id": "home_team",
                                  "away_team_id": "away_team", "home_score": "home_goals",
                                  "away_score": "away_goals", "season_name": "season"})
        _gh["date"] = pd.to_datetime(_gh["date"], errors="coerce", utc=True).dt.tz_localize(None)
        _gh["season"] = pd.to_numeric(_gh["season"], errors="coerce")
        _gh = _gh.dropna(subset=["date", "home_goals", "away_goals", "season"])
        _gh = _gh[_gh["season"] >= 2013].sort_values("date")
        _elo_full, _ = compute_elo(_gh, K=25, home_adv=80, regress=0.40, return_ratings=True)
    except Exception as _e:
        print(f"[warn] full ELO history fetch failed ({_e}); using model frame")
        _elo_full = _elo_df
    _elo_hist = {}
    for _t in tids:
        _name = id2name.get(_t, _t)
        _hm = _elo_full[_elo_full["home_team"] == _t][["date", "home_elo"]].rename(
            columns={"home_elo": "elo"})
        _aw = _elo_full[_elo_full["away_team"] == _t][["date", "away_elo"]].rename(
            columns={"away_elo": "elo"})
        _ser = pd.concat([_hm, _aw]).sort_values("date")
        if _ser.empty:
            continue
        # downsample to ~120 points max (keep every Nth) for payload size
        _step = max(1, len(_ser) // 120)
        _pts = [[d.strftime("%Y-%m-%d"), int(round(e))]
                for d, e in zip(_ser["date"].iloc[::_step], _ser["elo"].iloc[::_step])]
        _elo_hist[_name] = _pts

    from data_pipeline.trophies import trophies_for
    _trophies = {id2name.get(_t, _t): trophies_for(id2name.get(_t, _t)) for _t in tids}
    _trophies = {k: v for k, v in _trophies.items() if v}
    print(f"Team profiles: {len(_team_inputs)} | ELO history: "
          f"{sum(len(v) for v in _elo_hist.values())} points | "
          f"teams with trophies: {len(_trophies)}")

    # ── Game cards: played (ensemble) + upcoming (DC) ────────────────────────
    games = []
    for i, r in played.iterrows():
        h, a = r["home_team"], r["away_team"]
        if _conf(_norm(id2name.get(h, ""))) is None or _conf(_norm(id2name.get(a, ""))) is None:
            continue
        res = "H" if r["home_goals"] > r["away_goals"] else "D" if r["home_goals"] == r["away_goals"] else "A"
        _lam, _mu = dc_lam_mu(h, a)
        games.append({"date": r["date"].strftime("%Y-%m-%d"), "home": id2name.get(h), "away": id2name.get(a),
                      "pH": round(float(pe[i, 0]), 3), "pD": round(float(pe[i, 1]), 3),
                      "pA": round(float(pe[i, 2]), 3),
                      "lam": round(_lam, 2), "mu": round(_mu, 2),
                      "hg": int(r["home_goals"]),
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

    # Champion metrics come from the live pointer — never hardcode them here
    # (a stale 0.6347 literal sat in this file across two promotions).
    _naive = 0.6406
    champ_brier, champ_cal, champ_run = None, None, "unknown"
    model_card = {
        "arch": ["Dixon-Coles", "Temperature", "XGBoost ×5 bag", "Capped-DC blend", "Temperature"],
        "config": {"ELO K": 25, "Home adv": 80, "Season regress": "40%", "DC decay": "120d",
                   "XGB weight ½-life": "6 seasons", "Seed bag": 5, "xG / form windows": "3 · 5 · 10 · 15"},
        "per_class": {}, "n_test": None,
    }
    try:
        _ptr = json.loads(Path("experiments/champion.json").read_text())
        _rep = json.loads(Path(_ptr["report"]).read_text())
        champ_brier = float(_rep["avg_brier"])
        champ_cal = _rep.get("max_decile_cal_error")
        champ_run = _ptr.get("run_id", "unknown")
        _ov = _rep.get("overall", {})
        model_card["per_class"] = {k: round(_ov.get(f"brier_{k}", 0), 4) for k in ("home", "draw", "away")}
        model_card["n_test"] = _ov.get("n")
    except Exception as e:
        print(f"[warn] champion report unreadable ({e}); model card will lack metrics")

    # ── Model-health block: feature-family completeness over current-season rows
    _FAMS = {
        "ELO":          [c for c in feat if "elo" in c],
        "xG rolling":   [c for c in feat if "xg" in c and "elo" not in c],
        "Form":         [c for c in feat if "form" in c],
        "GK z-score":   [c for c in feat if "gk_z" in c],
        "Availability": [c for c in feat if "avail" in c],
        "is_playoff":   [c for c in feat if c == "is_playoff"],
    }
    _rows = df[df["season"] == ts]
    health = {
        "frame_file": str(_frame),
        "frame_mtime": pd.Timestamp(_frame.stat().st_mtime, unit="s").strftime("%Y-%m-%d %H:%M"),
        "espn_ok": True, "espn_events": len(sched),
        "season_rows": int(len(_rows)), "played_rows": int(len(played)),
        # complete = non-null share; nondefault = non-zero share (0 is the
        # fillna default at predict time). Both are per-column means averaged
        # across the family's columns, over current-season frame rows.
        "features": [
            {"family": fam, "cols": len(cols),
             **health_feature_stats(_rows, cols)}
            for fam, cols in _FAMS.items() if cols
        ],
    }

    # ── Per-year model vs naive (walk-forward; 2019 + 2022-2025; skip 2020/2021
    #    COVID cal-fold gap). Unbagged (n_bags=1) for build speed — a yearly
    #    display read; the headline champion 0.6330 stays the bagged number. ───
    from models.research_model import walk_forward
    perf_by_year = []
    try:
        _pyears = [y for y in (2019, 2022, 2023, 2024, 2025) if y in set(df["season"])]
        _wf = walk_forward(df, feat, _pyears, n_bags=1)
        for _y in _pyears:
            _ys = str(_y)
            _mb = _wf["per_season"].get(_ys)
            _tr = df[df["season"] < _y - 1].dropna(subset=["label_result"])
            _te = df[df["season"] == _y].dropna(subset=["label_result"])
            if _mb is None or _tr.empty or _te.empty:
                continue
            _fq = np.bincount(_tr["label_result"].values.astype(int), minlength=3) / len(_tr)
            _yo = np.eye(3)[_te["label_result"].values.astype(int)]
            _nb = float(np.mean(np.sum((np.tile(_fq, (len(_te), 1)) - _yo) ** 2, axis=1)))
            perf_by_year.append({"year": _y, "model": round(_mb, 4), "naive": round(_nb, 4),
                                 "improve_pct": round((_nb - _mb) / _nb * 100, 2)})
        print(f"Perf by year: {[(p['year'], p['model']) for p in perf_by_year]}")
    except Exception as _e:
        print(f"[warn] perf_by_year failed: {_e}")

    # ── League meta (multi-league platform) ──────────────────────────────────
    _lg_logo = None
    try:
        _lg_logo = (requests.get(f"{_ESPN}/scoreboard", headers=_HDR,
                    verify=False, timeout=20).json().get("leagues", [{}])[0]
                    .get("logos") or [{}])[0].get("href")
    except Exception:
        pass
    _pct = round(len([g for g in games if g["result"]]) /
                 max(1, len(games)) * 100)

    data = {"league": {"id": "mls", "name": "Major League Soccer", "logo": _lg_logo,
                       "confederation": "Concacaf", "status": "live",
                       "pct_complete": _pct},
            "perf_by_year": perf_by_year,
            "season": ts, "in_season": True,
            "played": len(games) - len(upcoming_cards), "upcoming": len(upcoming_cards),
            "sim": {"teams": [id2name.get(t, t) for t in tids],
                    "pmatrix": [[None if hi == ai else
                                 [int(round(PM[hi, ai, k] * 1000)) for k in range(3)]
                                 for ai in range(nT)] for hi in range(nT)]},
            "in_season_brier": in_season_brier,
            "market_brier": market_brier,
            "team_inputs": _team_inputs,
            "elo_history": _elo_hist,
            "trophies": _trophies,
            "health": health,
            "model_card": model_card,
            "model": {"best_brier": round(champ_brier, 4) if champ_brier else None,
                      "naive": _naive,
                      "improve_pct": round((_naive - champ_brier) / _naive * 100, 2)
                      if champ_brier else None,
                      "cal_err": champ_cal,
                      "name": "research_model", "metric": "brier_sum_form"},
            "n_sims": N, "playoff_slots": _PLAYOFF_SLOTS, "hfa_slots": _HFA_SLOTS,
            "standings": standings, "games": games,
            "generated": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
            "provenance": {"git_commit": git_commit,
                           "model_file": "models/research_model.py",
                           "champion_run": champ_run,
                           "metric_convention": "brier_sum_form (range 0-2; random ~0.6406); "
                                                "champion avg = 2022-2025 walk-forward"}}
    out = Path("webapp/data/mls.js")
    write_js_payload(out, "LEAGUE_DATA", data)
    _kb = out.stat().st_size / 1024
    print(f"Wrote {out} ({_kb:.0f} KB) · {data['played']} played + "
          f"{data['upcoming']} upcoming · {len(standings)} teams")
    for s in standings[:3]:
        print(f"  {s['team']:<22} {s['conf']} {s['pts']}pts/{s['gp']}gp  proj {s['proj_pts']}  "
              f"PO {s['playoff']}%  Shield {s['shield']}%")


if __name__ == "__main__":
    main()
