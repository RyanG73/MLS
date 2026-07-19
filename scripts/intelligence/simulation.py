"""Deterministic table simulation and fixture-leverage calculations."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


OUTCOME_POINTS = {
    "H": (3.0, 0.0),
    "D": (1.0, 1.0),
    "A": (0.0, 3.0),
}


def _rules(snapshot: dict) -> list[dict]:
    return [rule for rule in snapshot.get("rules", {}).get("targets", [])
            if rule.get("key")]


@dataclass
class TrialBatch:
    snapshot: dict
    n: int
    seed: int

    def __post_init__(self) -> None:
        self.teams = self.snapshot["teams"]
        self.team_ids = [team["team_id"] for team in self.teams]
        self.index = {team_id: i for i, team_id in enumerate(self.team_ids)}
        self.fixtures = self.snapshot.get("fixtures") or []
        self.base_points = np.array([float(team.get("pts") or 0) for team in self.teams])
        self.base_gd = np.array([float(team.get("gd") or 0) for team in self.teams])
        self.home = np.array([self.index[fixture["home_id"]] for fixture in self.fixtures], dtype=int)
        self.away = np.array([self.index[fixture["away_id"]] for fixture in self.fixtures], dtype=int)
        self.rng = np.random.default_rng(self.seed)
        self.random = self.rng.random((self.n, len(self.fixtures)))
        self.jitter = self.rng.random((self.n, len(self.teams))) * 10
        self.sampled = np.zeros((self.n, len(self.fixtures)), dtype=np.int8)
        self.points = np.tile(self.base_points, (self.n, 1))
        for fixture_index, fixture in enumerate(self.fixtures):
            u = self.random[:, fixture_index]
            outcomes = np.where(
                u < fixture["pH"], 0,
                np.where(u < fixture["pH"] + fixture["pD"], 1, 2),
            )
            self.sampled[:, fixture_index] = outcomes
            self._add_sampled(self.points, fixture_index, outcomes, 1.0)

    def _add_sampled(self, points: np.ndarray, fixture_index: int,
                     outcomes: np.ndarray, multiplier: float) -> None:
        home, away = self.home[fixture_index], self.away[fixture_index]
        rows = np.arange(self.n)
        points[rows, home] += multiplier * np.where(
            outcomes == 0, 3.0, np.where(outcomes == 1, 1.0, 0.0))
        points[rows, away] += multiplier * np.where(
            outcomes == 2, 3.0, np.where(outcomes == 1, 1.0, 0.0))

    def forced_points(self, fixture_index: int, outcome: str) -> np.ndarray:
        points = self.points.copy()
        self._add_sampled(points, fixture_index, self.sampled[:, fixture_index], -1.0)
        home_pts, away_pts = OUTCOME_POINTS[outcome]
        points[:, self.home[fixture_index]] += home_pts
        points[:, self.away[fixture_index]] += away_pts
        return points

    def aggregate(self, points: np.ndarray) -> dict[str, dict]:
        order = np.argsort(-(points * 10000 + self.base_gd * 10 + self.jitter), axis=1)
        ranks = np.empty_like(order)
        ranks[np.arange(self.n)[:, None], order] = np.arange(1, len(self.teams) + 1)
        target_values: dict[str, np.ndarray] = {}
        for rule in _rules(self.snapshot):
            key = rule["key"]
            membership = np.zeros_like(points, dtype=float)
            if rule.get("per_conf_top"):
                top = int(rule["per_conf_top"])
                conferences = sorted({team.get("conf") for team in self.teams if team.get("conf")})
                for conference in conferences:
                    members = [i for i, team in enumerate(self.teams)
                               if team.get("conf") == conference]
                    if not members:
                        continue
                    conf_order = np.argsort(
                        -(points[:, members] * 10000
                          + self.base_gd[members] * 10
                          + self.jitter[:, members]), axis=1)
                    chosen = np.array(members)[conf_order[:, :top]]
                    membership[np.arange(self.n)[:, None], chosen] = 1.0
            elif rule.get("top"):
                membership = (ranks <= int(rule["top"])).astype(float)
            elif rule.get("bottom"):
                membership = (ranks > len(self.teams) - int(rule["bottom"])).astype(float)
            elif rule.get("band"):
                lo, hi = rule["band"]
                membership = ((ranks >= int(lo)) & (ranks <= int(hi))).astype(float)
            elif rule.get("promo_top"):
                auto = ranks <= int(rule["promo_top"])
                lo, hi = rule["playoff_band"]
                playoff = (ranks >= int(lo)) & (ranks <= int(hi))
                playoff_share = float(rule.get("barrage_win_rate", 1.0)) / max(int(hi) - int(lo) + 1, 1)
                membership = auto.astype(float) + playoff.astype(float) * playoff_share
            else:
                continue
            target_values[key] = membership.mean(axis=0) * 100
        return {
            team_id: {
                "proj_pts": round(float(points[:, index].mean()), 1),
                "proj_rank": round(float(ranks[:, index].mean()), 1),
                **{key: round(float(values[index]), 1)
                   for key, values in target_values.items()},
            }
            for index, team_id in enumerate(self.team_ids)
        }

    def baseline(self) -> dict[str, dict]:
        return self.aggregate(self.points)

    def force_fixture(self, fixture_index: int, outcome: str) -> dict[str, dict]:
        return self.aggregate(self.forced_points(fixture_index, outcome))


def run_simulation(snapshot: dict, forced: dict[str, str] | None = None,
                   n: int | None = None, seed: int | None = None) -> dict[str, dict]:
    n = n or min(int(snapshot.get("n_sims") or 2000), 5000)
    seed = int(snapshot.get("replay_seed") if seed is None else seed)
    batch = TrialBatch(snapshot, n, seed)
    points = batch.points.copy()
    fixture_index = {fixture["fixture_id"]: index
                     for index, fixture in enumerate(batch.fixtures)}
    for fixture_id, outcome in (forced or {}).items():
        if fixture_id not in fixture_index or outcome not in OUTCOME_POINTS:
            raise ValueError(f"invalid scenario assumption: {fixture_id}={outcome}")
        index = fixture_index[fixture_id]
        batch._add_sampled(points, index, batch.sampled[:, index], -1.0)
        home_pts, away_pts = OUTCOME_POINTS[outcome]
        points[:, batch.home[index]] += home_pts
        points[:, batch.away[index]] += away_pts
    return batch.aggregate(points)


def fixture_leverage(snapshot: dict, target_by_team: dict[str, str],
                     n: int = 400) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """Evaluate every fixture under H/D/A using one common-random trial batch."""
    batch = TrialBatch(snapshot, n, int(snapshot["replay_seed"]))
    baseline = batch.baseline()
    per_team = {team_id: [] for team_id in batch.team_ids}
    for fixture_index, fixture in enumerate(batch.fixtures):
        outcomes = {
            outcome: batch.force_fixture(fixture_index, outcome)
            for outcome in ("H", "D", "A")
        }
        for team_id in batch.team_ids:
            target = target_by_team.get(team_id)
            if not target or target not in baseline[team_id]:
                continue
            values = {outcome: result[team_id][target]
                      for outcome, result in outcomes.items()}
            leverage = round(max(values.values()) - min(values.values()), 1)
            is_own = team_id in (fixture["home_id"], fixture["away_id"])
            if not is_own and leverage < 0.5:
                continue
            expected = round(
                fixture["pH"] * values["H"]
                + fixture["pD"] * values["D"]
                + fixture["pA"] * values["A"]
                - baseline[team_id][target], 1)
            per_team[team_id].append({
                "fixture_id": fixture["fixture_id"],
                "date": fixture["date"],
                "ko": fixture.get("ko"),
                "home": fixture["home"],
                "away": fixture["away"],
                "home_id": fixture["home_id"],
                "away_id": fixture["away_id"],
                "is_own_fixture": is_own,
                "target_metric": target,
                "baseline_pct": baseline[team_id][target],
                "conditional_pct": values,
                "leverage_pp": leverage,
                "expected_move_pp": expected,
                "evidence_ids": [f"fixture:{fixture['fixture_id']}",
                                 f"snapshot:{snapshot['snapshot_id']}"],
            })
    for rows in per_team.values():
        rows.sort(key=lambda row: (-row["leverage_pp"], row["date"], row["fixture_id"]))
    return baseline, per_team
