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


@pytest.fixture(autouse=True)
def _isolate_caches(tmp_path, monkeypatch):
    """Never let a test write into the real data/ tree.

    `_fetch_csv` persists every response to `_RAW_CACHE_DIR` as a side effect,
    so mocking `requests.get` alone is not isolation: before 2026-08-08 this
    module's own fixtures had overwritten the real BRA.csv and JPN.csv caches
    with their 2- and 1-row synthetic bodies, silently disarming the offline
    fallback for those two leagues.
    """
    monkeypatch.setattr(fdi, "_RAW_CACHE_DIR", tmp_path / "raw")
    monkeypatch.setattr(fdi, "_RESULTS_CACHE_DIR", tmp_path / "results")


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
    df = fdi._parse_results(pd.read_csv(io.StringIO(CALENDAR_CSV)), "brazil-serie-a")
    assert list(df.columns) == fdi._COLS
    played = df[df["is_result"]]
    assert len(played) == 2   # the Chapecoense-SC row (no goals) is dropped
    row = played.iloc[0]
    assert row["home_team"] == "Palmeiras" and row["season"] == 2012
    assert row["label_result"] == 1  # draw


def test_parse_results_drops_unresulted_row():
    df = fdi._parse_results(pd.read_csv(io.StringIO(CALENDAR_CSV)), "brazil-serie-a")
    assert "Chapecoense-SC" not in set(df["home_team"])


def test_parse_results_split_year_season_is_first_year():
    df = fdi._parse_results(pd.read_csv(io.StringIO(SPLIT_CSV)), "denmark-superliga")
    assert set(df["season"]) == {2012}


def test_parse_results_xg_always_nan():
    df = fdi._parse_results(pd.read_csv(io.StringIO(CALENDAR_CSV)), "brazil-serie-a")
    assert df["home_xg"].isna().all() and df["away_xg"].isna().all()


def test_parse_results_match_id_unique_per_fixture():
    df = fdi._parse_results(pd.read_csv(io.StringIO(CALENDAR_CSV)), "brazil-serie-a")
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
    # 2026-07-10 wave (the original seven) …
    wave1 = {"brazil-serie-a", "japan-j1", "sweden-allsvenskan",
             "norway-eliteserien", "denmark-superliga", "poland-ekstraklasa",
             "argentina-primera"}
    # … plus the 2026-07-11 round-4 additions (footballdata_intl top flights +
    # projection-only China/Russia). Finland is added with Phase 3 (API key).
    round4 = {"austria-bundesliga", "swiss-super-league", "romania-liga1",
              "ireland-premier", "china-super", "russia-premier",
              "finland-veikkausliiga"}
    assert set(fdi.COUNTRY) == wave1 | round4


# ── competition filter ────────────────────────────────────────────────────────
# Each `new/<CCC>.csv` is a COUNTRY file, not a competition file. Surveyed
# 2026-08-08 across all 14 cached files: ARG mixes the Liga Profesional with the
# Copa de la Liga Profesional, SWZ carries two Challenge League rows, and five
# files carry a trailing-space variant of their own name (an era split, not a
# different competition). Fixtures below mirror the real headers — note that the
# Argentine and Swiss files have NO Country column, only League.

ARG_MIXED_CSV = """League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA
Liga Profesional ,2016/2017,20/08/2016,17:00,Boca Juniors,River Plate,1,0,H,2.1,3.3,3.6
Liga Profesional,2024,10/05/2024,20:00,Racing Club,Independiente,2,2,D,2.0,3.2,3.9
Copa De La Liga Profesional,2024,25/01/2024,22:00,Racing Club,Independiente,1,0,H,2.2,3.1,3.5
"""

SWZ_MIXED_CSV = """League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA
Super League,2020/2021,15/08/2020,18:00,Basel,Young Boys,0,2,A,2.6,3.5,2.6
Challenge League,2020/2021,27/05/2021,20:30,Thun,Sion,1,4,A,2.4,3.4,2.9
"""

SWZ_ALL_FOREIGN_CSV = """League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA
Challenge League,2020/2021,27/05/2021,20:30,Thun,Sion,1,4,A,2.4,3.4,2.9
"""

NO_LEAGUE_COL_CSV = """Country,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA
Brazil,2012,19/05/2012,22:30,Palmeiras,Portuguesa,1,1,D,1.75,3.86,5.25
"""


def test_norm_competition_strips_and_casefolds():
    assert fdi._norm_competition("Liga Profesional ") == "liga profesional"
    assert fdi._norm_competition("  SUPER   League ") == "super league"


def test_trailing_space_variant_normalises_to_the_same_competition():
    """The 2,114-row trap: ARG's older era carries 'Liga Profesional ' with a
    trailing space. An exact-match filter would silently drop a third of it."""
    assert (fdi._norm_competition("Liga Profesional ")
            == fdi._norm_competition("Liga Profesional"))


def test_parse_results_keeps_both_whitespace_variants_of_the_league():
    df = fdi._parse_results(pd.read_csv(io.StringIO(ARG_MIXED_CSV)),
                            "argentina-primera")
    assert set(df["home_team"]) == {"Boca Juniors", "Racing Club"}
    assert len(df[df["season"] == 2016]) == 1   # the trailing-space era survives


def test_parse_results_flags_non_league_competition_without_dropping_it():
    """Argentina's Copa de la Liga is contested by the same top-flight clubs, so
    it stays in the frame for ELO/Dixon-Coles, but `is_playoff=1` keeps it out
    of the league table (build_league_data filters on exactly that flag)."""
    df = fdi._parse_results(pd.read_csv(io.StringIO(ARG_MIXED_CSV)),
                            "argentina-primera")
    copa = df[df["date"] == pd.Timestamp("2024-01-25")]
    assert len(copa) == 1
    assert int(copa.iloc[0]["is_playoff"]) == 1


def test_parse_results_leaves_league_rows_unflagged():
    df = fdi._parse_results(pd.read_csv(io.StringIO(ARG_MIXED_CSV)),
                            "argentina-primera")
    liga = df[df["date"] == pd.Timestamp("2024-05-10")]
    assert int(liga.iloc[0]["is_playoff"]) == 0


def test_parse_results_drops_a_foreign_competition():
    """SWZ's two 2020/21 rows labelled 'Challenge League' are the Thun-Sion
    relegation barrage — a different competition, not this league's data."""
    df = fdi._parse_results(pd.read_csv(io.StringIO(SWZ_MIXED_CSV)),
                            "swiss-super-league")
    assert len(df) == 1
    assert df.iloc[0]["home_team"] == "Basel"


def test_select_competitions_raises_when_nothing_matches_the_league():
    """A mis-specified filter must fail loudly, never quietly empty a league."""
    csv = pd.read_csv(io.StringIO(SWZ_ALL_FOREIGN_CSV))
    with pytest.raises(ValueError, match="no rows"):
        fdi._select_competitions(csv, "swiss-super-league")


def test_select_competitions_keeps_every_row_when_the_file_declares_nothing():
    """Absence of evidence must never drop data — several country files have no
    Country column and a future one may drop League too."""
    csv = pd.read_csv(io.StringIO(NO_LEAGUE_COL_CSV))
    out = fdi._select_competitions(csv, "brazil-serie-a")
    assert len(out) == len(csv)
    assert not out["_non_league"].any()


def test_every_registered_league_declares_its_competitions():
    assert set(fdi.LEAGUE_COMPETITIONS) == set(fdi.COUNTRY)
    assert set(fdi.NON_LEAGUE_COMPETITIONS) <= set(fdi.COUNTRY)
    for lid, names in fdi.LEAGUE_COMPETITIONS.items():
        assert names, f"{lid} declares no competition"
        assert all(n == fdi._norm_competition(n) for n in names), \
            f"{lid} declares an unnormalised competition name"


def test_market_probs_excludes_a_foreign_competition(monkeypatch):
    _mock_get(SWZ_MIXED_CSV, monkeypatch)
    mk = fdi.market_probs("swiss-super-league")
    assert list(mk["home_team"]) == ["Basel"]


def test_attach_market_distinguishes_two_meetings_of_one_pair_in_a_season(monkeypatch):
    """Racing v Independiente happens twice in 2024 — once in the Liga, once in
    the Copa. Merging on (season, home, away) alone fans one frame row into two
    and attaches the other tournament's price."""
    _mock_get(ARG_MIXED_CSV, monkeypatch)
    frame = fdi._parse_results(pd.read_csv(io.StringIO(ARG_MIXED_CSV)),
                               "argentina-primera")
    out = fdi.attach_market(frame, "argentina-primera")
    assert len(out) == len(frame)
    liga = out[out["date"] == pd.Timestamp("2024-05-10")].iloc[0]
    inv = 1 / 2.0 + 1 / 3.2 + 1 / 3.9        # the Liga row's own odds, not the Copa's
    assert liga["mkt_home"] == pytest.approx((1 / 2.0) / inv, abs=1e-6)


def test_cached_raw_files_declare_only_known_competitions():
    """Guards against football-data renaming a competition under us: every value
    in every cached file must be one we have classified."""
    from pathlib import Path
    raw = Path(__file__).resolve().parent.parent / "data/football_data_intl/raw"
    by_code = {code: lid for lid, code in fdi.COUNTRY.items()}
    seen = 0
    for code, lid in sorted(by_code.items()):
        path = raw / f"{code}.csv"
        if not path.exists():
            continue
        seen += 1
        csv = pd.read_csv(path)
        if "League" not in csv.columns:
            continue
        known = (fdi.LEAGUE_COMPETITIONS[lid]
                 | fdi.NON_LEAGUE_COMPETITIONS.get(lid, frozenset())
                 | fdi.FOREIGN_COMPETITIONS.get(lid, frozenset()))
        found = {fdi._norm_competition(v) for v in csv["League"].dropna().unique()}
        assert found <= known, f"{code}.csv has unclassified competition(s): {found - known}"
    if not seen:
        pytest.skip("no cached raw CSVs in this checkout")


def test_attach_market_never_changes_row_count_without_a_date_column(monkeypatch):
    """build_league_data slices `played[["season","home_team","away_team"]]`
    before calling this, so the date key is unavailable there. The left-merge
    must still never multiply the caller's frame."""
    _mock_get(ARG_MIXED_CSV, monkeypatch)
    frame = pd.DataFrame([
        {"season": 2024, "home_team": "Racing Club", "away_team": "Independiente"},
    ])
    out = fdi.attach_market(frame, "argentina-primera")
    assert len(out) == 1


def test_dropped_competitions_are_declared_not_merely_unlisted():
    """A stray competition we choose to drop must be named, so the warning path
    stays reserved for a competition football-data has renamed under us."""
    assert set(fdi.FOREIGN_COMPETITIONS) <= set(fdi.COUNTRY)
    for lid, names in fdi.FOREIGN_COMPETITIONS.items():
        assert all(n == fdi._norm_competition(n) for n in names)
        assert not (names & fdi.LEAGUE_COMPETITIONS[lid])


def test_undeclared_competition_is_dropped_with_a_warning(caplog):
    """A renamed competition must be loud, not silent."""
    renamed = SWZ_MIXED_CSV.replace("Challenge League", "Promotion League")
    with caplog.at_level("WARNING"):
        df = fdi._parse_results(pd.read_csv(io.StringIO(renamed)),
                                "swiss-super-league")
    assert len(df) == 1
    assert "UNDECLARED" in caplog.text and "promotion league" in caplog.text


def test_declared_foreign_competition_is_dropped_quietly(caplog):
    with caplog.at_level("WARNING"):
        df = fdi._parse_results(pd.read_csv(io.StringIO(SWZ_MIXED_CSV)),
                                "swiss-super-league")
    assert len(df) == 1
    assert "UNDECLARED" not in caplog.text
