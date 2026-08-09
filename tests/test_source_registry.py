"""Source registry — per-family ordered sources with recorded fallback. No network.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md §6.1/§6.2.
"""
from __future__ import annotations

import pandas as pd
import pytest


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"match_id": ["m1"], "home_team": ["A"], "away_team": ["B"]})


@pytest.fixture
def isolated_health(tmp_path, monkeypatch):
    from data_pipeline import source_health
    p = tmp_path / "source_health.parquet"
    monkeypatch.setattr(source_health, "_HEALTH_PATH", p)
    return p


# ── ordering: no registry entry means today's source string, unchanged ───────
def test_default_is_primary_source_only():
    from data_pipeline import source_registry
    assert source_registry.sources_for("epl", "fixtures", default="understat") \
        == ["understat"]


def test_registry_entry_overrides_order(monkeypatch):
    from data_pipeline import source_registry
    monkeypatch.setitem(source_registry.REGISTRY, "epl",
                        {"fixtures": ["api_football", "espn"]})
    assert source_registry.sources_for("epl", "fixtures", default="understat") \
        == ["api_football", "espn"]
    # A family the entry doesn't name still falls back to the default.
    assert source_registry.sources_for("epl", "xg", default="understat") \
        == ["understat"]


# ── resolution: ordered attempts, recorded failures, loud total failure ──────
def test_resolve_returns_primary_when_it_answers(isolated_health):
    from data_pipeline import source_registry
    df, src = source_registry.resolve(
        "epl", "fixtures", loaders={"understat": _frame}, default="understat")
    assert src == "understat" and len(df) == 1


def test_resolve_falls_through_on_exception(monkeypatch, isolated_health):
    from data_pipeline import source_registry
    monkeypatch.setitem(source_registry.REGISTRY, "epl",
                        {"fixtures": ["api_football", "espn"]})

    def broken():
        raise RuntimeError("403")

    df, src = source_registry.resolve(
        "epl", "fixtures",
        loaders={"api_football": broken, "espn": _frame}, default="understat")
    assert src == "espn" and len(df) == 1


def test_resolve_falls_through_on_empty_frame(monkeypatch, isolated_health):
    from data_pipeline import source_registry
    monkeypatch.setitem(source_registry.REGISTRY, "epl",
                        {"fixtures": ["api_football", "espn"]})
    df, src = source_registry.resolve(
        "epl", "fixtures",
        loaders={"api_football": pd.DataFrame, "espn": _frame},
        default="understat")
    assert src == "espn"


def test_resolve_all_fail_raises_with_every_source_named(monkeypatch, isolated_health):
    from data_pipeline import source_registry
    monkeypatch.setitem(source_registry.REGISTRY, "epl",
                        {"fixtures": ["api_football", "espn"]})

    def broken():
        raise RuntimeError("dark")

    with pytest.raises(RuntimeError, match="api_football.*espn"):
        source_registry.resolve(
            "epl", "fixtures",
            loaders={"api_football": broken, "espn": broken},
            default="understat")


def test_resolve_missing_loader_is_a_recorded_failure(monkeypatch, isolated_health):
    from data_pipeline import source_registry
    monkeypatch.setitem(source_registry.REGISTRY, "epl",
                        {"fixtures": ["nonexistent", "espn"]})
    df, src = source_registry.resolve(
        "epl", "fixtures", loaders={"espn": _frame}, default="understat")
    assert src == "espn"


def test_resolve_records_the_failed_source_in_health(monkeypatch, isolated_health):
    """A silent fallback is indistinguishable from a healthy build — the
    failed attempt must leave a source_health row (spec §6.2)."""
    from data_pipeline import source_registry
    monkeypatch.setitem(source_registry.REGISTRY, "epl",
                        {"fixtures": ["api_football", "espn"]})

    def broken():
        raise RuntimeError("403 dark")

    source_registry.resolve(
        "epl", "fixtures",
        loaders={"api_football": broken, "espn": _frame}, default="understat")
    health = pd.read_parquet(isolated_health)
    failed = health[~health["success"]]
    assert len(failed) == 1
    assert failed.iloc[0]["source_name"] == "api_football"
    assert "epl" in failed.iloc[0]["endpoint"]


def test_module_imports_without_pandas(monkeypatch):
    """fast_refresh's --select step runs on the runner's BARE Python, before
    pip install (see refresh-fast.yml and the import comments in
    scripts/fast_refresh.py). select_leagues calls uses_spine, which reaches
    this module — so a module-scope pandas import here breaks league selection
    in CI with ModuleNotFoundError. It did, every 15 minutes, on 2026-08-08."""
    import subprocess, sys, textwrap
    code = textwrap.dedent("""
        import sys
        for m in list(sys.modules):
            if m == "pandas" or m.startswith("pandas."):
                del sys.modules[m]
        import builtins
        real = builtins.__import__
        def guard(name, *a, **k):
            if name == "pandas" or name.startswith("pandas."):
                raise ModuleNotFoundError("No module named 'pandas'")
            return real(name, *a, **k)
        builtins.__import__ = guard
        from data_pipeline.source_registry import sources_for
        assert sources_for("epl", "fixtures", default="espn") == ["espn"]
        print("ok")
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, (
        f"source_registry must import without pandas.\n{r.stderr}")
