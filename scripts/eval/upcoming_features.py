"""Carry-forward feature matrix for unplayed fixtures.

Rolling features in the parity frame are team-level snapshots stamped onto each
match row as side-prefixed pairs (home_*/away_* in the champion frame; h_*/a_*
in some eval frames). For an unplayed fixture we take each team's values from
its most recent PLAYED row (home or away side, whichever is later) and re-stamp
them under the correct side prefix.

Cross-team derived columns (elo_diff, xg_diff, form_diff, gk_z_diff,
avail_share_diff, home_xg_sum) ARE knowable pre-match — they are recomputed
from the two sides' carried values, mirroring feature_builders.py semantics
(w0 = first xG window = 3). Matchup-symmetric columns that are genuinely not
knowable pre-assignment (e.g. referee rates) are left None (imputed to 0 by
predict_upcoming's fillna, same as training-time missing).
"""
import pandas as pd

# Longest prefixes first so home_/away_ aren't mis-split as h_/a_.
_HOME_PREFIXES = ("home_", "h_")
_AWAY_PREFIXES = ("away_", "a_")


def _side_key(col: str) -> str | None:
    for p in _HOME_PREFIXES + _AWAY_PREFIXES:
        if col.startswith(p):
            return col[len(p):]
    return None


def _is_home_col(col: str) -> bool:
    return col.startswith(_HOME_PREFIXES)


def _sub(row: dict, a: str, b: str, fill=None):
    va, vb = row.get(a), row.get(b)
    if fill is not None:
        va = fill if va is None else va
        vb = fill if vb is None else vb
    if va is None or vb is None:
        return None
    return va - vb


def _add(row: dict, a: str, b: str):
    va, vb = row.get(a), row.get(b)
    if va is None or vb is None:
        return None
    return va + vb


# Champion feat_base derived columns → recompute from carried side values.
# Mirrors feature_builders.py (xg_diff/home_xg_sum use w0=3) and
# eval_baseline.py (gk_z_diff uses fillna(0)).
_DERIVED = {
    "elo_diff": lambda r: _sub(r, "home_elo", "away_elo"),
    "xg_diff": lambda r: _sub(r, "home_xg_roll_3", "away_xg_roll_3"),
    "home_xg_sum": lambda r: _add(r, "home_xg_roll_3", "away_xg_roll_3"),
    "form_diff": lambda r: _sub(r, "home_form_3", "away_form_3"),
    "gk_z_diff": lambda r: _sub(r, "home_gk_z", "away_gk_z", fill=0.0),
    "avail_share_diff": lambda r: _sub(r, "home_avail_share", "away_avail_share"),
    "is_playoff": lambda r: 0.0,  # forward fixtures default to regular season
}


def latest_team_features(frame: pd.DataFrame, feat_cols: list[str]) -> dict:
    """{team: {suffix: latest value}} from played rows, most recent date wins."""
    played = frame.dropna(subset=["home_goals", "away_goals"]).sort_values("date")
    out: dict[str, dict] = {}
    suffixes = sorted({s for c in feat_cols if (s := _side_key(c))})
    h_cols = {s: next((p + s for p in _HOME_PREFIXES if p + s in frame.columns), None)
              for s in suffixes}
    a_cols = {s: next((p + s for p in _AWAY_PREFIXES if p + s in frame.columns), None)
              for s in suffixes}
    for _, r in played.iterrows():
        out[r["home_team"]] = {s: r.get(h_cols[s]) for s in suffixes if h_cols[s]}
        out[r["away_team"]] = {s: r.get(a_cols[s]) for s in suffixes if a_cols[s]}
    return out


def build_upcoming_row(home: str, away: str, team_feats: dict,
                       feat_cols: list[str]) -> dict:
    hf, af = team_feats.get(home), team_feats.get(away)
    row: dict = {"home_team": home, "away_team": away}
    for c in feat_cols:
        s = _side_key(c)
        if s is None:
            row[c] = None
        elif _is_home_col(c):
            row[c] = None if hf is None else hf.get(s)
        else:
            row[c] = None if af is None else af.get(s)
    # derived cross-team columns are knowable — recompute them
    for c in feat_cols:
        if c in _DERIVED:
            row[c] = _DERIVED[c](row)
    return row


def build_upcoming_features(frame: pd.DataFrame, pairs: list[tuple[str, str]],
                            feat_cols: list[str], season: int) -> pd.DataFrame:
    tf = latest_team_features(frame, feat_cols)
    rows = []
    for i, (h, a) in enumerate(pairs):
        r = build_upcoming_row(h, a, tf, feat_cols)
        r.update({"match_id": f"up_{i}", "season": season})
        rows.append(r)
    return pd.DataFrame(rows)
