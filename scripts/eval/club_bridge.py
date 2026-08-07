"""Per-club continental adjustment — the layer a country coefficient cannot reach.

The problem
-----------
`league_bridge` fits one offset per LEAGUE, anchored on the UEFA country
coefficient. That coefficient measures an association's DEPTH: how many of its
clubs qualify for Europe and how far they collectively go. It is not a statement
about any single club, and applying it flat to every club in a league therefore
gets the elite systematically wrong in both directions:

  * a top-heavy league is under-rated at the top. Paris Saint-Germain has 38
    continental appearances in this dataset, 9 of them quarter-final or later —
    5th most in Europe — while Ligue 1's coefficient is dragged down by clubs
    that exit in August.
  * a deep-but-not-elite league is over-rated at the top. Portugal's coefficient
    is 6th in Europe because Benfica, Porto, Sporting and Braga all enter and
    all accumulate; between them Sporting and Porto have zero quarter-finals in
    the same window.

Owner, 2026-08-07: "the cross league calibration is a mess if PSG, who just
played in the champions league final back to back years, is #18 and portugal has
three teams in the top ten despite no consistent deep european competition runs
in a long time." Both halves of that are measurable, and both are the same
aggregation error.

The fix
-------
A club's own European record is far better evidence about that club than its
country's coefficient. For each club, hold every opponent at its published
rating and find the additive adjustment that best explains that club's own
continental results, then shrink toward zero by how much evidence there is:

    adj = MLE * tau^2 / (tau^2 + se^2)

A club with 38 matches moves most of the way; a club with 7 barely moves; a club
with no continental history keeps its league offset untouched, which is the
correct behaviour — for those clubs the league IS the only evidence.

This deliberately does NOT replace the league offset. It is a second, narrower
layer on top of it, and it only ever speaks for clubs that have played.
"""
from __future__ import annotations

import argparse
import collections
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from data_pipeline.espn_continental import continental_results
from scripts.eval.league_bridge import _COMPS_BY_CONF, _probs_vec, _resolve_uefa_team
from scripts.payload_utils import read_js_payload

_log = logging.getLogger(__name__)

_OUT = Path("experiments/club_continental_offsets.json")
_DATA = Path("webapp/data")

# How far a club may a priori sit from what its league says. 60 ELO — a club can
# plausibly be that much better or worse than its league's average European
# representative without the league offset itself being wrong.
_TAU = 60.0
# Below this many appearances the estimate is noise and the shrinkage would do
# almost nothing anyway; skipping keeps the file small and honest.
_MIN_APPS = 6


def _display_name(league_id: str, frame_key: str) -> str:
    """Football-data frame key -> the name the payload publishes.

    `_resolve_uefa_team` returns frame keys ("Sp Lisbon") while every published
    surface is keyed by display name ("Sporting CP"). Reproduces `tname()` from
    build_league_data, which is the only place the two vocabularies meet.
    """
    # Imported lazily and from build_league_data because that is where the two
    # alias tables actually live; importing it at module scope would drag the
    # whole league builder into every caller.
    from scripts.build_league_data import FD_ESPN, FDI_ESPN
    for table in (FD_ESPN, FDI_ESPN):
        m = table.get(league_id) or {}
        if frame_key in m:
            return m[frame_key]
    return frame_key


def _ladder() -> dict[tuple[str, str], float]:
    """{(league_id, display_name): LEAGUE-ONLY strength} for every rated club.

    Any adjustment this script previously wrote is subtracted back out. That is
    not tidiness, it is the difference between converging and oscillating: the
    payloads are rebuilt daily, so `global_elo` already contains the last run's
    adjustment, and fitting on top of it would measure the residual that
    remains AFTER the correction — near zero — then overwrite the file with
    those near-zero values and silently undo the whole layer on the next build.
    Fit against the league-only baseline every time and the result is stable.
    """
    out: dict[tuple[str, str], float] = {}
    for path in sorted(_DATA.glob("*.js")):
        data = read_js_payload(path)
        if not isinstance(data, dict):
            continue
        lid = (data.get("league") or {}).get("id")
        if not lid:
            continue
        for row in data.get("standings") or []:
            if isinstance(row.get("global_elo"), (int, float)):
                prior_adj = row.get("global_elo_adj") or 0.0
                out[(lid, row["team"])] = float(row["global_elo"]) - float(prior_adj)
    return out


def _matches(strength: dict[tuple[str, str], float]) -> list[tuple]:
    """Continental matches where BOTH clubs are on the ladder.

    Intra-league ties are KEPT here, unlike league_bridge, which drops them
    because they carry no cross-league signal. They carry plenty of per-club
    signal: Real Madrid against Barcelona says a great deal about both.
    """
    rows = []
    for comp in _COMPS_BY_CONF["UEFA"]:
        try:
            df = continental_results(comp)
        except Exception as exc:                       # noqa: BLE001
            _log.warning("club_bridge: %s unavailable: %s", comp, exc)
            continue
        if df is None or df.empty:
            continue
        df = df[df["is_result"] == True]               # noqa: E712
        for _, r in df.iterrows():
            h = _resolve_uefa_team(r["home_team"])
            a = _resolve_uefa_team(r["away_team"])
            if not h or not a:
                continue
            hk = (h[0], _display_name(*h))
            ak = (a[0], _display_name(*a))
            if hk not in strength or ak not in strength:
                continue
            hg, ag = int(r["home_goals"]), int(r["away_goals"])
            rows.append((hk, ak, bool(r.get("neutral", False)),
                         0 if hg > ag else (1 if hg == ag else 2)))
    return rows


def _fit(rows: list[tuple], strength: dict, clubs: list) -> dict[tuple, tuple]:
    """{club: (mle, se, shrunk)} — one profile likelihood per club."""
    neu = np.array([r[2] for r in rows], dtype=bool)
    out = np.array([r[3] for r in rows], dtype=int)
    idx = np.arange(len(out))

    def nll(club, delta):
        sh = np.array([strength[h] + (delta if h == club else 0.0)
                       for h, a, _, _ in rows])
        sa = np.array([strength[a] + (delta if a == club else 0.0)
                       for h, a, _, _ in rows])
        p = _probs_vec(sh, sa, neu, "UEFA")
        return float(-np.log(np.maximum(p[idx, out], 1e-12)).sum())

    fitted = {}
    for club in clubs:
        r = minimize_scalar(lambda d: nll(club, d), bounds=(-400, 400),
                            method="bounded", options={"xatol": 1.0})
        d0, base = r.x, r.fun
        h = 30.0
        curv = (nll(club, d0 + h) + nll(club, d0 - h) - 2 * base) / h ** 2
        if curv <= 0:
            continue
        se = (1.0 / curv) ** 0.5
        if not np.isfinite(se):
            continue
        fitted[club] = (d0, se, d0 * _TAU ** 2 / (_TAU ** 2 + se ** 2))
    return fitted


def _brier(rows, strength, adj) -> float:
    sh = np.array([strength[h] + adj.get(h, 0.0) for h, a, _, _ in rows])
    sa = np.array([strength[a] + adj.get(a, 0.0) for h, a, _, _ in rows])
    neu = np.array([r[2] for r in rows], dtype=bool)
    out = np.array([r[3] for r in rows], dtype=int)
    p = _probs_vec(sh, sa, neu, "UEFA")
    act = np.zeros_like(p)
    act[np.arange(len(out)), out] = 1.0
    return float(((p - act) ** 2).sum(axis=1).mean())


def build(seeds: int = 10, write: bool = True) -> dict:
    strength = _ladder()
    rows = _matches(strength)
    apps = collections.Counter()
    for h, a, _, _ in rows:
        apps[h] += 1
        apps[a] += 1
    clubs = [c for c, n in apps.items() if n >= _MIN_APPS]
    print(f"[club-bridge] {len(rows)} continental matches, "
          f"{len(clubs)} clubs with >={_MIN_APPS} appearances")

    # Held-out gate, same protocol as league_bridge: 70/30, N seeds, adjustments
    # refitted on train only and scored on test.
    wins, with_adj, without = 0, [], []
    for s in range(seeds):
        rng = np.random.default_rng(42 + 100 * s)
        order = rng.permutation(len(rows))
        cut = int(0.7 * len(rows))
        tr = [rows[i] for i in order[:cut]]
        te = [rows[i] for i in order[cut:]]
        tr_apps = collections.Counter()
        for h, a, _, _ in tr:
            tr_apps[h] += 1
            tr_apps[a] += 1
        f = _fit(tr, strength, [c for c, n in tr_apps.items() if n >= _MIN_APPS])
        adj = {c: v[2] for c, v in f.items()}
        a_, b_ = _brier(te, strength, adj), _brier(te, strength, {})
        with_adj.append(a_)
        without.append(b_)
        wins += a_ < b_
    mean_a, mean_b = float(np.mean(with_adj)), float(np.mean(without))
    print(f"[club-bridge] held-out Brier {mean_a:.4f} with adjustments vs "
          f"{mean_b:.4f} without (delta {mean_a - mean_b:+.4f}), "
          f"{wins}/{seeds} seeds")

    adopted = mean_a < mean_b and wins >= 0.7 * seeds
    full = _fit(rows, strength, clubs)
    payload = {
        "generated": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "tau": _TAU, "min_apps": _MIN_APPS, "n_matches": len(rows),
        "holdout": {"with": round(mean_a, 5), "without": round(mean_b, 5),
                    "seeds_won": wins, "seeds": seeds},
        "adopted": bool(adopted),
        "offsets": ({f"{lid}|{team}": round(v[2], 1)
                     for (lid, team), v in full.items()} if adopted else {}),
    }
    if not adopted:
        print("[club-bridge] REJECTED — adjustments do not beat the league-only "
              "ladder on held-out data; writing an empty offset set.")
    if write:
        _OUT.parent.mkdir(parents=True, exist_ok=True)
        _OUT.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"[club-bridge] wrote {_OUT} ({len(payload['offsets'])} clubs)")

    print(f"\n{'club':<26}{'league':<20}{'apps':>5}{'MLE':>7}{'se':>6}{'applied':>9}")
    for (lid, team), (d0, se, sh) in sorted(full.items(), key=lambda kv: -abs(kv[1][2]))[:20]:
        print(f"{team[:25]:<26}{lid[:19]:<20}{apps[(lid, team)]:>5}"
              f"{d0:>+7.0f}{se:>6.0f}{sh:>+9.0f}")
    return payload


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    build(seeds=args.seeds, write=not args.dry_run)


if __name__ == "__main__":
    main()
