"""Tests for the Transfermarkt squad-value scrape.

The bug these guard against (found 2026-07-26): the parser was one regex over
raw HTML, `title="([^"]+)".*?€([\\d.]+)(bn|m)`, with a `v > 20` floor meant to
skip player-value cells. A club row carries `title="<club>"` three times (crest
cell, name cell, squad-size link) before its money cells, and the money cells
are ordered [ø market value, total market value] — so the non-greedy `.*?`
resolved to the ø column. For an elite squad that per-player average clears the
€20m floor, so the guard passed it through and Bayern Munich 2019 was stored as
€20.46m instead of €777.33m.

13.5% of big-5 rows were wrong and they were the richest clubs — Man City
€44.79m (really €1.5bn), Real Madrid €44.74m (€1.43bn), PSG €37.29m (€1.37bn).
That is the exact population a squad-value prior exists to inform.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.eval.tm_value_backfill import (
    MIN_TOP_CLUB_EUR_M, _money_to_m, parse_league_season, validate,
)

# Trimmed from the real Bundesliga 2019 season page. Preserves everything that
# matters: the repeated title attributes, the ø column before the total, and
# the value inside an <a> in the total cell.
FIXTURE = """
<table class="items">
<thead><tr>
  <th>&nbsp;</th><th>name</th><th>Squad</th><th>&oslash; age</th>
  <th>Foreigners</th><th>&oslash; market value</th><th>Total market value</th>
</tr></thead>
<tbody>
<tr class="odd">
  <td class="zentriert no-border-rechts"><a title="Bayern Munich" href="/x"><img title=" " alt="Bayern Munich" /></a></td>
  <td class="hauptlink no-border-links"><a title="Bayern Munich" href="/x">Bayern Munich</a></td>
  <td class="zentriert"><a title="Bayern Munich" href="/y">38</a></td>
  <td class="zentriert">24.2</td>
  <td class="zentriert">21</td>
  <td class="rechts">&euro;20.46m</td>
  <td class="rechts"><a title="Bayern Munich" href="/y">&euro;777.33m</a></td>
</tr>
<tr class="even">
  <td class="zentriert no-border-rechts"><a title="SC Paderborn 07" href="/x"><img alt="SC Paderborn 07" /></a></td>
  <td class="hauptlink no-border-links"><a title="SC Paderborn 07" href="/x">SC Paderborn 07</a></td>
  <td class="zentriert"><a title="SC Paderborn 07" href="/y">29</a></td>
  <td class="zentriert">25.6</td>
  <td class="zentriert">9</td>
  <td class="rechts">&euro;1.00m</td>
  <td class="rechts"><a title="SC Paderborn 07" href="/y">&euro;28.90m</a></td>
</tr>
<tr class="odd">
  <td class="zentriert no-border-rechts"><a title="Manchester City" href="/x"><img alt="Manchester City" /></a></td>
  <td class="hauptlink no-border-links"><a title="Manchester City" href="/x">Manchester City</a></td>
  <td class="zentriert"><a title="Manchester City" href="/y">25</a></td>
  <td class="zentriert">26.4</td>
  <td class="zentriert">18</td>
  <td class="rechts">&euro;44.79m</td>
  <td class="rechts"><a title="Manchester City" href="/y">&euro;1.50bn</a></td>
</tr>
</tbody>
</table>
"""


def test_parses_total_not_average():
    """The whole bug in one assertion."""
    got = parse_league_season(FIXTURE.replace("&euro;", "€"))
    assert got["Bayern Munich"] == pytest.approx(777.33), (
        "took the ø market-value column instead of the total"
    )
    assert got["SC Paderborn 07"] == pytest.approx(28.90)


def test_billions_are_scaled():
    got = parse_league_season(FIXTURE.replace("&euro;", "€"))
    assert got["Manchester City"] == pytest.approx(1500.0), "bn not converted to m"


def test_every_club_row_is_captured_once():
    got = parse_league_season(FIXTURE.replace("&euro;", "€"))
    assert len(got) == 3, got


def test_no_table_returns_empty_not_crash():
    assert parse_league_season("<html><body>nothing here</body></html>") == {}


@pytest.mark.parametrize("cell,expected", [
    ("€777.33m", 777.33), ("€1.50bn", 1500.0), ("€1.02bn", 1020.0),
    ("€900k", 0.9), ("€1,234.5m", 1234.5), ("€20.46m", 20.46),
    ("<a href='/x'>€45.60m</a>", 45.60), ("no money here", None),
])
def test_money_parsing(cell, expected):
    got = _money_to_m(cell)
    assert got == pytest.approx(expected) if expected is not None else got is None


# ── validator ────────────────────────────────────────────────────────────────

def _table(values: dict[str, float], league="epl", season=2019) -> pd.DataFrame:
    return pd.DataFrame([{"league": league, "season": season,
                          "tm_name": k, "value_eur_m": v} for k, v in values.items()])


def test_validator_catches_the_average_value_column():
    """A league-season whose richest club is tiny is the corrupt signature."""
    corrupt = _table({f"club{i}": 20.0 + i for i in range(18)})
    problems = validate(corrupt)
    assert any("ø market-value" in p or "richest club" in p for p in problems), problems


def test_validator_catches_wrong_club_count():
    too_many = _table({f"club{i}": 300.0 for i in range(30)})
    assert any("clubs (expected" in p for p in validate(too_many)), validate(too_many)


def test_validator_catches_duplicates():
    df = pd.concat([_table({"Arsenal": 800.0, "Chelsea": 700.0})] * 2, ignore_index=True)
    df = pd.concat([df, _table({f"c{i}": 300.0 for i in range(16)})], ignore_index=True)
    assert any("duplicate" in p for p in validate(df)), validate(df)


def test_validator_passes_a_healthy_table():
    healthy = _table({f"club{i}": 900.0 - i * 40 for i in range(18)})
    assert validate(healthy) == []


def test_shipped_table_is_valid():
    """The committed data file must satisfy the validator."""
    from scripts.eval.tm_value_backfill import OUT
    if not OUT.exists():
        pytest.skip("value table not built")
    problems = validate(pd.read_csv(OUT))
    assert not problems, "shipped squad-value table is invalid:\n  " + "\n  ".join(problems)


def test_known_clubs_have_credible_values():
    """Spot-check the clubs the bug hit hardest."""
    from scripts.eval.tm_value_backfill import OUT
    if not OUT.exists():
        pytest.skip("value table not built")
    df = pd.read_csv(OUT)
    for name in ("Manchester City", "Real Madrid", "FC Bayern München", "Bayern Munich",
                 "Paris Saint-Germain", "Inter Milan"):
        rows = df[df.tm_name == name]
        if rows.empty:
            continue
        top = float(rows.value_eur_m.max())
        assert top > MIN_TOP_CLUB_EUR_M, f"{name} peaks at only €{top:.1f}m"
