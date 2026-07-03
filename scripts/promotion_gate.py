#!/usr/bin/env python3
"""
Champion / challenger promotion gate (Phase 4c).

Encodes the codebase-review's circular-review loop as code: a challenger model is
promoted to champion ONLY if it clears every gate criterion. This turns the manual
"KEEP/DROP with a 2024 check" judgement into a reproducible, auditable decision.

Gate criteria (all must hold for PASS):
  GUARDRAILS (must not regress)
    - coverage:        challenger n per season >= champion (data not shrunk)
    - robustness_2024: challenger 2024 Brier <= champion 2024 + tol   [CLAUDE.md hard gate]
    - calibration:     challenger cal_err <= champion cal_err + cal_tol
    - slices:          no season/confidence slice regresses by > slice_tol
  IMPROVEMENT (must gain)
    - core_metric:     challenger avg Brier improved by >= min_gain

Inputs are JSON reports produced by scripts/model_report.py.

Subcommands:
  evaluate   --challenger R [--champion R]   Run the gate; exit 0=PASS, 1=FAIL.
  promote    --challenger R                  Set R as the champion (writes champion.json).
  self-test                                  Assert the gate rejects a worse challenger.

If no champion exists, `evaluate` reports "no champion (bootstrap)" and PASSES so the
first report can be promoted as the initial champion.

Usage:
  python scripts/model_report.py --label champion --out experiments/champion.report.json
  python scripts/promotion_gate.py promote --challenger experiments/champion.report.json
  python scripts/promotion_gate.py evaluate --challenger experiments/cand.report.json
  python scripts/promotion_gate.py self-test
"""

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
CHAMPION_PTR = REPO_ROOT / "experiments" / "champion.json"

# Gate tolerances
MIN_GAIN = 0.0005     # challenger must beat champion avg Brier by at least this
TOL_2024 = 0.0005     # allowed 2024 Brier regression (noise band)
CAL_TOL = 0.005       # allowed calibration-error regression
SLICE_TOL = 0.02      # allowed per-slice Brier regression


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"[gate] report not found: {path}")
    return json.loads(p.read_text())


def _champion_report() -> dict | None:
    if not CHAMPION_PTR.exists():
        return None
    ptr = json.loads(CHAMPION_PTR.read_text())
    rep_path = REPO_ROOT / ptr["report"]
    if not rep_path.exists():
        return None
    return json.loads(rep_path.read_text())


def evaluate_gate(champion: dict | None, challenger: dict) -> tuple[bool, list]:
    """Return (passed, [(criterion, ok, detail), ...])."""
    checks = []

    if champion is None:
        checks.append(("bootstrap", True,
                       "no champion on record — challenger eligible as initial champion"))
        return True, checks

    # ── coverage ─────────────────────────────────────────────────────────────
    cov_ok = True
    cov_detail = []
    for s, n_champ in champion.get("coverage_by_season", {}).items():
        n_chal = challenger.get("coverage_by_season", {}).get(s, 0)
        if n_chal < n_champ:
            cov_ok = False
            cov_detail.append(f"{s}: {n_chal}<{n_champ}")
    checks.append(("coverage", cov_ok,
                   "ok" if cov_ok else "shrunk: " + ", ".join(cov_detail)))

    # ── robustness_2024 (hard gate) ──────────────────────────────────────────
    champ_24 = champion.get("per_season", {}).get("2024")
    chal_24 = challenger.get("per_season", {}).get("2024")
    if champ_24 is None or chal_24 is None:
        checks.append(("robustness_2024", True, "2024 not in both reports — skipped"))
    else:
        ok24 = chal_24 <= champ_24 + TOL_2024
        checks.append(("robustness_2024", ok24,
                       f"challenger {chal_24:.4f} vs champion {champ_24:.4f} "
                       f"(Δ {champ_24 - chal_24:+.4f}, tol {TOL_2024})"))

    # ── calibration ──────────────────────────────────────────────────────────
    champ_cal = champion.get("max_decile_cal_error")
    chal_cal = challenger.get("max_decile_cal_error")
    if champ_cal is not None and chal_cal is not None:
        okcal = chal_cal <= champ_cal + CAL_TOL
        checks.append(("calibration", okcal,
                       f"challenger {chal_cal:.4f} vs champion {champ_cal:.4f} "
                       f"(tol {CAL_TOL})"))

    # ── slices (season + confidence) ─────────────────────────────────────────
    slice_ok = True
    slice_detail = []
    for grp in ("by_season", "by_confidence"):
        c_slices = champion.get("slices", {}).get(grp, {})
        x_slices = challenger.get("slices", {}).get(grp, {})
        for k, cm in c_slices.items():
            xm = x_slices.get(k)
            if not xm or cm.get("n", 0) < 20 or xm.get("n", 0) < 20:
                continue
            reg = xm["brier_sum"] - cm["brier_sum"]
            if reg > SLICE_TOL:
                slice_ok = False
                slice_detail.append(f"{grp}/{k}: +{reg:.4f}")
    checks.append(("slices", slice_ok,
                   "ok" if slice_ok else "regressed: " + ", ".join(slice_detail)))

    # ── data-source health (Phase A → gate; review's "coverage not worse") ────
    # Challenger report may embed a source_health snapshot from
    # data_pipeline.source_health.coverage_gate_status(). If present, every
    # source must be ok=True. Absent/empty (e.g. no DB at report time) → skip.
    sh = challenger.get("source_health")
    if sh:
        bad = [f"{name}({d.get('parsed')}/{d.get('floor')}"
               + (f", err={d.get('error')}" if d.get("error") else "") + ")"
               for name, d in sh.items() if not d.get("ok", True)]
        sh_ok = not bad
        checks.append(("data_source_health", sh_ok,
                       "ok (" + ", ".join(sh) + ")" if sh_ok
                       else "degraded: " + ", ".join(bad)))
    else:
        checks.append(("data_source_health", True,
                       "no source_health snapshot in report — skipped"))

    # ── core metric (improvement) ────────────────────────────────────────────
    champ_b = champion.get("avg_brier")
    chal_b = challenger.get("avg_brier")
    gain = (champ_b - chal_b) if (champ_b is not None and chal_b is not None) else None
    core_ok = gain is not None and gain >= MIN_GAIN
    checks.append(("core_metric", core_ok,
                   f"challenger {chal_b:.4f} vs champion {champ_b:.4f} "
                   f"(gain {gain:+.4f}, need >= {MIN_GAIN})"))

    # ── feature completeness (ADVISORY — reported, never blocks) ────────────
    # A challenger evaluated on mostly-defaulted features can look deceptively
    # good. Flag any key feature with >20% nulls in the test window so the
    # operator can investigate before promoting.
    fc = challenger.get("feature_completeness")
    if fc:
        HIGH_NULL = 0.20
        flagged = [
            f"{feat}@{season}={null_rate:.0%}"
            for season, cols in fc.items()
            for feat, null_rate in cols.items()
            if null_rate > HIGH_NULL
        ]
        checks.append(("feature_completeness", True,
                       ("ok — all key features < 20% null" if not flagged
                        else "advisory — high null: " + ", ".join(flagged[:5])
                             + (" …" if len(flagged) > 5 else ""))))
    else:
        checks.append(("feature_completeness", True,
                       "no feature_completeness in report — skipped (advisory)"))

    # ── paired significance (ADVISORY — reported, never blocks) ──────────────
    # When both reports embed per-match Brier vectors (model_report.py
    # "per_match"), bootstrap the mean paired difference on common match_ids.
    # Measured seed noise is σ≈0.001 on avg Brier (2026-06-09), so unpaired
    # gains near MIN_GAIN are ambiguous; this quantifies the paired evidence.
    pm_c = (champion or {}).get("per_match")
    pm_x = challenger.get("per_match")
    if pm_c and pm_x:
        try:
            import numpy as _np
            cd = dict(zip(pm_c["match_id"], pm_c["brier"]))
            xd = dict(zip(pm_x["match_id"], pm_x["brier"]))
            common = sorted(set(cd) & set(xd))
            if len(common) >= 100:
                diffs = _np.array([cd[m] - xd[m] for m in common])  # >0 ⇒ challenger better
                rng = _np.random.default_rng(42)
                boots = rng.choice(diffs, size=(2000, len(diffs)),
                                   replace=True).mean(axis=1)
                p_better = float((boots > 0).mean())
                checks.append(("paired_significance", True,
                               f"n={len(diffs)} paired · mean Δ={diffs.mean():+.5f} · "
                               f"P(challenger better)={p_better:.3f} — advisory"))
            else:
                checks.append(("paired_significance", True,
                               f"only {len(common)} common matches — skipped"))
        except Exception as e:  # diagnostics must never break the gate
            checks.append(("paired_significance", True, f"error ({e}) — skipped"))
    else:
        checks.append(("paired_significance", True,
                       "per_match vectors absent — skipped (advisory)"))

    passed = all(ok for _, ok, _ in checks)
    return passed, checks


def _print_checks(champion, challenger, passed, checks) -> None:
    print("\n" + "=" * 72)
    print("PROMOTION GATE")
    if champion is not None:
        print(f"  champion:   {champion.get('run_id','?')}  avg_brier={champion.get('avg_brier')}")
    print(f"  challenger: {challenger.get('run_id','?')}  avg_brier={challenger.get('avg_brier')}")
    print("=" * 72)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name:<16} {detail}")
    print("-" * 72)
    print(f"  RESULT: {'PROMOTE ✓' if passed else 'REJECT ✗'}")
    print("=" * 72 + "\n")


def cmd_evaluate(args) -> int:
    challenger = _load(args.challenger)
    champion = _load(args.champion) if args.champion else _champion_report()
    passed, checks = evaluate_gate(champion, challenger)
    _print_checks(champion, challenger, passed, checks)
    return 0 if passed else 1


def cmd_promote(args) -> int:
    challenger = _load(args.challenger)
    champion = _champion_report()
    passed, checks = evaluate_gate(champion, challenger)
    _print_checks(champion, challenger, passed, checks)
    if not passed and not args.force:
        print("[gate] challenger did not pass — not promoting (use --force to override).")
        return 1
    rel = str(Path(args.challenger).resolve().relative_to(REPO_ROOT))
    CHAMPION_PTR.parent.mkdir(parents=True, exist_ok=True)
    CHAMPION_PTR.write_text(json.dumps({
        "report": rel,
        "run_id": challenger.get("run_id"),
        "avg_brier": challenger.get("avg_brier"),
        "promoted_at": challenger.get("timestamp"),
    }, indent=2))
    print(f"[gate] champion set → {rel} (run {challenger.get('run_id')})")
    return 0


def cmd_self_test(args) -> int:
    """Synthesize a deliberately-worse challenger and assert the gate REJECTS it."""
    base = {
        "run_id": "synthetic-champion",
        "avg_brier": 0.6347,
        "max_decile_cal_error": 0.1490,
        "per_season": {"2022": 0.6317, "2023": 0.6369, "2024": 0.6354},
        "coverage_by_season": {"2022": 489, "2023": 521, "2024": 522},
        "slices": {
            "by_season": {
                "2022": {"n": 489, "brier_sum": 0.6317},
                "2023": {"n": 521, "brier_sum": 0.6369},
                "2024": {"n": 522, "brier_sum": 0.6354},
            },
            "by_confidence": {">60%": {"n": 200, "brier_sum": 0.50}},
        },
    }
    failures = []

    # Case 1: identical challenger → should FAIL core_metric (no gain)
    same = copy.deepcopy(base); same["run_id"] = "synthetic-same"
    p, _ = evaluate_gate(base, same)
    if p:
        failures.append("identical challenger was PROMOTED (should fail: no gain)")

    # Case 2: 2024 regression → should FAIL robustness_2024
    worse24 = copy.deepcopy(base); worse24["run_id"] = "synthetic-worse2024"
    worse24["avg_brier"] = 0.6300                       # better average …
    worse24["per_season"]["2024"] = 0.6500             # … but 2024 blows up
    worse24["slices"]["by_season"]["2024"]["brier_sum"] = 0.6500
    p, checks = evaluate_gate(base, worse24)
    if p:
        failures.append("2024-regressing challenger was PROMOTED (should fail robustness_2024)")
    if not any(name == "robustness_2024" and not ok for name, ok, _ in checks):
        failures.append("robustness_2024 check did not fire on a 2024 regression")

    # Case 3: calibration blowup → should FAIL calibration
    worsecal = copy.deepcopy(base); worsecal["run_id"] = "synthetic-worsecal"
    worsecal["avg_brier"] = 0.6300
    worsecal["per_season"]["2024"] = 0.6350
    worsecal["slices"]["by_season"]["2024"]["brier_sum"] = 0.6350
    worsecal["max_decile_cal_error"] = 0.30
    p, _ = evaluate_gate(base, worsecal)
    if p:
        failures.append("calibration-blowup challenger was PROMOTED (should fail calibration)")

    # Case 4: genuine improvement → should PASS
    better = copy.deepcopy(base); better["run_id"] = "synthetic-better"
    better["avg_brier"] = 0.6320
    better["per_season"] = {"2022": 0.6300, "2023": 0.6350, "2024": 0.6310}
    for s, b in better["per_season"].items():
        better["slices"]["by_season"][s]["brier_sum"] = b
    p, checks = evaluate_gate(base, better)
    if not p:
        det = "; ".join(f"{n}:{d}" for n, ok, d in checks if not ok)
        failures.append(f"genuine improvement was REJECTED (should pass) — {det}")

    # Case 5: bootstrap (no champion) → should PASS
    p, _ = evaluate_gate(None, base)
    if not p:
        failures.append("bootstrap (no champion) was REJECTED (should pass)")

    # Case 6: degraded data source → should FAIL data_source_health
    badsrc = copy.deepcopy(base); badsrc["run_id"] = "synthetic-badsrc"
    badsrc["avg_brier"] = 0.6320
    badsrc["per_season"] = {"2022": 0.6300, "2023": 0.6350, "2024": 0.6310}
    for s, b in badsrc["per_season"].items():
        badsrc["slices"]["by_season"][s]["brier_sum"] = b
    badsrc["source_health"] = {  # ASA feed silently shrank below its floor
        "asa": {"parsed": 12, "floor": 200, "ok": False, "success": True, "error": None},
    }
    p, checks = evaluate_gate(base, badsrc)
    if p:
        failures.append("degraded-source challenger was PROMOTED (should fail data_source_health)")
    if not any(name == "data_source_health" and not ok for name, ok, _ in checks):
        failures.append("data_source_health check did not fire on a degraded feed")

    # Case 7: high feature null rate → advisory fires, gate still PASSES
    hitnull = copy.deepcopy(base); hitnull["run_id"] = "synthetic-hitnull"
    hitnull["avg_brier"] = 0.6320
    hitnull["per_season"] = {"2022": 0.6300, "2023": 0.6350, "2024": 0.6310}
    for s, b in hitnull["per_season"].items():
        hitnull["slices"]["by_season"][s]["brier_sum"] = b
    hitnull["feature_completeness"] = {
        "2022": {"xg_rolling_5": 0.45, "elo_pre": 0.0},  # xg_rolling_5 badly null
        "2023": {"xg_rolling_5": 0.30, "elo_pre": 0.0},
    }
    p, checks = evaluate_gate(base, hitnull)
    if not p:
        det = "; ".join(f"{n}:{d}" for n, ok, d in checks if not ok)
        failures.append(f"high-null-feature challenger was REJECTED (advisory should not block) — {det}")
    fc_check = next((d for n, _, d in checks if n == "feature_completeness"), None)
    if fc_check is None or "advisory" not in fc_check:
        failures.append("feature_completeness advisory did not fire for high null rates")

    print("\n=== promotion_gate self-test ===")
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        print(f"\n{len(failures)} self-test failure(s).")
        return 1
    print("  All 7 cases passed: identical→reject, 2024-regress→reject, "
          "cal-blowup→reject, improvement→promote, bootstrap→promote, "
          "degraded-source→reject, high-null→advisory-only.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    pe = sub.add_parser("evaluate", help="Run the gate (challenger vs champion)")
    pe.add_argument("--challenger", required=True)
    pe.add_argument("--champion", default=None,
                    help="Champion report path (default: experiments/champion.json pointer)")

    pp = sub.add_parser("promote", help="Set a challenger as the champion")
    pp.add_argument("--challenger", required=True)
    pp.add_argument("--force", action="store_true", help="Promote even if the gate fails")

    sub.add_parser("self-test", help="Assert the gate rejects a worse challenger")

    args = p.parse_args()
    if args.command == "evaluate":
        return cmd_evaluate(args)
    if args.command == "promote":
        return cmd_promote(args)
    if args.command == "self-test":
        return cmd_self_test(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
