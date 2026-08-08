"""No dict literal in the payload builders may define a key twice.

Python keeps the LAST duplicate silently, so a collision does not raise — it
just discards one contributor's value. On 2026-08-08 the Stage-0 routing
provenance was added to `data` as "provenance" while the model provenance
block, 70 lines further down the same literal, already used that key: the
routing provenance never reached a single payload, and the spec's invariant 5
("provenance is published, per column family") was false for a whole day while
being reported as shipped.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

BUILDERS = ["scripts/build_league_data.py", "scripts/build_dashboard_data.py"]


@pytest.mark.parametrize("path", BUILDERS)
def test_no_duplicate_keys_in_dict_literals(path):
    tree = ast.parse(Path(path).read_text())
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = [k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes:
            offenders.append((node.lineno, sorted(dupes)))
    assert offenders == [], (
        f"{path}: dict literals with duplicate keys (the later value wins "
        f"and the earlier is silently discarded): {offenders}")
