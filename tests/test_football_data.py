"""football-data.co.uk per-season adapter — division-integrity guard.

No network — requests.get is monkeypatched.

Regression cover for 2026-08-08: football-data.co.uk 301-redirected the
not-yet-published Spanish 2026-27 files onto the Scottish ones
(`mmz4281/2627/SP2.csv` -> `SC2.csv`, and `SP1.csv` -> `SC1.csv`). requests
follows redirects by default and `raise_for_status()` sees the final 200, so
five Scottish League One results were cached as `SP2-2627.csv` and parsed into
LaLiga 2's canonical frame. That pushed `max_played_season` to 2026 and would
have rendered Scottish clubs in Segunda's published table on the next refresh.
"""
import io

import pandas as pd

import data_pipeline.football_data as fd

_HEADER = ("Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,Referee,"
           "B365H,B365D,B365A")

# What football-data actually served for SP2.csv on 2026-08-08 (Scottish
# League One), reproduced with the mangled BOM the cache really carries:
# `_fetch_csv` writes `r.text`, and requests decodes a charset-less text/csv as
# ISO-8859-1, so the UTF-8 BOM survives as the three literal chars "ï»¿".
SC2_CSV = "ï»¿" + _HEADER + "\n" + "\n".join([
    "SC2,01/08/2026,15:00,Alloa,East Fife,0,0,D,0,0,D,J Kennedy,1.9,3.5,3.4",
    "SC2,01/08/2026,15:00,Montrose,Hamilton,0,5,A,0,2,A,A Hendry,3.3,3.4,1.9",
    "SC2,01/08/2026,15:00,Peterhead,Ross County,0,1,A,0,0,D,C Stirling,3.5,4,1.73",
]) + "\n"

# A genuine SP2 file, same shape.
SP2_CSV = _HEADER + "\n" + "\n".join([
    "SP2,16/08/2026,19:00,Almeria,Albacete,2,0,H,1,0,H,Munuera,1.8,3.4,4.5",
    "SP2,17/08/2026,19:00,Burgos,Cadiz,1,1,D,0,1,A,Pulido,2.4,3.1,3.2",
]) + "\n"


def _mock_get(text, monkeypatch, *, redirected_to=None):
    class _Resp:
        url = redirected_to or "https://www.football-data.co.uk/mmz4281/2627/SP2.csv"
        history = [object()] if redirected_to else []

        def raise_for_status(self):
            pass

        @property
        def text(self):
            return text

    monkeypatch.setattr(fd.requests, "get", lambda *a, **k: _Resp())


def _cache_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(fd, "_RESULTS_CACHE_DIR", tmp_path)
    monkeypatch.setattr(fd, "_RAW_CACHE_DIR", tmp_path / "raw")
    monkeypatch.setattr(fd, "_health", lambda *a, **k: None)


# ── _division_of ─────────────────────────────────────────────────────────────

def test_division_of_reads_the_div_column():
    assert fd._division_of(pd.read_csv(io.StringIO(SP2_CSV))) == {"SP2"}


def test_division_of_survives_the_mangled_bom():
    """The real cached header is 'ï»¿Div', not 'Div' — read it positionally."""
    df = pd.read_csv(io.StringIO(SC2_CSV))
    assert df.columns[0] != "Div"          # guards the premise
    assert fd._division_of(df) == {"SC2"}


def test_division_of_is_empty_when_there_is_no_div_column():
    """Absence of evidence must never block a fetch."""
    df = pd.DataFrame({"HomeTeam": ["A"], "AwayTeam": ["B"]})
    assert fd._division_of(df) == set()


# ── _fetch_csv division guard ────────────────────────────────────────────────

def test_fetch_csv_rejects_a_redirected_wrong_division(tmp_path, monkeypatch):
    """SP2.csv that 301s to SC2.csv must be refused, not cached."""
    _cache_dirs(tmp_path, monkeypatch)
    _mock_get(SC2_CSV, monkeypatch,
              redirected_to="https://www.football-data.co.uk/mmz4281/2627/SC2.csv")
    assert fd._fetch_csv("SP2", 2026) is None
    assert not (tmp_path / "raw" / "SP2-2627.csv").exists(), \
        "a rejected response must never reach the disk cache"


def test_fetch_csv_accepts_the_matching_division(tmp_path, monkeypatch):
    _cache_dirs(tmp_path, monkeypatch)
    _mock_get(SP2_CSV, monkeypatch)
    got = fd._fetch_csv("SP2", 2026)
    assert got is not None and len(got) == 2
    assert (tmp_path / "raw" / "SP2-2627.csv").exists()


def test_fetch_csv_distrusts_an_already_poisoned_cache(tmp_path, monkeypatch):
    """The bad file is already on disk from an earlier run — do not serve it."""
    _cache_dirs(tmp_path, monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    (raw / "SP2-2627.csv").write_text(SC2_CSV)

    _mock_get(SP2_CSV, monkeypatch)          # the site has since been fixed
    got = fd._fetch_csv("SP2", 2026)
    assert got is not None
    assert fd._division_of(got) == {"SP2"}, "poisoned cache was served instead of re-fetching"


# ── match_results integration ────────────────────────────────────────────────

def test_match_results_drops_a_wrong_division_season(tmp_path, monkeypatch):
    """The whole point: Scottish rows must not enter LaLiga 2's frame.

    With the season refused, segunda's max played season stays 2025, which is
    what lets the build's pre-season flip reach ESPN for the real fixtures.
    """
    _cache_dirs(tmp_path, monkeypatch)
    _mock_get(SC2_CSV, monkeypatch,
              redirected_to="https://www.football-data.co.uk/mmz4281/2627/SC2.csv")
    df = fd.match_results("segunda", seasons=[2026], refresh_latest=True)
    assert df.empty
    scots = {"Alloa", "East Fife", "Montrose", "Hamilton", "Peterhead", "Ross County"}
    assert not (set(df["home_team"]) | set(df["away_team"])) & scots
