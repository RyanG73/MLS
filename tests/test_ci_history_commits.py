"""F-1/F-2/F-4: the accrual parquets must be allowlisted past .gitignore and
actually staged in both refresh workflows' commit step, or CI silently
discards the history every run (this happened to match_prob_history.parquet
for weeks before it was noticed — see docs/product-roadmap-2026-07.md §2)."""
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _is_gitignored(rel_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", rel_path], cwd=REPO_ROOT,
    )
    return result.returncode == 0


def _commit_step_text(workflow_name: str) -> str:
    text = (REPO_ROOT / ".github" / "workflows" / workflow_name).read_text()
    return text.split("Commit and push if changed")[1]


def test_match_prob_history_not_gitignored():
    assert not _is_gitignored("data/match_prob_history.parquet")


def test_daily_refresh_commits_match_prob_history():
    assert "data/match_prob_history.parquet" in _commit_step_text("refresh-daily.yml")


def test_league_refresh_commits_match_prob_history():
    assert "data/match_prob_history.parquet" in _commit_step_text("refresh-leagues.yml")
