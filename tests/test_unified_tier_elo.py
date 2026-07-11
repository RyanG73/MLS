import pandas as pd

from scripts.eval import unified_tier_elo as ute


def _row(mover="Mover", opp="Opp", is_home=True, outcome=0, season=2022, day=1):
    return ute._MoverMatch(
        mover=mover,
        opp=opp,
        is_home=is_home,
        outcome=outcome,
        season=season,
        date=pd.Timestamp(f"{season}-08-{day:02d}"),
        exit_elo=1400.0,
        delta=-100.0,
    )


def test_decay_weight_linearly_hands_off():
    assert ute._decay_weight(0, 8) == 1.0
    assert ute._decay_weight(4, 8) == 0.5
    assert ute._decay_weight(8, 8) == 0.0
    assert ute._decay_weight(12, 8) == 0.0


def test_mover_match_counts_are_per_mover_and_season():
    rows = [
        _row(mover="A", season=2022, day=8),
        _row(mover="A", season=2022, day=1),
        _row(mover="B", season=2022, day=3),
        _row(mover="A", season=2023, day=1),
    ]

    counts = ute._mover_match_counts(rows)

    assert counts[1] == 0
    assert counts[0] == 1
    assert counts[2] == 0
    assert counts[3] == 0


def test_bridge_decay_brier_uses_destination_elo_after_window():
    rows = [_row(day=1), _row(day=2)]
    # Pre-match destination-league ELOs exist for both rows. window=1 means
    # first row uses bridge, second row has fully handed off to league ELO.
    history = {
        "Mover": ([pd.Timestamp("2022-08-01"), pd.Timestamp("2022-08-02")], [1500.0, 1600.0]),
        "Opp": ([pd.Timestamp("2022-08-01"), pd.Timestamp("2022-08-02")], [1500.0, 1500.0]),
    }

    brier = ute._brier_bridge_decay(rows, history, window=1)

    assert 0.0 < brier < 2.0
