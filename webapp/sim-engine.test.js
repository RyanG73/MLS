// webapp/sim-engine.test.js — plain Node characterization tests for sim-engine.js.
// Run directly: `node webapp/sim-engine.test.js` (no npm install, no framework —
// matches this repo's "no JS build tooling" convention). Wrapped by
// tests/test_sim_engine_js.py so `pytest tests/` remains the single CI entrypoint.
const assert = require('node:assert');
const SimEngine = require('./sim-engine.js');

function test(name, fn) {
  try { fn(); console.log(`ok - ${name}`); }
  catch (e) { console.error(`not ok - ${name}\n  ${e.stack}`); process.exitCode = 1; }
}

test('createPRNG is deterministic for the same seed', () => {
  const a = SimEngine.createPRNG(42);
  const b = SimEngine.createPRNG(42);
  const seqA = [a(), a(), a()];
  const seqB = [b(), b(), b()];
  assert.deepStrictEqual(seqA, seqB);
});

test('createPRNG produces values in [0, 1)', () => {
  const rng = SimEngine.createPRNG(7);
  for (let i = 0; i < 1000; i++) {
    const v = rng();
    assert.ok(v >= 0 && v < 1, `value out of range: ${v}`);
  }
});

test('createPRNG differs across seeds', () => {
  const a = SimEngine.createPRNG(1)();
  const b = SimEngine.createPRNG(2)();
  assert.notStrictEqual(a, b);
});

test('resolveFixedAndFree splits forced vs free fixtures', () => {
  // 2 teams, 3 fixtures: fixture 0 forced H (home=team0), fixture 1 forced D
  // (home=team0, away=team1), fixture 2 free.
  const { fixedPts, free } = SimEngine.resolveFixedAndFree(
    2, 3, { 0: 'H', 1: 'D' }, [0, 0, 1], [1, 1, 0]
  );
  assert.strictEqual(fixedPts[0], 3 + 1); // fixture0 H (+3 home) + fixture1 D (+1 home)
  assert.strictEqual(fixedPts[1], 1);     // fixture1 D (+1 away)
  assert.deepStrictEqual(free, [2]);
});

test('resolveFixedAndFree treats undefined as free', () => {
  const { fixedPts, free } = SimEngine.resolveFixedAndFree(2, 2, {}, [0, 1], [1, 0]);
  assert.deepStrictEqual(free, [0, 1]);
  assert.strictEqual(fixedPts[0], 0);
  assert.strictEqual(fixedPts[1], 0);
});

test('simulateTrialPoints samples a free fixture as H, D, or A only', () => {
  const prng = SimEngine.createPRNG(123);
  const basePts = new Float64Array([10, 20]);
  const baseGd = new Float64Array([1, -1]);
  const fixedPts = new Float64Array([0, 0]);
  const { pts, key } = SimEngine.simulateTrialPoints(
    prng, 2, basePts, baseGd, fixedPts, [0], [0], [1], [0.5], [0.7]
  );
  const added = (pts[0] - basePts[0]) + (pts[1] - basePts[1]);
  assert.ok(added === 3 || added === 2, `unexpected points added: ${added}`);
  assert.strictEqual(key.length, 2);
});

test('simulateTrialPoints is fully reproducible given the same seed', () => {
  const basePts = new Float64Array([10, 20, 5]);
  const baseGd = new Float64Array([1, -1, 0]);
  const fixedPts = new Float64Array([0, 0, 0]);
  const homeIdx = [0, 1], awayIdx = [1, 2], cumHome = [0.4, 0.5], cumHomeDraw = [0.6, 0.7];
  const run = (seed) => {
    const prng = SimEngine.createPRNG(seed);
    return SimEngine.simulateTrialPoints(prng, 3, basePts, baseGd, fixedPts, [0, 1], homeIdx, awayIdx, cumHome, cumHomeDraw);
  };
  const r1 = run(999), r2 = run(999);
  assert.deepStrictEqual(Array.from(r1.pts), Array.from(r2.pts));
  assert.deepStrictEqual(Array.from(r1.key), Array.from(r2.key));
});

test('percentile returns the position at the requested cumulative quantile', () => {
  const hist = [3, 7]; // position1(idx0)=3 trials, position2(idx1)=7 trials, n=10
  assert.strictEqual(SimEngine.percentile(hist, 0.10, 10), 1);
  assert.strictEqual(SimEngine.percentile(hist, 0.50, 10), 2);
  assert.strictEqual(SimEngine.percentile(hist, 1.0, 10), 2);
});

test('standardError matches the binomial proportion formula', () => {
  const se = SimEngine.standardError(0.5, 100);
  assert.ok(Math.abs(se - 0.05) < 1e-9, `expected 0.05, got ${se}`);
});

test('standardError handles n=0 without dividing by zero', () => {
  assert.strictEqual(SimEngine.standardError(0.5, 0), null);
});

test('meta reports engine version, n, and seed', () => {
  const m = SimEngine.meta(10000, 42);
  assert.strictEqual(m.n, 10000);
  assert.strictEqual(m.seed, 42);
  assert.strictEqual(m.engine_version, SimEngine.ENGINE_VERSION);
});

test('meta reports seed as null when not provided', () => {
  const m = SimEngine.meta(10000);
  assert.strictEqual(m.seed, null);
});

test('replayMlsConferenceTargets reconstructs published targets for a small synthetic league', () => {
  // 4 teams, 2 per conference, no remaining fixtures (isolates the seeding/
  // ranking logic from the sampling logic, which simulateTrialPoints already
  // covers above).
  const snapshot = {
    replay_seed: 42,
    rules: { playoff_slots: 1, hfa_slots: 1 },
    teams: [
      { team_id: 'A', conf: 'East', pts: 30, gd: 10 },
      { team_id: 'B', conf: 'East', pts: 10, gd: -10 },
      { team_id: 'C', conf: 'West', pts: 25, gd: 5 },
      { team_id: 'D', conf: 'West', pts: 5, gd: -5 },
    ],
    fixtures: [],
  };
  const out = SimEngine.replayMlsConferenceTargets(snapshot, 500);
  const byId = Object.fromEntries(out.map(r => [r.team_id, r]));
  // No remaining fixtures → points are fixed → the ranking is deterministic
  // every trial: A always leads East, C always leads West.
  assert.strictEqual(byId['A'].playoff, 100);
  assert.strictEqual(byId['A'].conf_win, 100);
  assert.strictEqual(byId['B'].playoff, 0);
  assert.strictEqual(byId['C'].playoff, 100);
  assert.strictEqual(byId['D'].playoff, 0);
  // Shield/spoon are global (best/worst key across both conferences) — A
  // (30 pts) beats C (25 pts) for Shield; D (5 pts) is worst for Spoon.
  assert.strictEqual(byId['A'].shield, 100);
  assert.strictEqual(byId['D'].spoon, 100);
});

test('replayMlsConferenceTargets is deterministic given the same replay_seed', () => {
  const snapshot = {
    replay_seed: 7,
    rules: { playoff_slots: 1, hfa_slots: 1 },
    teams: [
      { team_id: 'A', conf: 'East', pts: 20, gd: 2 },
      { team_id: 'B', conf: 'East', pts: 18, gd: 1 },
      { team_id: 'C', conf: 'West', pts: 19, gd: 0 },
      { team_id: 'D', conf: 'West', pts: 17, gd: -1 },
    ],
    fixtures: [
      { home_id: 'A', away_id: 'B', pH: 0.4, pD: 0.3 },
      { home_id: 'C', away_id: 'D', pH: 0.5, pD: 0.2 },
    ],
  };
  const r1 = SimEngine.replayMlsConferenceTargets(snapshot, 200);
  const r2 = SimEngine.replayMlsConferenceTargets(snapshot, 200);
  assert.deepStrictEqual(r1, r2);
});

if (process.exitCode !== 1) console.log('\nAll sim-engine.js tests passed.');
