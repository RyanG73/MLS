#!/usr/bin/env python3
"""Documentation contract checks.

Makes the rules in CLAUDE.md ("Fact rules") and docs/PLAN.md (the filing rule) executable
instead of aspirational. Four assertions:

  1. filed     — every doc under docs/ is named in docs/PLAN.md
  2. dangling  — every docs/*.md reference in any doc resolves to a real file
  3. branch    — no doc gives an instruction naming the retired dev branch
  4. figures   — every figure in docs/figures.json still matches what the payloads measure,
                 and no doc restates a known-stale value

Run directly (`python3 scripts/check_docs.py`) or via `make test`. Exit 0 = clean.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
PLAN = DOCS / "PLAN.md"
FIGURES = DOCS / "figures.json"

# Files that carry doc references and must resolve. Worktrees are excluded everywhere.
SCAN_ROOTS = ["docs", "CLAUDE.md", "README.md", ".claude"]
EXCLUDE_PARTS = {"worktrees", "node_modules", ".git", "venv", "__pycache__"}

RETIRED_BRANCH = "claude/mls-prediction-dashboard-C2mQM"

# Naming the retired branch is fine in prose, inventories, and history notes. What must never
# appear is an *instruction* that would put an agent on it. Match the instruction shapes
# directly rather than trying to allowlist every way prose can say "this is history" — the
# allowlist approach produced false positives on "retains it for history" and on notes that
# wrapped further than a fixed window.
BRANCH_INSTRUCTION_RE = re.compile(
    r"""(
        worktree \s+ add [^\n]*                # git worktree add ... <branch>
      | git \s+ checkout \s+                   # git checkout <branch>
      | git \s+ switch \s+
      | branch \s* : \s* `?                    # "Branch: <branch>"
      | (?:work|working|all\s+work) \s+ on \s+ `?   # "work on <branch>"
      | must \s+ be \s+ on \s+ `?
      | never \s+ (?:work|push) \s+ on \s+ main
    )""",
    re.X | re.I,
)


def _iter_files() -> list[Path]:
    out: list[Path] = []
    for root in SCAN_ROOTS:
        p = ROOT / root
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for f in p.rglob("*.md"):
                if EXCLUDE_PARTS & set(f.parts):
                    continue
                out.append(f)
    return sorted(out)


def _rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


# ---------------------------------------------------------------- 1. filed


def check_filed() -> list[str]:
    if not PLAN.exists():
        return [f"{_rel(PLAN)} is missing — the filing rule has no authority"]
    plan = PLAN.read_text()
    problems = []
    for f in sorted(DOCS.rglob("*.md")):
        if EXCLUDE_PARTS & set(f.parts) or f == PLAN:
            continue
        if f.name not in plan:
            problems.append(f"unfiled in PLAN.md: {_rel(f)}")
    return problems


# ------------------------------------------------------------- 2. dangling

REF_RE = re.compile(r"docs/[A-Za-z0-9._/-]+\.(?:md|json)")


def check_dangling() -> list[str]:
    problems = []
    seen: dict[str, str] = {}
    for f in _iter_files():
        for m in REF_RE.finditer(f.read_text()):
            ref = m.group(0).rstrip(".")
            if not (ROOT / ref).exists():
                seen.setdefault(ref, _rel(f))
    for ref, where in sorted(seen.items()):
        problems.append(f"dangling reference: {ref}  (first seen in {where})")
    return problems


# --------------------------------------------------------------- 3. branch


def check_branch() -> list[str]:
    """Flag the retired branch only where it reads as an instruction.

    Mentioning it in prose, a branch inventory, or a history note is correct and expected.
    What breaks a campaign is an instruction that puts an agent on it.
    """
    problems = []
    for f in _iter_files():
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if RETIRED_BRANCH not in line:
                continue
            # "never base a worktree on it" is a warning, not an instruction to use it.
            if re.search(r"never\s+base", line, re.I):
                continue
            if BRANCH_INSTRUCTION_RE.search(line):
                problems.append(
                    f"{_rel(f)}:{i} instructs work on the retired dev branch — "
                    f"agents would build worktrees from it"
                )
    return problems


# -------------------------------------------------------------- 4. figures


def _load_payload(path: Path):
    txt = path.read_text()
    m = re.search(r"=\s*(\{.*\})\s*;?\s*$", txt, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


_CROSS_SURFACE_SKIP = {
    "power.js", "logos.js", "movers.js", "drift.js", "coefficients.js", "leagues.js",
}


def power():
    return _load_payload(ROOT / "webapp/data/power.js")


def payload_rows():
    for f in sorted((ROOT / "webapp/data").glob("*.js")):
        if f.name in _CROSS_SURFACE_SKIP:
            continue
        d = _load_payload(f)
        if not d:
            continue
        rows = d.get("standings") or d.get("teams") or []
        if not isinstance(rows, list):
            continue
        for r in rows:
            if isinstance(r, dict):
                yield f.stem, r


def champion():
    return json.loads((ROOT / "experiments/champion.json").read_text())


def check_figures() -> list[str]:
    if not FIGURES.exists():
        return [f"{_rel(FIGURES)} is missing"]
    spec = json.loads(FIGURES.read_text())
    problems = []
    env = {"power": power, "payload_rows": payload_rows, "champion": champion}

    for name, fig in spec.get("figures", {}).items():
        expr = fig.get("measure")
        if not expr:
            continue
        try:
            actual = eval(expr, {"__builtins__": {"sum": sum, "len": len, "set": set,
                                                  "round": round, "min": min, "max": max}}, env)
        except Exception as exc:  # measurement itself broke
            problems.append(f"figure '{name}': measurement failed — {exc}")
            continue
        if actual != fig["value"]:
            problems.append(
                f"figure '{name}': docs/figures.json says {fig['value']}, "
                f"payloads measure {actual} — update the manifest and every surface in "
                f"{fig.get('surfaces', [])}"
            )

    # Known-stale values must not reappear anywhere.
    for name, fig in spec.get("figures", {}).items():
        for stale in fig.get("stale", []):
            hits = _grep_stale(stale)
            for hit in hits:
                problems.append(f"figure '{name}': stale value {stale!r} still present at {hit}")
    return problems


def _grep_stale(value: str) -> list[str]:
    """Find a stale figure value, ignoring lines that explicitly call it stale."""
    try:
        out = subprocess.run(
            ["rg", "-n", "--glob", "!**/worktrees/**", "--glob", "!**/figures.json",
             rf"\b{re.escape(value)}\b", "docs", "CLAUDE.md", "README.md", ".claude"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    hits = []
    for line in out.splitlines():
        low = line.lower()
        if "stale" in low or "previous" in low or "was " in low:
            continue  # a line documenting the correction is allowed to name the old value
        hits.append(line.split(":", 2)[0] + ":" + line.split(":", 2)[1])
    return hits


# ------------------------------------------------------------------- main

PLAN_MAX_LINES = 100


def check_plan_length() -> list[str]:
    """PLAN.md states its own 100-line budget. Nothing enforced it, so it drifted to 121."""
    if not PLAN.exists():
        return []
    n = len(PLAN.read_text().splitlines())
    if n > PLAN_MAX_LINES:
        return [
            f"{_rel(PLAN)} is {n} lines, over its stated {PLAN_MAX_LINES}-line budget — "
            f"it is navigation, so trim it rather than raising the limit"
        ]
    return []


CHECKS = [
    ("filed    ", check_filed),
    ("dangling ", check_dangling),
    ("branch   ", check_branch),
    ("figures  ", check_figures),
    ("plan-len ", check_plan_length),
]


def main() -> int:
    total = 0
    for label, fn in CHECKS:
        problems = fn()
        total += len(problems)
        status = "ok" if not problems else f"{len(problems)} problem(s)"
        print(f"[{label}] {status}")
        for p in problems:
            print(f"    - {p}")
    print()
    if total:
        print(f"check_docs: FAIL — {total} problem(s)")
        return 1
    print("check_docs: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
