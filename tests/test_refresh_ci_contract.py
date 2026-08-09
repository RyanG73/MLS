"""CI contract for the refresh path — serialization and the bare-Python step.

Spec: docs/superpowers/specs/2026-08-09-platform-reliability-and-api-opportunity-spec.md
§3.3 (R5, serialized league rebuilds) and §3.5 (R6, the `--select` step runs
before `pip install`).

Both of these were previously enforced by discipline. R5's protection was that
the workflow refuses to force a data commit, which loses the second rebuild
instead of queueing it; R6's was a single test on one module, and defect #8
(`source_registry` importing pandas at module scope) walked straight past it
and broke league selection every 15 minutes for a day.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow(name: str) -> dict:
    # PyYAML parses the bare `on:` key as the boolean True (YAML 1.1); harmless
    # here, since nothing below reads it.
    return yaml.safe_load((WORKFLOWS / name).read_text())


# ── §3.3 / R5: league rebuilds are serialized by CI, not by discipline ───────
def test_league_rebuilds_are_serialized():
    wf = _workflow("refresh-leagues.yml")
    conc = wf.get("concurrency")
    assert conc, "refresh-leagues.yml must declare a concurrency group (R5)"
    assert conc.get("group")
    assert conc.get("cancel-in-progress") is False, (
        "a rebuild hours into 70 leagues has already spent the budget and the "
        "wall clock — queue the second run, do not cancel the first")


def test_the_concurrency_group_is_a_constant_not_a_per_run_expression():
    """`github.run_id` in the group would give every run its own group and
    serialize nothing — the failure mode that makes this look configured."""
    group = _workflow("refresh-leagues.yml")["concurrency"]["group"]
    assert "${{" not in group, f"concurrency group must be constant, got {group!r}"


# ── §3.5 / R6: the whole --select import closure runs on bare Python ─────────
# Third-party packages the runner does NOT have when `--select` executes. The
# step runs before actions/setup-python and before `pip install -r
# requirements.txt` (see refresh-fast.yml), on whatever python3 the image ships.
_BLOCKED = ("pandas", "numpy", "requests", "yaml", "xgboost", "sklearn",
            "scipy", "pyarrow", "matplotlib", "bs4", "dotenv", "statsmodels")


def _run_with_blocked_imports(body: str) -> subprocess.CompletedProcess:
    code = textwrap.dedent(f"""
        import builtins, sys
        BLOCKED = {_BLOCKED!r}
        for m in list(sys.modules):
            if m.split(".")[0] in BLOCKED:
                del sys.modules[m]
        real = builtins.__import__
        def guard(name, *a, **k):
            top = name.split(".")[0]
            if top in BLOCKED:
                raise ModuleNotFoundError("No module named " + repr(top))
            return real(name, *a, **k)
        builtins.__import__ = guard
    """) + textwrap.dedent(body)
    return subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, cwd=ROOT)


def test_select_step_runs_on_bare_python_end_to_end():
    """Not "the module imports" — the actual CLI the workflow runs, producing
    the actual JSON the workflow reads. An import test one level away from the
    entrypoint is what defect #8 slipped through."""
    r = _run_with_blocked_imports("""
        import json, runpy, sys
        sys.argv = ["fast_refresh.py", "--select"]
        try:
            runpy.run_path("scripts/fast_refresh.py", run_name="__main__")
        except SystemExit as e:
            assert not e.code, e.code
    """)
    assert r.returncode == 0, (
        "scripts/fast_refresh.py --select must run on the runner's bare "
        f"Python, before pip install.\n{r.stderr}")
    import json
    leagues = json.loads(r.stdout.strip().splitlines()[-1])
    assert isinstance(leagues, list)


@pytest.mark.parametrize("module", [
    "scripts.fast_refresh",
    "scripts.payload_utils",
    "data_pipeline.source_registry",
])
def test_select_import_closure_members_import_without_third_party(module):
    """Each module the --select path pulls in, named individually, so a failure
    says WHICH import closure member regressed rather than just that the step
    broke."""
    r = _run_with_blocked_imports(f"""
        import importlib
        importlib.import_module({module!r})
        print("ok")
    """)
    assert r.returncode == 0 and "ok" in r.stdout, (
        f"{module} must import without {', '.join(_BLOCKED)}.\n{r.stderr}")


def test_the_guard_itself_can_fail():
    """A blocked-import test that cannot fail proves nothing. This asserts the
    harness really does hide pandas."""
    r = _run_with_blocked_imports("""
        import pandas
    """)
    assert r.returncode != 0 and "No module named 'pandas'" in r.stderr


# ── the dark-feed counter must survive the run that failed ───────────────────
# consecutive_dark_runs lives in a COMMITTED json summary, because a runner is
# fresh every time. `--write` runs on always(), but the payload commit step
# deliberately does not — a build failure must not ship half-built payloads.
# Without a separate always() commit the summary is written and discarded, and
# the counter resets on exactly the runs a dark feed causes, so the
# three-consecutive escalation can never reach its threshold.

@pytest.mark.parametrize("workflow", ["refresh-leagues.yml", "refresh-daily.yml"])
def test_health_surface_is_persisted_even_when_the_build_fails(workflow):
    spec = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text())
    steps = [s for j in spec["jobs"].values() for s in j.get("steps", [])]
    persist = [s for s in steps
               if "source-health surface" in (s.get("name") or "")
               and "git commit" in (s.get("run") or "")]
    assert persist, f"{workflow}: no always() step commits the health surface"
    step = persist[0]
    assert str(step.get("if", "")).strip() == "always()", (
        f"{workflow}: the persistence step must run on always(), got "
        f"{step.get('if')!r} — otherwise it is skipped by the very failure it "
        "exists to record")
    run = step["run"]
    assert "data/source_health_summary.json" in run
    for payload_path in ("webapp/data/", "data/odds_history.parquet",
                         "data/match_prob_history.parquet"):
        assert payload_path not in run, (
            f"{workflow}: the persistence step stages {payload_path} — it must "
            "commit the health surface ALONE, or a failed build ships a "
            "half-built payload through the back door")


@pytest.mark.parametrize("workflow", ["refresh-leagues.yml", "refresh-daily.yml"])
def test_health_persistence_warns_rather_than_fails(workflow):
    """The run may already be failing for a real reason. A push error here must
    not become the error a human sees first."""
    spec = yaml.safe_load((ROOT / ".github/workflows" / workflow).read_text())
    steps = [s for j in spec["jobs"].values() for s in j.get("steps", [])]
    run = next(s["run"] for s in steps
               if "source-health surface" in (s.get("name") or "")
               and "git commit" in (s.get("run") or ""))
    assert "::warning::" in run
    assert "::error::" not in run
    assert "exit 1" not in run
