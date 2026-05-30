#!/usr/bin/env python3
"""
scripts/experiment.py — multi-agent experiment runner and comparator.

Three sub-commands:
  baseline   Record the unmodified harness result as the reference point.
  run        Run an instrumented eval with custom flags and register the result.
  compare    Rank all recorded experiments against a baseline.

Usage examples:
  # Record baseline on the current branch
  python scripts/experiment.py baseline

  # Run an agent's candidate feature group
  python scripts/experiment.py run --name feat-tz-shift --cache \
      -- --ab-only "Base,+TZShift"

  # Run the calibration agent's Platt experiment
  python scripts/experiment.py run --name cal-platt --cache \
      -- --calibration platt --ab-only "Base"

  # Run the hyperparameter agent
  python scripts/experiment.py run --name hyp-k30-ha80 --cache \
      -- --elo-k 30 --elo-home-adv 80 --ab-only "Base"

  # Compare all experiments vs the latest baseline
  python scripts/experiment.py compare
  python scripts/experiment.py compare --baseline <SHA>
"""

import argparse
import datetime
import json
import math
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
EXPERIMENTS_DIR = REPO_ROOT / "experiments"
REGISTRY_FILE = EXPERIMENTS_DIR / "registry.jsonl"
EVAL_SCRIPT = REPO_ROOT / "scripts" / "eval_baseline.py"


# ─── helpers ──────────────────────────────────────────────────────────────────

def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _git_branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _git_diff_stat() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "diff", "--stat", "HEAD"],
            text=True,
        ).strip() or "(no local changes)"
    except Exception:
        return "unknown"


def _load_registry() -> list[dict]:
    if not REGISTRY_FILE.exists():
        return []
    records = []
    with open(REGISTRY_FILE) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def _append_registry(record: dict) -> None:
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def _fmt(v, fmt=".4f") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "    —   "
    return f"{v:{fmt}}"


# ─── sub-commands ─────────────────────────────────────────────────────────────

def cmd_baseline(args: argparse.Namespace) -> int:
    """Run eval_baseline.py with no flags and record as the reference point."""
    print("Recording baseline (unmodified harness, no CLI flags)...")
    sha = _git_sha()
    branch = _git_branch()
    exp_id = f"baseline-{sha[:8]}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    out_path = EXPERIMENTS_DIR / f"{exp_id}.json"
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, str(EVAL_SCRIPT), "--out", str(out_path)]
    if args.cache:
        cmd.append("--cache")

    print(f"  → {' '.join(cmd)}")
    ret = subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode
    if ret != 0:
        print(f"[baseline] eval_baseline.py exited with code {ret}", file=sys.stderr)
        return ret

    if not out_path.exists():
        print("[baseline] No JSON output produced — check eval_baseline.py --out flag", file=sys.stderr)
        return 1

    with open(out_path) as fh:
        result = json.load(fh)

    record = {
        "experiment_id": exp_id,
        "role": "baseline",
        "git_sha": sha,
        "git_branch": branch,
        "git_diff_stat": _git_diff_stat(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "name": args.name or "baseline",
        "notes": args.notes or "",
        "eval_flags": [],
        "result_file": str(out_path.relative_to(REPO_ROOT)),
        "naive_brier": result.get("naive_brier"),
        "best_brier": result.get("best_brier"),
        "best_model": result.get("best_model"),
        "improvement_pct": result.get("improvement_pct_vs_naive"),
        "max_cal_error": result.get("max_decile_calibration_error"),
        "config": result.get("config", {}),
        "ab_sets": result.get("ab_sets", {}),
        "per_season": result.get("per_season", {}),
    }
    _append_registry(record)
    print(f"\nBaseline recorded → experiments/{out_path.name}")
    print(f"  naive_brier={_fmt(result.get('naive_brier'))}  "
          f"best_brier={_fmt(result.get('best_brier'))}  "
          f"cal_err={_fmt(result.get('max_decile_calibration_error'))}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run eval_baseline.py with the given flags and register the result."""
    sha = _git_sha()
    branch = _git_branch()
    name = args.name or f"exp-{sha[:8]}"
    exp_id = f"{name}-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    out_path = EXPERIMENTS_DIR / f"{exp_id}.json"
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # eval_flags = everything after the -- separator
    eval_flags = args.eval_flags or []

    cmd = [sys.executable, str(EVAL_SCRIPT), "--out", str(out_path)] + eval_flags
    print(f"Running experiment '{name}'")
    print(f"  git: {branch} @ {sha[:8]}")
    print(f"  cmd: {' '.join(cmd)}")

    ret = subprocess.run(cmd, cwd=str(REPO_ROOT)).returncode
    if ret != 0:
        print(f"[run] eval_baseline.py exited with code {ret}", file=sys.stderr)
        return ret

    if not out_path.exists():
        print("[run] No JSON output produced — ensure --out is passed", file=sys.stderr)
        return 1

    with open(out_path) as fh:
        result = json.load(fh)

    record = {
        "experiment_id": exp_id,
        "role": "experiment",
        "git_sha": sha,
        "git_branch": branch,
        "git_diff_stat": _git_diff_stat(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "name": name,
        "notes": args.notes or "",
        "eval_flags": eval_flags,
        "result_file": str(out_path.relative_to(REPO_ROOT)),
        "naive_brier": result.get("naive_brier"),
        "best_brier": result.get("best_brier"),
        "best_model": result.get("best_model"),
        "improvement_pct": result.get("improvement_pct_vs_naive"),
        "max_cal_error": result.get("max_decile_calibration_error"),
        "config": result.get("config", {}),
        "ab_sets": result.get("ab_sets", {}),
        "per_season": result.get("per_season", {}),
    }
    _append_registry(record)

    print(f"\nExperiment registered → experiments/{out_path.name}")
    print(f"  naive_brier={_fmt(result.get('naive_brier'))}  "
          f"best_brier={_fmt(result.get('best_brier'))}  "
          f"cal_err={_fmt(result.get('max_decile_calibration_error'))}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Print a ranked comparison table of all registered experiments."""
    records = _load_registry()
    if not records:
        print("No experiments in registry yet. Run `experiment.py baseline` first.")
        return 0

    # Find the baseline to compare against
    baseline_record = None
    if args.baseline:
        # match on SHA prefix or experiment_id prefix
        for r in reversed(records):
            if (r.get("git_sha", "").startswith(args.baseline)
                    or r.get("experiment_id", "").startswith(args.baseline)
                    or r.get("name", "") == args.baseline):
                baseline_record = r
                break
        if not baseline_record:
            print(f"[compare] Baseline SHA/id '{args.baseline}' not found in registry.",
                  file=sys.stderr)
            return 1
    else:
        # Latest baseline role entry
        for r in reversed(records):
            if r.get("role") == "baseline":
                baseline_record = r
                break
        if not baseline_record:
            # Fall back to earliest record
            baseline_record = records[0]
            print("[compare] No 'baseline' role found; using first registry entry as reference.")

    b_brier = baseline_record.get("best_brier")
    b_cal = baseline_record.get("max_cal_error")

    # Sort experiments by best_brier (ascending = better)
    sortable = [r for r in records if r.get("best_brier") is not None]
    sortable.sort(key=lambda r: r.get("best_brier", 9.0))

    print("\n" + "=" * 90)
    print("EXPERIMENT COMPARISON")
    print(f"  Baseline: {baseline_record['name']} @ {baseline_record.get('git_sha','?')[:8]}"
          f"  best_brier={_fmt(b_brier)}  cal_err={_fmt(b_cal)}")
    print("=" * 90)
    print(f"  {'Name':<36} {'Best Brier':>10}  {'Δ vs Base':>10}  {'Cal Err':>9}  "
          f"{'Verdict':>8}  {'Branch'}")
    print("  " + "-" * 84)

    winner_id = None
    winner_delta = 0.0

    for r in sortable:
        name = r.get("name", r.get("experiment_id", "?"))[:36]
        bb = r.get("best_brier")
        ce = r.get("max_cal_error")
        branch = r.get("git_branch", "?")[:20]

        if bb is None:
            continue

        delta = (b_brier - bb) if b_brier is not None else float("nan")
        if math.isnan(delta):
            verdict = "?"
        elif delta > 0.001:
            verdict = "KEEP ✓"
        elif delta > 0:
            verdict = "~marginal"
        elif r.get("experiment_id") == baseline_record.get("experiment_id"):
            verdict = "(baseline)"
        else:
            verdict = "DROP"

        marker = " ◀" if (delta > 0.001 and delta > winner_delta) else "  "
        if delta > winner_delta and delta > 0.001:
            winner_delta = delta
            winner_id = r.get("experiment_id")

        print(f"  {name:<36} {_fmt(bb):>10}  {delta:>+10.4f}  "
              f"{_fmt(ce):>9}  {verdict:>9}{marker}  {branch}")

    print()
    if winner_id:
        print(f"  Winner: {winner_id}")
        print(f"  Δ vs baseline: {winner_delta:+.4f}")
    else:
        print("  No experiment beats the baseline by >0.001 Brier yet.")
    print()
    return 0


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description="MLS experiment runner — records, runs, and compares eval experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    # baseline
    p_base = sub.add_parser("baseline", help="Run unmodified harness and record as reference")
    p_base.add_argument("--name",  type=str, default="baseline", help="Human-readable label")
    p_base.add_argument("--notes", type=str, default="",         help="Free-text notes")
    p_base.add_argument("--cache", action="store_true",          help="Enable ASA response cache")

    # run — only --name/--notes are owned here; ALL other flags are forwarded
    # to eval_baseline.py (e.g. --cache, --calibration, --ab-only, --regress).
    # The optional `--` separator is supported but no longer required.
    p_run = sub.add_parser(
        "run",
        help="Run eval_baseline.py with custom flags",
        epilog="Any flag not listed here (e.g. --cache, --calibration, --ab-only) "
               "is forwarded to eval_baseline.py. The '--' separator is optional.",
    )
    p_run.add_argument("--name",   type=str, required=True, help="Human-readable label for this run")
    p_run.add_argument("--notes",  type=str, default="",    help="Free-text notes (e.g. component, hypothesis)")

    # compare
    p_cmp = sub.add_parser("compare", help="Rank registered experiments vs a baseline")
    p_cmp.add_argument("--baseline", type=str, default=None,
                       help="SHA/experiment_id/name of the reference (default: latest baseline role)")

    # parse_known_args: anything experiment.py doesn't recognise is forwarded to
    # the harness, regardless of whether it appears before or after a '--'.
    args, unknown = p.parse_known_args()
    forwarded = [a for a in unknown if a != "--"]  # drop the optional separator

    if args.command == "run":
        args.eval_flags = forwarded
    elif forwarded:
        # baseline/compare don't forward flags — surface typos rather than silently drop
        print(f"[warn] ignoring unrecognized args for '{args.command}': {forwarded}",
              file=sys.stderr)

    if args.command == "baseline":
        return cmd_baseline(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "compare":
        return cmd_compare(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
