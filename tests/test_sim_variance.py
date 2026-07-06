import math

import numpy as np

from scripts.eval.sim_variance import (
    ELO_LOGIT_K,
    gap_sigma_multiplier,
    perturb_probs,
    team_sigmas,
)


def _fixture_probs():
    """3 fixtures × 3 outcomes (H/D/A), rows sum to 1."""
    return np.array([
        [0.50, 0.28, 0.22],
        [0.33, 0.33, 0.34],
        [0.15, 0.25, 0.60],
    ])


def test_zero_delta_is_identity():
    P = _fixture_probs()
    LP = np.log(P)
    RH = np.array([0, 1, 2])
    RA = np.array([1, 2, 0])
    delta = np.zeros(3)
    out = perturb_probs(LP, RH, RA, delta)
    np.testing.assert_allclose(out, P, atol=1e-12)


def test_positive_home_delta_shifts_toward_home():
    P = _fixture_probs()
    LP = np.log(P)
    RH = np.array([0])
    RA = np.array([1])
    delta = np.array([100.0, 0.0])
    out = perturb_probs(LP[:1], RH, RA, delta)
    assert out[0, 0] > P[0, 0]          # home win prob up
    assert out[0, 2] < P[0, 2]          # away win prob down
    np.testing.assert_allclose(out.sum(axis=1), 1.0)


def test_equal_delta_both_teams_is_identity():
    P = _fixture_probs()
    LP = np.log(P)
    RH = np.array([0, 1])
    RA = np.array([1, 0])
    delta = np.array([70.0, 70.0])
    out = perturb_probs(LP[:2], RH, RA, delta)
    np.testing.assert_allclose(out, P[:2], atol=1e-12)


def test_400_points_shift_home_away_odds_ratio_by_10x():
    # ELO consistency: +400 differential multiplies the home-vs-away
    # odds ratio by exactly 10 (the ELO expectation curve's scale).
    P = _fixture_probs()
    LP = np.log(P)
    RH = np.array([0])
    RA = np.array([1])
    out = perturb_probs(LP[:1], RH, RA, np.array([400.0, 0.0]))
    ratio_before = P[0, 0] / P[0, 2]
    ratio_after = out[0, 0] / out[0, 2]
    np.testing.assert_allclose(ratio_after / ratio_before, 10.0, rtol=1e-9)
    # and the constant itself encodes ln(10)/800 per side
    np.testing.assert_allclose(ELO_LOGIT_K, math.log(10.0) / 800.0)


def test_gap_sigma_multiplier():
    assert gap_sigma_multiplier(0.0, gamma=1.0) == 1.0
    assert gap_sigma_multiplier(100.0, gamma=1.0) == 1.5   # 1 + 100/200
    assert gap_sigma_multiplier(100.0, gamma=0.0) == 1.0   # gamma off
    assert gap_sigma_multiplier(400.0, gamma=1.0) == 1.5   # capped
    assert gap_sigma_multiplier(-100.0, gamma=1.0) == 1.5  # |gap| symmetric


def test_team_sigmas_vector():
    tids = ["A", "B", "C"]
    gaps = {"A": 100.0, "C": -400.0}   # B missing → gap 0
    sig = team_sigmas(tids, gaps, sigma_base=50.0, gamma=1.0)
    np.testing.assert_allclose(sig, [75.0, 50.0, 75.0])


def test_perturbation_widens_simulated_points_distribution():
    # Mini season sim: 4 teams double round-robin, all fixtures 40/25/35.
    # Per-sim strength perturbations must increase the across-sim variance
    # of a team's final points (the production preseason-widening contract).
    rng = np.random.default_rng(0)
    nT, n_sims = 4, 2000
    fixtures = [(h, a) for h in range(nT) for a in range(nT) if h != a]
    RH = np.array([f[0] for f in fixtures])
    RA = np.array([f[1] for f in fixtures])
    P = np.tile([0.40, 0.25, 0.35], (len(fixtures), 1))
    LP = np.log(P)

    def run(sigma):
        pts = np.zeros((n_sims, nT))
        for s in range(n_sims):
            Ps = (perturb_probs(LP, RH, RA, rng.standard_normal(nT) * sigma)
                  if sigma else P)
            u = rng.random(len(fixtures))
            o = np.where(u < Ps[:, 0], 0, np.where(u < Ps[:, 0] + Ps[:, 1], 1, 2))
            np.add.at(pts[s], RH[o == 0], 3)
            np.add.at(pts[s], RH[o == 1], 1)
            np.add.at(pts[s], RA[o == 1], 1)
            np.add.at(pts[s], RA[o == 2], 3)
        return pts.std(axis=0).mean()

    assert run(60.0) > run(0.0) * 1.05
