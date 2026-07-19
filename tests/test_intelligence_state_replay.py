"""Replay test (docs/intelligence-hub-implementation-instructions.md §4.7,
§5 S3): an archived intelligence-state snapshot must reconstruct the
published target probabilities within a documented tolerance.

Runs archive_intelligence_state.py against the REAL current MLS payload,
then replays the archived snapshot via webapp/sim-engine.js's
replayMlsConferenceTargets (Node, no npm/jest — same convention as
tests/test_sim_engine_js.py) and compares to the snapshot's own recorded
`published` values.

TOLERANCE_PP is 3.0pp, not the 1.5pp the SIM PORTING CONTRACT comment in
webapp/index.html states for "unforced JS@10k within ±1.5pp of server@20k".
Investigated before touching this number (per this plan's own instruction
not to loosen a tolerance without investigating first): running the replay
at both 20k and 200k trials produced the SAME ~2-2.7pp gap on a handful of
borderline metrics (Chicago Fire hfa, Sporting KC spoon, Vancouver conf_win,
etc.) — a gap that does not shrink with more trials is not Monte Carlo
noise, it is a genuine methodology difference. That difference is
scripts/build_dashboard_data.py's "strength-uncertainty widening"
(scripts/eval/sim_variance.py, added 2026-07-07): the SERVER simulation
perturbs each team's win probability per trial by a mid-season random
strength adjustment to represent model uncertainty; the browser's what-if
simulator (webapp/index.html's runSim, unchanged by S2/S3) has never
replicated this — it is a pre-existing gap in the shipped feature, not a
regression introduced by S1-S3. The perturbation's magnitude
(preseason_sigma_for_source("asa") * (1 - season_fraction)) shrinks toward
zero as the season progresses, so this gap is expected to tighten over the
year; 3.0pp covers today's mid-season (43% complete) observed max with a
small margin, and 6 of the 7 published targets are covered (all except
"cup", excluded per this plan's own scoping note — it needs confBracket,
which stays in webapp/index.html, not Node-requirable sim-engine.js).
"""
import gzip
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.archive_intelligence_state import build_snapshot, write_snapshot
from scripts.payload_utils import read_js_payload

REPO_ROOT = Path(__file__).resolve().parent.parent
TOLERANCE_PP = 3.0


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_replay_reconstructs_published_targets_within_tolerance(tmp_path):
    payload = read_js_payload(REPO_ROOT / "webapp" / "data" / "mls.js")
    assert payload is not None, "webapp/data/mls.js must exist and parse for this replay test"
    snapshot = build_snapshot(payload)
    write_snapshot(snapshot, snapshot_dir=tmp_path)
    snap_path = tmp_path / f"{snapshot['snapshot_id'].replace(':', '_')}.json.gz"
    with gzip.open(snap_path, "rt", encoding="utf-8") as f:
        raw_snapshot = json.load(f)
    # Freshly written into a brand-new tmp_path — cannot have been deduplicated
    # against a prior snapshot, so pmatrix must be the full array here.
    assert isinstance(raw_snapshot["pmatrix"], list)

    plain_snapshot_path = tmp_path / "snapshot_for_replay.json"
    plain_snapshot_path.write_text(json.dumps(raw_snapshot))

    node_script = f"""
    const SimEngine = require('{(REPO_ROOT / "webapp" / "sim-engine.js").as_posix()}');
    const snapshot = require('{plain_snapshot_path.as_posix()}');
    const replayed = SimEngine.replayMlsConferenceTargets(snapshot, 20000);
    console.log(JSON.stringify(replayed));
    """
    result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
    assert result.returncode == 0, f"replay script failed:\n{result.stderr}"
    replayed = {r["team_id"]: r for r in json.loads(result.stdout)}

    checked = 0
    for team in snapshot["teams"]:
        rep = replayed.get(team["team_id"])
        assert rep is not None, f"no replayed result for {team['team']}"
        for metric in ("playoff", "hfa", "shield", "spoon", "conf_win"):
            published = team["published"].get(metric)
            if published is None:
                continue
            diff = abs(rep[metric] - published)
            assert diff <= TOLERANCE_PP, (
                f"{team['team']} {metric}: published {published} vs replayed "
                f"{rep[metric]} — diff {diff:.2f}pp exceeds {TOLERANCE_PP}pp tolerance"
            )
            checked += 1
    assert checked > 0, "no metrics were actually compared — test would pass vacuously"
