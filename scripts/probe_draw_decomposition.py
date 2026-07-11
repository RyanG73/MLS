#!/usr/bin/env python3
"""
Probe: per-match draw decomposition + offline sims for the draw-Brier campaign.

Phase 0 of docs/superpowers/plans/2026-07-11-draw-brier-campaign.md — discharges the
deferred M2.3-M2.5 diagnostic. Replicates the champion fold loop (models/research_model)
persisting every intermediate, so candidate interventions can be simulated offline
without harness runs:

  T1  Murphy decomposition of draw-class Brier (reliability vs resolution) per season
  T2  draw reliability by predicted-draw bin x lambda+mu quintile x season (settles M2)
  T3  component draw Brier: DC vs XGB vs hurdle vs blend pre/post second-pass temp
  T4  offline sims, honest (cal-fit) vs oracle (test-fit), per fold:
        B  per-class blend weights (w_ha, w_d) in [0.7,1.0]^2
        C  soft hurdle: p_d' = (1-a)*xgb_d + a*hur_d, H/A scaled, a in [0,1]
        D  (--with-ref-feat) XGB + ref_draw_rate, draw-only ratio-preserving recal

Correctness check: pooled champion output must reproduce challenger-bag5.report.json
(brier_draw 0.191867, draw_reliability bins) within noise.

This is a research probe; it does NOT modify the harness or production model.

Usage:
  python scripts/probe_draw_decomposition.py [--frame data/parity_frame.parquet]
      [--seed 42] [--with-ref-feat] [--out-dir experiments/draw_probe]
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.optimize import minimize_scalar
from sklearn.metrics import log_loss

from models.metrics import brier_multiclass_sum, per_class_brier, brier_binary
from models.research_model import (fit_dc, dc_predict_batch, fit_xgb, bag_proba,
                                   calibrate_temperature, fit_capped_blend, blend,
                                   _season_weights)

# Pinned. meta["test_seasons"] lists 2021 too, and the frame contains in-progress
# 2026 rows that are training-only — never derive the fold list from meta here.
TEST_SEASONS = (2022, 2023, 2024, 2025)
CHAMPION_REPORT = "experiments/challenger-bag5.report.json"


def _load_frame(frame_arg: str):
    frame = Path(frame_arg)
    meta_path = frame.with_suffix(".meta.json")
    if not frame.exists() and frame.with_suffix(".pkl").exists():
        frame = frame.with_suffix(".pkl")
    if not frame.exists() or not meta_path.exists():
        raise SystemExit(f"[probe] missing {frame} or {meta_path}")
    try:
        df = pd.read_parquet(frame)
    except Exception:
        df = pd.read_pickle(frame)
    return df, json.loads(meta_path.read_text())


def _lam_mu(split_df, atk, dfd, ha):
    lam = np.array([math.exp(atk.get(r.home_team, 0) + dfd.get(r.away_team, 0) + ha)
                    for _, r in split_df.iterrows()])
    mu = np.array([math.exp(atk.get(r.away_team, 0) + dfd.get(r.home_team, 0))
                   for _, r in split_df.iterrows()])
    return lam, mu


def _fit_hurdle(train, feat, best_p, weight_hl, seed, n_jobs=2):
    """T3a binary P(draw) XGB — mirror of eval_baseline.py:3040-3051."""
    sw = _season_weights(train["season"], train["season"].max(), weight_hl)
    clf = xgb.XGBClassifier(
        objective="binary:logistic", eval_metric="logloss", verbosity=0,
        random_state=seed, subsample=0.8, colsample_bytree=0.8, n_jobs=n_jobs,
        max_depth=best_p["max_depth"], n_estimators=best_p["n_estimators"],
        learning_rate=best_p["learning_rate"])
    clf.fit(train[feat].fillna(0).values,
            (train["label_result"].values == 1).astype(int), sample_weight=sw)
    return clf


def _hur_merge(p3, pdraw):
    """T3a recombination: hurdle owns the draw column, 3-class decides H-vs-A."""
    ha2 = p3[:, [0, 2]]
    ha2 = ha2 / ha2.sum(axis=1, keepdims=True).clip(1e-9, None)
    out = np.empty_like(p3)
    out[:, 0] = (1.0 - pdraw) * ha2[:, 0]
    out[:, 1] = pdraw
    out[:, 2] = (1.0 - pdraw) * ha2[:, 1]
    return out


def _mix_soft(p3, hur3, alpha):
    """C: draw column alpha-mix, H/A scaled to preserve their ratio. alpha=0 -> p3."""
    pd_new = (1.0 - alpha) * p3[:, 1] + alpha * hur3[:, 1]
    scale = (1.0 - pd_new) / np.clip(1.0 - p3[:, 1], 1e-9, None)
    out = np.empty_like(p3)
    out[:, 0] = p3[:, 0] * scale
    out[:, 1] = pd_new
    out[:, 2] = p3[:, 2] * scale
    return out / out.sum(axis=1, keepdims=True).clip(1e-9, None)


def _blend_pc(xg, dc, w_ha, w_d):
    """B: per-class convex blend — draw column gets its own weight."""
    w = np.array([w_ha, w_d, w_ha])
    b = xg * w + dc * (1.0 - w)
    return b / b.sum(axis=1, keepdims=True).clip(1e-9, None)


def _draw_recal(p3_cal, y_cal, p3_te):
    """D: draw-only ratio-preserving binary temperature on the draw logit.

    NOT in the 14-variant sweep (that tested per-class methods on all three
    columns). Fits one scalar T_d on cal binary NLL of the draw column; H/A are
    scaled by (1-p_d')/(1-p_d) so their ratio is untouched.
    """
    eps = 1e-9
    z_cal = np.log(np.clip(p3_cal[:, 1], eps, 1 - eps) /
                   np.clip(1 - p3_cal[:, 1], eps, 1 - eps))
    y_d = (y_cal == 1).astype(float)

    def _nll(T):
        p = 1.0 / (1.0 + np.exp(-z_cal / max(T, 0.1)))
        p = np.clip(p, eps, 1 - eps)
        return float(-np.mean(y_d * np.log(p) + (1 - y_d) * np.log(1 - p)))

    T = minimize_scalar(_nll, bounds=(0.3, 5.0), method="bounded").x
    z_te = np.log(np.clip(p3_te[:, 1], eps, 1 - eps) /
                  np.clip(1 - p3_te[:, 1], eps, 1 - eps))
    pd_new = 1.0 / (1.0 + np.exp(-z_te / T))
    scale = (1.0 - pd_new) / np.clip(1.0 - p3_te[:, 1], eps, None)
    out = np.empty_like(p3_te)
    out[:, 0] = p3_te[:, 0] * scale
    out[:, 1] = pd_new
    out[:, 2] = p3_te[:, 2] * scale
    return out / out.sum(axis=1, keepdims=True).clip(1e-9, None), float(T)


def _murphy(p_d, y_d, width=0.05):
    """Murphy decomposition of the binary draw Brier: BS = UNC - RES + REL."""
    edges = np.arange(0.0, 1.0 + width, width)
    ybar = float(y_d.mean())
    unc = ybar * (1.0 - ybar)
    rel = res = 0.0
    n = len(p_d)
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p_d >= lo) & (p_d < hi)
        if not m.any():
            continue
        pk, yk, nk = float(p_d[m].mean()), float(y_d[m].mean()), int(m.sum())
        rel += nk / n * (pk - yk) ** 2
        res += nk / n * (yk - ybar) ** 2
    return {"brier": brier_binary(p_d, y_d), "unc": round(unc, 6),
            "res": round(res, 6), "rel": round(rel, 6), "base_rate": round(ybar, 4)}


def _reliability(p_d, y_d, min_n=25):
    """Same binning as model_report.py draw_reliability (0.05 bins, min n=25)."""
    curve = []
    for lo in np.arange(0.0, 0.7, 0.05):
        m = (p_d >= lo) & (p_d < lo + 0.05)
        if m.sum() < min_n:
            continue
        curve.append({"bin": f"{lo:.2f}", "n": int(m.sum()),
                      "p_mean": round(float(p_d[m].mean()), 4),
                      "freq": round(float(y_d[m].mean()), 4),
                      "rel_contrib": round(float(m.sum() / len(p_d) *
                                           (p_d[m].mean() - y_d[m].mean()) ** 2), 6)})
    return curve


def _second_pass(cal_blend, y_cal, te_blend):
    return calibrate_temperature(cal_blend, y_cal, te_blend)


def _metrics(p3, y_oh):
    pc = per_class_brier(p3, y_oh)
    return {"brier": round(brier_multiclass_sum(p3, y_oh), 6),
            "brier_home": round(pc[0], 6), "brier_draw": round(pc[1], 6),
            "brier_away": round(pc[2], 6)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frame", default="data/parity_frame.parquet")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-bags", type=int, default=5)
    ap.add_argument("--with-ref-feat", action="store_true",
                    help="also run the D-sim (extra XGB fit per fold with ref_draw_rate)")
    ap.add_argument("--out-dir", default="experiments/draw_probe")
    args = ap.parse_args()

    df, meta = _load_frame(args.frame)
    df["date"] = pd.to_datetime(df["date"])
    feat = [c for c in meta["feat_base"] if c in df.columns]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("# Probe: draw decomposition + offline sims (Phase 0, draw-Brier campaign)")
    print(f"Frame {len(df):,} rows · {len(feat)} features · folds {TEST_SEASONS} · "
          f"seed {args.seed} · bags {args.n_bags} · D-sim {'ON' if args.with_ref_feat else 'off'}\n")

    rows = []          # per-match parquet records
    fold_summ = {}     # per-fold sim + component results
    pooled = {k: [] for k in ("final", "y", "season", "lam_mu", "dc", "xgb", "hur", "pre2")}

    for ts in TEST_SEASONS:
        cal_s = ts - 1
        train = df[df["season"] < cal_s].dropna(subset=["home_goals", "away_goals"])
        cal = df[df["season"] == cal_s].dropna(subset=["home_goals", "away_goals"])
        test = df[df["season"] == ts].dropna(subset=["home_goals", "away_goals"])
        if len(train) < 200 or len(cal) < 50 or len(test) < 50:
            print(f"  {ts}: skipped (insufficient data)")
            continue
        y_cal = cal["label_result"].values.astype(int)
        y_te = test["label_result"].values.astype(int)
        y_cal_oh, y_te_oh = np.eye(3)[y_cal], np.eye(3)[y_te]

        # ── champion pipeline, intermediates kept ────────────────────────────
        atk, dfd, ha, rho = fit_dc(train, decay_hl=meta.get("dc_decay_hl", 120))
        dc_cal_raw = dc_predict_batch(cal, atk, dfd, ha, rho)
        dc_te_raw = dc_predict_batch(test, atk, dfd, ha, rho)
        dc_cal = calibrate_temperature(dc_cal_raw, y_cal, dc_cal_raw)
        dc_te = calibrate_temperature(dc_cal_raw, y_cal, dc_te_raw)
        lam_cal, mu_cal = _lam_mu(cal, atk, dfd, ha)
        lam_te, mu_te = _lam_mu(test, atk, dfd, ha)

        clfs, best_p = fit_xgb(train, feat, weight_hl=meta.get("weight_hl", 6),
                               seed=args.seed, n_bags=args.n_bags)
        xgb_cal_raw = bag_proba(clfs, cal[feat].fillna(0).values)
        xgb_te_raw = bag_proba(clfs, test[feat].fillna(0).values)
        xgb_cal = calibrate_temperature(xgb_cal_raw, y_cal, xgb_cal_raw)
        xgb_te = calibrate_temperature(xgb_cal_raw, y_cal, xgb_te_raw)

        # T3a hurdle on RAW xgb (as in eval_baseline), calibrated after merge
        clf_d = _fit_hurdle(train, feat, best_p, meta.get("weight_hl", 6), args.seed)
        pd_cal = clf_d.predict_proba(cal[feat].fillna(0).values)[:, 1]
        pd_te = clf_d.predict_proba(test[feat].fillna(0).values)[:, 1]
        hur_cal_raw = _hur_merge(xgb_cal_raw, pd_cal)
        hur_te_raw = _hur_merge(xgb_te_raw, pd_te)
        hur_cal = calibrate_temperature(hur_cal_raw, y_cal, hur_cal_raw)
        hur_te = calibrate_temperature(hur_cal_raw, y_cal, hur_te_raw)

        w = fit_capped_blend(xgb_cal, dc_cal, y_cal_oh)
        cal_blend = blend(xgb_cal, dc_cal, w)
        te_blend = blend(xgb_te, dc_te, w)
        ens_te = _second_pass(cal_blend, y_cal, te_blend)

        champ = _metrics(ens_te, y_te_oh)
        f = {"w_xgb": round(w, 3), "champion": champ,
             "components_draw_brier": {
                 "dc": round(per_class_brier(dc_te, y_te_oh)[1], 6),
                 "xgb": round(per_class_brier(xgb_te, y_te_oh)[1], 6),
                 "hurdle": round(per_class_brier(hur_te, y_te_oh)[1], 6),
                 "blend_pre2nd": round(per_class_brier(te_blend, y_te_oh)[1], 6),
                 "final": champ["brier_draw"]}}

        # ── T4 B-sim: per-class blend (w_ha, w_d), grid 0.70..1.00 step 0.025 ─
        grid = np.arange(0.70, 1.0001, 0.025)
        best = {"honest": (None, np.inf), "oracle": (None, np.inf)}
        for w_ha in grid:
            for w_d in grid:
                cb = _blend_pc(xgb_cal, dc_cal, w_ha, w_d)
                tb = _blend_pc(xgb_te, dc_te, w_ha, w_d)
                cal_b = brier_multiclass_sum(cb, y_cal_oh)          # honest criterion
                fin = _second_pass(cb, y_cal, tb)
                te_b = brier_multiclass_sum(fin, y_te_oh)           # oracle criterion
                if cal_b < best["honest"][1]:
                    best["honest"] = ((w_ha, w_d), cal_b, fin)
                if te_b < best["oracle"][1]:
                    best["oracle"] = ((w_ha, w_d), te_b, fin)
        f["B"] = {}
        for mode in ("honest", "oracle"):
            (w_ha, w_d), _, fin = best[mode]
            f["B"][mode] = {"w_ha": round(w_ha, 3), "w_d": round(w_d, 3),
                            **_metrics(fin, y_te_oh)}

        # ── T4 C-sim: soft hurdle alpha grid 0..1 step 0.05 ──────────────────
        c_rows = []
        for alpha in np.arange(0.0, 1.0001, 0.05):
            xc = _mix_soft(xgb_cal, hur_cal, alpha)
            xt = _mix_soft(xgb_te, hur_te, alpha)
            w_c = fit_capped_blend(xc, dc_cal, y_cal_oh)
            cb, tb = blend(xc, dc_cal, w_c), blend(xt, dc_te, w_c)
            fin = _second_pass(cb, y_cal, tb)
            c_rows.append({"alpha": round(alpha, 2), "w": round(w_c, 3),
                           "cal_brier": brier_multiclass_sum(cb, y_cal_oh),
                           **_metrics(fin, y_te_oh)})
        hon = min(c_rows, key=lambda r: r["cal_brier"])
        ora = min(c_rows, key=lambda r: r["brier"])
        f["C"] = {"honest": hon, "oracle": ora}

        # ── T4 D-sim (opt-in): ref_draw_rate feature + draw-only recal ───────
        if args.with_ref_feat and "ref_draw_rate" in df.columns:
            feat_d = feat + ["ref_draw_rate"]
            clfs_r, _ = fit_xgb(train, feat_d, weight_hl=meta.get("weight_hl", 6),
                                seed=args.seed, n_bags=args.n_bags)
            xr_cal_raw = bag_proba(clfs_r, cal[feat_d].fillna(0).values)
            xr_te_raw = bag_proba(clfs_r, test[feat_d].fillna(0).values)
            xr_cal = calibrate_temperature(xr_cal_raw, y_cal, xr_cal_raw)
            xr_te = calibrate_temperature(xr_cal_raw, y_cal, xr_te_raw)
            w_r = fit_capped_blend(xr_cal, dc_cal, y_cal_oh)
            cb_r, tb_r = blend(xr_cal, dc_cal, w_r), blend(xr_te, dc_te, w_r)
            fin_r_cal = _second_pass(cb_r, y_cal, cb_r)
            fin_r = _second_pass(cb_r, y_cal, tb_r)
            rec_r, T_r = _draw_recal(fin_r_cal, y_cal, fin_r)
            fin_c_cal = _second_pass(cal_blend, y_cal, cal_blend)
            rec_c, T_c = _draw_recal(fin_c_cal, y_cal, ens_te)
            f["D"] = {"feat_only": _metrics(fin_r, y_te_oh),
                      "feat_plus_recal": {**_metrics(rec_r, y_te_oh), "T_d": round(T_r, 3)},
                      "recal_only": {**_metrics(rec_c, y_te_oh), "T_d": round(T_c, 3)},
                      "w_xgb": round(w_r, 3)}

        fold_summ[str(ts)] = f
        d = f["components_draw_brier"]
        print(f"  {ts}: champ {champ['brier']:.6f} (draw {champ['brier_draw']:.6f}) "
              f"w={w:.3f} | comp draw dc={d['dc']:.4f} xgb={d['xgb']:.4f} "
              f"hur={d['hurdle']:.4f} pre2={d['blend_pre2nd']:.4f}")
        print(f"        B honest ({f['B']['honest']['w_ha']:.2f},{f['B']['honest']['w_d']:.2f}) "
              f"{f['B']['honest']['brier']:.6f}/d{f['B']['honest']['brier_draw']:.6f} · "
              f"oracle ({f['B']['oracle']['w_ha']:.2f},{f['B']['oracle']['w_d']:.2f}) "
              f"{f['B']['oracle']['brier']:.6f}/d{f['B']['oracle']['brier_draw']:.6f}")
        print(f"        C honest a={hon['alpha']:.2f} {hon['brier']:.6f}/d{hon['brier_draw']:.6f} · "
              f"oracle a={ora['alpha']:.2f} {ora['brier']:.6f}/d{ora['brier_draw']:.6f}")

        # ── persist per-match records ─────────────────────────────────────────
        for part, sub, y_, lam_, mu_, dc_, xg_, hu_, pre2_, fin_ in (
                ("cal", cal, y_cal, lam_cal, mu_cal, dc_cal, xgb_cal, hur_cal,
                 cal_blend, None),
                ("test", test, y_te, lam_te, mu_te, dc_te, xgb_te, hur_te,
                 te_blend, ens_te)):
            rec = pd.DataFrame({
                "fold": ts, "part": part,
                "season": sub["season"].values, "label": y_,
                "lam": lam_, "mu": mu_,
                "dc_h": dc_[:, 0], "dc_d": dc_[:, 1], "dc_a": dc_[:, 2],
                "xgb_h": xg_[:, 0], "xgb_d": xg_[:, 1], "xgb_a": xg_[:, 2],
                "hur_h": hu_[:, 0], "hur_d": hu_[:, 1], "hur_a": hu_[:, 2],
                "pre2_h": pre2_[:, 0], "pre2_d": pre2_[:, 1], "pre2_a": pre2_[:, 2],
            })
            if fin_ is not None:
                rec["fin_h"], rec["fin_d"], rec["fin_a"] = fin_[:, 0], fin_[:, 1], fin_[:, 2]
            if "match_id" in sub.columns:
                rec["match_id"] = sub["match_id"].values
            if "ref_draw_rate" in sub.columns:
                rec["ref_draw_rate"] = sub["ref_draw_rate"].values
            rec["w_xgb"] = round(w, 3)
            rows.append(rec)

        pooled["final"].append(ens_te); pooled["y"].append(y_te)
        pooled["season"].append(test["season"].values)
        pooled["lam_mu"].append(lam_te + mu_te)
        pooled["dc"].append(dc_te); pooled["xgb"].append(xgb_te)
        pooled["hur"].append(hur_te); pooled["pre2"].append(te_blend)

    # ══ pooled analysis over the full test window ══════════════════════════════
    P = np.vstack(pooled["final"]); y = np.concatenate(pooled["y"])
    y_oh = np.eye(3)[y]
    seasons = np.concatenate(pooled["season"])
    lam_mu = np.concatenate(pooled["lam_mu"])
    y_d = (y == 1).astype(float)

    print("\n## Verification vs champion report")
    champ_pool = _metrics(P, y_oh)
    ref = json.loads(Path(CHAMPION_REPORT).read_text())
    print(f"  probe:  n={len(P)} brier={champ_pool['brier']:.6f} "
          f"draw={champ_pool['brier_draw']:.6f}")
    print(f"  report: n={ref['overall']['n']} brier={ref['overall']['brier_sum']:.6f} "
          f"draw={ref['overall']['brier_draw']:.6f}")

    print("\n## T1 Murphy decomposition of draw Brier (BS = UNC - RES + REL)")
    t1 = {"pooled": _murphy(P[:, 1], y_d)}
    m = t1["pooled"]
    print(f"  pooled: BS={m['brier']:.6f} UNC={m['unc']:.6f} RES={m['res']:.6f} "
          f"REL={m['rel']:.6f} (base {m['base_rate']})")
    for s in sorted(set(seasons)):
        mask = seasons == s
        t1[str(int(s))] = _murphy(P[mask, 1], y_d[mask])
        m = t1[str(int(s))]
        print(f"  {int(s)}:   BS={m['brier']:.6f} UNC={m['unc']:.6f} RES={m['res']:.6f} "
              f"REL={m['rel']:.6f}")

    print("\n## T2 draw reliability (pooled; report binning)")
    t2 = {"pooled": _reliability(P[:, 1], y_d)}
    for b in t2["pooled"]:
        print(f"  bin {b['bin']}: n={b['n']:4d} pred={b['p_mean']:.4f} "
              f"obs={b['freq']:.4f} rel_contrib={b['rel_contrib']:.6f}")
    print("  by lambda+mu quintile (pred vs obs draw rate):")
    t2["by_lam_mu"] = []
    q = pd.qcut(lam_mu, 5, labels=False)
    for k in range(5):
        mask = q == k
        row = {"quintile": k + 1,
               "lam_mu_range": f"{lam_mu[mask].min():.2f}-{lam_mu[mask].max():.2f}",
               "n": int(mask.sum()), "pred": round(float(P[mask, 1].mean()), 4),
               "obs": round(float(y_d[mask].mean()), 4),
               "draw_brier": round(brier_binary(P[mask, 1], y_d[mask]), 6)}
        t2["by_lam_mu"].append(row)
        print(f"    Q{k+1} ({row['lam_mu_range']}): n={row['n']} pred={row['pred']:.4f} "
              f"obs={row['obs']:.4f} brier={row['draw_brier']:.6f}")

    print("\n## T3 component draw Brier (pooled)")
    t3 = {name: round(per_class_brier(np.vstack(pooled[key]), y_oh)[1], 6)
          for name, key in (("dc", "dc"), ("xgb", "xgb"), ("hurdle", "hur"),
                            ("blend_pre2nd", "pre2"), ("final", "final"))}
    for k_, v in t3.items():
        print(f"  {k_:14s} {v:.6f}")

    # ── write artifacts ────────────────────────────────────────────────────────
    per_match = pd.concat(rows, ignore_index=True)
    pq = out_dir / f"draw_components_seed{args.seed}.parquet"
    per_match.to_parquet(pq, index=False)
    summary = {"seed": args.seed, "n_bags": args.n_bags, "folds": fold_summ,
               "pooled_champion": champ_pool, "T1_murphy": t1,
               "T2_reliability": t2, "T3_components": t3,
               "verification": {"probe": champ_pool,
                                "report": {k: ref["overall"][k] for k in
                                           ("n", "brier_sum", "brier_draw")}}}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {pq} ({len(per_match):,} rows) and {out_dir/'summary.json'}")

    # ── decision-rule readout (plan P0.4) ──────────────────────────────────────
    print("\n## Decision rules (vs champion, per fold)")
    for cand in ("B", "C"):
        print(f"  {cand}:")
        for mode in ("honest", "oracle"):
            deltas = []
            for ts, f in fold_summ.items():
                ch, v = f["champion"], f[cand][mode]
                deltas.append((ts, v["brier_draw"] - ch["brier_draw"],
                               v["brier"] - ch["brier"]))
            avg_d = np.mean([d[1] for d in deltas])
            avg_n = np.mean([d[2] for d in deltas])
            per = "  ".join(f"{ts}:d{dd:+.4f}/n{dn:+.4f}" for ts, dd, dn in deltas)
            print(f"    {mode:6s} avg draw {avg_d:+.6f} · avg net {avg_n:+.6f} · {per}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
