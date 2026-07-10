"""football-data.co.uk "new leagues" adapter (Brazil/Japan/Nordics/Poland/Argentina).

No network — requests.get is monkeypatched to return synthetic CSV text
matching the real schema verified 2026-07-10 (docs/league-expansion-report.md).
"""
import io

import pandas as pd
import pytest

import data_pipeline.football_data_intl as fdi

CALENDAR_CSV = """Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,BFECH,BFECD,BFECA,B365CH,B365CD,B365CA
Brazil,Serie A,2012,19/05/2012,22:30,Palmeiras,Portuguesa,1,1,D,1.75,3.86,5.25,1.76,3.87,5.31,1.69,3.5,4.9,,,,,,
Brazil,Serie A,2012,26/05/2012,20:00,Corinthians,Santos,2,0,H,1.6,3.7,6.0,1.65,3.8,6.1,1.55,3.4,5.5,,,,,,
Brazil,Serie A,2012,11/12/2016,19:00,Chapecoense-SC,Atletico-MG,,,,,,,,,,,,,,,,,,
"""

SPLIT_CSV = """Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,BFECH,BFECD,BFECA,B365CH,B365CD,B365CA
Denmark,Superliga,2012/2013,13/07/2012,17:30,Aarhus,Aalborg,1,1,D,2.37,3.31,3.37,2.38,3.4,3.6,2.18,3.25,3.26,,,,,,
Denmark,Superliga,2012/2013,20/07/2012,17:30,Brondby,FC Copenhagen,0,2,A,3.5,3.3,2.1,3.6,3.4,2.15,3.2,3.1,2.0,,,,,,
"""

# Japan's real file has a typo column: B36CA instead of B365CA.
JAPAN_TYPO_CSV = """Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA,MaxCH,MaxCD,MaxCA,AvgCH,AvgCD,AvgCA,BFECH,BFECD,BFECA,B365CH,B365CD,B36CA
Japan,J1 League,2012,10/03/2012,05:00,Gamba Osaka,Vissel Kobe,2,3,A,1.94,3.56,4.34,1.94,4,5.5,1.71,3.62,4.55,,,,,,
"""


def _mock_get(text, monkeypatch):
    class _Resp:
        def raise_for_status(self): pass
        @property
        def text(self): return text
    monkeypatch.setattr(fdi.requests, "get", lambda *a, **k: _Resp())


# ── _season_int ────────────────────────────────────────────────────────────────

def test_season_int_plain_year():
    assert fdi._season_int("2012") == 2012


def test_season_int_split_year_takes_first():
    assert fdi._season_int("2012/2013") == 2012


def test_season_int_unparseable_is_none():
    assert fdi._season_int("TBD") is None
    assert fdi._season_int(None) is None


# ── _parse_results ─────────────────────────────────────────────────────────────

def test_parse_results_calendar_year_shape():
    df = fdi._parse_results(pd.read_csv(io.StringIO(CALENDAR_CSV)))
    assert list(df.columns) == fdi._COLS
    played = df[df["is_result"]]
    assert len(played) == 2   # the Chapecoense-SC row (no goals) is dropped
    row = played.iloc[0]
    assert row["home_team"] == "Palmeiras" and row["season"] == 2012
    assert row["label_result"] == 1  # draw


def test_parse_results_drops_unresulted_row():
    df = fdi._parse_results(pd.read_csv(io.StringIO(CALENDAR_CSV)))
    assert "Chapecoense-SC" not in set(df["home_team"])


def test_parse_results_split_year_season_is_first_year():
    df = fdi._parse_results(pd.read_csv(io.StringIO(SPLIT_CSV)))
    assert set(df["season"]) == {2012}


def test_parse_results_xg_always_nan():
    df = fdi._parse_results(pd.read_csv(io.StringIO(CALENDAR_CSV)))
    assert df["home_xg"].isna().all() and df["away_xg"].isna().all()


def test_parse_results_match_id_unique_per_fixture():
    df = fdi._parse_results(pd.read_csv(io.StringIO(CALENDAR_CSV)))
    assert df["match_id"].nunique() == len(df)


# ── match_results (mocked network) ──────────────────────────────────────────────

def test_match_results_writes_and_reads_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fdi, "_RESULTS_CACHE_DIR", tmp_path)
    _mock_get(CALENDAR_CSV, monkeypatch)
    df = fdi.match_results("brazil-serie-a")
    assert (tmp_path / "brazil-serie-a.parquet").exists()
    assert len(df[df["is_result"]]) == 2


def test_match_results_season_filter():
    pass  # covered by the seasons= kwarg test below


def test_match_results_seasons_kwarg_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(fdi, "_RESULTS_CACHE_DIR", tmp_path)
    two_season_csv = CALENDAR_CSV + \
        "Brazil,Serie A,2013,15/05/2013,20:00,Santos,Palmeiras,3,1,H,1.8,3.5,4.5,,,,,,,,,,,,\n"
    _mock_get(two_season_csv, monkeypatch)
    df2013 = fdi.match_results("brazil-serie-a", seasons=[2013])
    assert set(df2013["season"]) == {2013}


def test_match_results_unknown_league_raises():
    with pytest.raises(ValueError):
        fdi.match_results("narnia-premier")


def test_match_results_falls_back_to_cache_on_network_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(fdi, "_RESULTS_CACHE_DIR", tmp_path)
    monkeypatch.setattr(fdi, "_RAW_CACHE_DIR", tmp_path / "raw")
    _mock_get(CALENDAR_CSV, monkeypatch)
    first = fdi.match_results("brazil-serie-a")
    assert len(first[first["is_result"]]) == 2

    def _boom(*a, **k):
        raise ConnectionError("network down")
    monkeypatch.setattr(fdi.requests, "get", _boom)
    second = fdi.match_results("brazil-serie-a")
    assert len(second[second["is_result"]]) == 2   # served from cache, not empty


# ── odds parsing / Japan's typo column ───────────────────────────────────────────

def test_devig_row_prefers_pinnacle_closing():
    row = pd.read_csv(io.StringIO(CALENDAR_CSV)).iloc[0]
    got = fdi._devig_row(row)
    assert got is not None
    assert sum(got) == pytest.approx(1.0, abs=1e-6)


def test_market_probs_survives_japans_typo_column(monkeypatch):
    """Japan's real CSV has 'B36CA' not 'B365CA' — the Bet365 fallback set
    must resolve to NaN there, not KeyError, and PSC still works fine."""
    _mock_get(JAPAN_TYPO_CSV, monkeypatch)
    mk = fdi.market_probs("japan-j1")
    assert len(mk) == 1
    assert mk.iloc[0]["home_team"] == "Gamba Osaka"
    assert sum(mk.iloc[0][["mkt_home", "mkt_draw", "mkt_away"]]) == pytest.approx(1.0, abs=1e-6)


def test_market_probs_drops_rows_without_any_odds():
    no_odds = "Country,League,Season,Date,Time,Home,Away,HG,AG,Res\nBrazil,Serie A,2012,19/05/2012,22:30,A,B,1,1,D\n"
    csv = pd.read_csv(io.StringIO(no_odds))
    for col in ("PSCH", "PSCD", "PSCA"):
        assert col not in csv.columns
    # simulate via market_probs' row-by-row logic directly (no odds columns at all)
    out = []
    for _, r in csv.iterrows():
        if fdi._devig_row(r) is not None:
            out.append(r)
    assert out == []


def test_attach_market_left_join_keeps_unmatched_as_nan(monkeypatch):
    _mock_get(CALENDAR_CSV, monkeypatch)
    frame = pd.DataFrame([
        {"season": 2012, "home_team": "Palmeiras", "away_team": "Portuguesa"},
        {"season": 2012, "home_team": "Unmatched FC", "away_team": "Nobody"},
    ])
    out = fdi.attach_market(frame, "brazil-serie-a")
    assert out.iloc[0]["mkt_home"] == pytest.approx(1 / 1.75 / (1/1.75 + 1/3.86 + 1/5.25), abs=1e-3)
    assert pd.isna(out.iloc[1]["mkt_home"])


# ── registry shape ────────────────────────────────────────────────────────────

def test_poland_flagged_as_no_espn_schedule():
    assert "poland-ekstraklasa" in fdi.NO_ESPN_SCHEDULE
    assert fdi.NO_ESPN_SCHEDULE <= set(fdi.COUNTRY)


def test_all_seven_tier1_leagues_registered():
    expected = {"brazil-serie-a", "japan-j1", "sweden-allsvenskan",
               "norway-eliteserien", "denmark-superliga", "poland-ekstraklasa",
               "argentina-primera"}
    assert set(fdi.COUNTRY) == expected
