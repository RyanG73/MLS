"""Node-based characterization tests for webapp/sim-engine.js (S2).

No npm/jest dependency — webapp/sim-engine.test.js uses only Node's built-in
`assert` module and CommonJS require(), matching this repo's "no JS build
tooling" convention (there is no package.json anywhere in the repo). This
thin wrapper keeps `pytest tests/` the single CI entrypoint instead of
adding a second test runner to every workflow.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_sim_engine_js_characterization_suite():
    result = subprocess.run(
        ["node", str(REPO_ROOT / "webapp" / "sim-engine.test.js")],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        "sim-engine.js characterization tests failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
