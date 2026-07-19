/* webapp/sim-engine.js — shared, versioned Monte Carlo simulation core.
 *
 * Extracted from the duplicated logic in runSim (MLS conference format) and
 * runSimTable (single-table format) in webapp/index.html — S2 of the
 * Intelligence Hub program (docs/intelligence-hub-implementation-instructions.md
 * §5). Pure functions only: no DOM, no page globals, no console — everything
 * needed is passed in explicitly, which is what makes this testable in plain
 * Node with no browser and no bundler (see webapp/sim-engine.test.js).
 *
 * SIM PORTING CONTRACT: the trial-sampling math here (resolveFixedAndFree,
 * simulateTrialPoints) mirrors the server-side simulator in
 * scripts/build_dashboard_data.py and scripts/build_league_data.py. Any
 * change to the sampling rule must be made in all three places.
 *
 * Works both as a browser global (window.SimEngine) and as a CommonJS module
 * (module.exports) for Node-based tests — no build step, no npm dependency.
 */
(function (root, factory) {
  const engine = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = engine;
  }
  if (typeof root !== 'undefined') {
    root.SimEngine = engine;
  }
})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this), function () {
  'use strict';

  const ENGINE_VERSION = 'v1';

  // Mulberry32 — small, fast, seedable PRNG. Deterministic given the same
  // 32-bit integer seed; period ~2^32, adequate for Monte Carlo sampling (not
  // cryptographic). Returns a function equivalent to Math.random(): a float
  // in [0, 1).
  function createPRNG(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Given per-fixture forced results ('H'|'D'|'A'|undefined) and each
  // fixture's home/away team-index arrays, split fixtures into deterministic
  // (already decided) point contributions and the remaining free-to-sample
  // fixture ids.
  function resolveFixedAndFree(nTeams, nFixtures, forced, homeIdx, awayIdx) {
    const fixedPts = new Float64Array(nTeams);
    const free = [];
    for (let id = 0; id < nFixtures; id++) {
      const f = forced[id];
      if (f === 'H') fixedPts[homeIdx[id]] += 3;
      else if (f === 'D') { fixedPts[homeIdx[id]] += 1; fixedPts[awayIdx[id]] += 1; }
      else if (f === 'A') fixedPts[awayIdx[id]] += 3;
      else free.push(id);
    }
    return { fixedPts, free };
  }

  // One Monte Carlo trial: sample every free fixture's H/D/A outcome from its
  // cumulative [pH, pH+pD] thresholds, add to each team's season points, and
  // compute the seeding key (pts*10000 + real goal-diff*10 + small random
  // tiebreak) used by both the MLS playoff bracket and single-table ranking.
  function simulateTrialPoints(prng, nTeams, basePts, baseGd, fixedPts, free,
                                homeIdx, awayIdx, cumHome, cumHomeDraw) {
    const pts = new Float64Array(nTeams);
    const key = new Float64Array(nTeams);
    for (let i = 0; i < nTeams; i++) pts[i] = basePts[i] + fixedPts[i];
    for (const id of free) {
      const u = prng();
      if (u < cumHome[id]) pts[homeIdx[id]] += 3;
      else if (u < cumHomeDraw[id]) { pts[homeIdx[id]] += 1; pts[awayIdx[id]] += 1; }
      else pts[awayIdx[id]] += 3;
    }
    for (let i = 0; i < nTeams; i++) key[i] = pts[i] * 10000 + baseGd[i] * 10 + prng() * 10;
    return { pts, key };
  }

  // 1-indexed finishing position at cumulative quantile q of a position
  // histogram (hist[r] = count of trials finishing in position r+1), out of n trials.
  function percentile(hist, q, n) {
    let c = 0;
    const target = q * n;
    for (let r = 0; r < hist.length; r++) {
      c += hist[r];
      if (c >= target) return r + 1;
    }
    return hist.length;
  }

  // Monte Carlo standard error of a proportion estimate (e.g. "38.2% made
  // the playoffs" from n trials): sqrt(p*(1-p)/n), p as a fraction in [0,1].
  function standardError(pFraction, n) {
    if (n <= 0) return null;
    return Math.sqrt(pFraction * (1 - pFraction) / n);
  }

  function meta(n, seed) {
    return { engine_version: ENGINE_VERSION, n, seed: seed === undefined ? null : seed };
  }

  // Replay an archived intelligence-state snapshot (scripts/archive_intelligence_state.py)
  // and aggregate the MLS conference-format targets that don't require the
  // playoff bracket: playoff/hfa/shield/spoon/conf_win/proj_pts. The
  // bracket-dependent "cup" target needs confBracket, which stays in
  // webapp/index.html (MLS-page rendering logic, not Node-requirable) — see
  // docs/PROJECT_HISTORY.md "Intelligence Hub S3" for the scoping rationale.
  function replayMlsConferenceTargets(snapshot, N) {
    const prng = createPRNG(snapshot.replay_seed);
    const teams = snapshot.teams;
    const nTeams = teams.length;
    const idOf = new Map(teams.map((t, i) => [t.team_id, i]));
    const basePts = new Float64Array(teams.map(t => t.pts));
    const baseGd = new Float64Array(teams.map(t => t.gd));
    const homeIdx = snapshot.fixtures.map(f => idOf.get(f.home_id));
    const awayIdx = snapshot.fixtures.map(f => idOf.get(f.away_id));
    const cumHome = snapshot.fixtures.map(f => f.pH);
    const cumHomeDraw = snapshot.fixtures.map(f => f.pH + f.pD);
    const { fixedPts, free } = resolveFixedAndFree(nTeams, snapshot.fixtures.length, {}, homeIdx, awayIdx);
    const eastIdx = teams.map((t, i) => t.conf === 'East' ? i : -1).filter(i => i >= 0);
    const westIdx = teams.map((t, i) => t.conf === 'West' ? i : -1).filter(i => i >= 0);
    const acc = teams.map(() => ({ proj: 0, playoff: 0, hfa: 0, shield: 0, spoon: 0, conf_win: 0 }));
    for (let s = 0; s < N; s++) {
      const { pts, key } = simulateTrialPoints(prng, nTeams, basePts, baseGd, fixedPts, free,
                                                homeIdx, awayIdx, cumHome, cumHomeDraw);
      for (const ci of [eastIdx, westIdx]) {
        const order = [...ci].sort((a, b) => key[b] - key[a]);
        for (let k = 0; k < snapshot.rules.playoff_slots && k < order.length; k++) acc[order[k]].playoff++;
        for (let k = 0; k < snapshot.rules.hfa_slots && k < order.length; k++) acc[order[k]].hfa++;
        if (order.length) acc[order[0]].conf_win++;
      }
      let bi = 0, wi = 0;
      for (let i = 1; i < nTeams; i++) { if (key[i] > key[bi]) bi = i; if (key[i] < key[wi]) wi = i; }
      acc[bi].shield++; acc[wi].spoon++;
      for (let i = 0; i < nTeams; i++) acc[i].proj += pts[i];
    }
    return teams.map((t, i) => ({
      team_id: t.team_id,
      proj_pts: +(acc[i].proj / N).toFixed(1),
      playoff: +(acc[i].playoff / N * 100).toFixed(1),
      hfa: +(acc[i].hfa / N * 100).toFixed(1),
      shield: +(acc[i].shield / N * 100).toFixed(1),
      spoon: +(acc[i].spoon / N * 100).toFixed(1),
      conf_win: +(acc[i].conf_win / N * 100).toFixed(1),
    }));
  }

  return {
    ENGINE_VERSION,
    createPRNG,
    resolveFixedAndFree,
    simulateTrialPoints,
    percentile,
    standardError,
    replayMlsConferenceTargets,
    meta,
  };
});
