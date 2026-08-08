"""Stage-2 comparison helpers — frame joining and standings. No network.

Spec: docs/superpowers/specs/2026-08-08-api-football-migration-execution-spec.md §7 Stage 2.
"""
from __future__ import annotations

import pandas as pd


def _frame(rows):
    cols = ["season", "home_team", "away_team", "home_goals", "away_goals", "is_result"]
    return pd.DataFrame(rows, columns=cols)


def test_standings_points_from_frame():
    from scripts.api_football_stage2_validate import standings
    f = _frame([
        (2024, "A", "B", 2, 0, True),   # A win
        (2024, "B", "A", 1, 1, True),   # draw
        (2024, "A", "C", 0, 1, True),   # C win
        (2024, "A", "D", 1, 0, False),  # unplayed — ignored
    ])
    pts = standings(f, 2024)
    assert pts == {"A": 4, "B": 1, "C": 3}


def test_join_on_season_home_away_compares_scorelines():
    """A double round-robin has each ordered (home, away) pair once per season,
    so the join key is unique; dates differ across sources (timezone) and must
    not be part of the key."""
    from scripts.api_football_stage2_validate import join_and_diff
    ours = _frame([(2024, "Flamengo", "Santos", 2, 1, True),
                   (2024, "Santos", "Flamengo", 0, 0, True)])
    spine = _frame([(2024, "Flamengo", "Santos", 2, 1, True),
                    (2024, "Santos", "Flamengo", 1, 0, True)])   # disagreement
    result = join_and_diff(ours, spine)
    assert result["matched"] == 2
    assert result["score_agree"] == 1
    assert result["disagreements"][0]["home_team"] == "Santos"


def test_join_reports_unmatched_fixtures_per_side():
    from scripts.api_football_stage2_validate import join_and_diff
    ours = _frame([(2024, "Flamengo", "Santos", 2, 1, True),
                   (2024, "Gremio", "Bahia", 1, 0, True)])
    spine = _frame([(2024, "Flamengo", "Santos", 2, 1, True),
                    (2024, "Cuiaba", "Goias", 0, 0, True)])
    result = join_and_diff(ours, spine)
    assert result["matched"] == 1
    assert result["only_ours"] == [("Gremio", "Bahia")]
    assert result["only_spine"] == [("Cuiaba", "Goias")]


def test_name_normalization_bridges_source_spellings():
    """Sources spell clubs differently (accents, suffixes); the join must
    survive the common cases via the normalizer + explicit rename map."""
    from scripts.api_football_stage2_validate import join_and_diff
    ours = _frame([(2024, "Atletico-MG", "Sao Paulo", 1, 1, True)])
    spine = _frame([(2024, "Atletico Mineiro", "São Paulo", 1, 1, True)])
    result = join_and_diff(
        ours, spine, spine_rename={"Atletico Mineiro": "Atletico-MG"})
    assert result["matched"] == 1 and result["score_agree"] == 1
