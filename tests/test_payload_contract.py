"""
Contract tests for webapp/data/*.js generated payloads.

Guards against the known failure mode identified in the Codex review:
health fields producing NaN when preseason current-season rows are empty,
combined with json.dumps() silently serialising NaN as the JavaScript literal NaN.

Each test is parametrised over every .js file so failures name the offending file.
"""
import glob
import json
import math
import re
from pathlib import Path

import pytest

WEBAPP_DATA = Path(__file__).parent.parent / "webapp" / "data"
# logos.js is a global team→logo lookup (window.TEAM_LOGOS), not a league/power payload,
# so it is excluded from the league-payload contract.
_NON_PAYLOAD = {"logos.js", "ledger.js"}
JS_FILES = sorted(p for p in WEBAPP_DATA.glob("*.js") if p.name not in _NON_PAYLOAD)


def _load_payload(path: Path) -> tuple[str, object]:
    """Strip the JS assignment wrapper and parse as strict JSON.

    Returns (var_name, parsed_object). Raises ValueError if the file does
    not match the expected pattern. Raises json.JSONDecodeError if the
    payload contains non-JSON tokens like NaN or Infinity.
    """
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^window\.(\w+) = (.*?);?\s*$", raw, re.DOTALL)
    if not m:
        raise ValueError(f"{path.name}: does not match 'window.VAR = ...;' pattern")
    var_name, json_body = m.group(1), m.group(2)
    data = json.loads(json_body)
    return var_name, data


def _collect_non_finite(obj, path="root") -> list[str]:
    """Recursively find all float values that are NaN or Inf."""
    issues = []
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            issues.append(f"{path} = {obj}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            issues.extend(_collect_non_finite(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            issues.extend(_collect_non_finite(v, f"{path}[{i}]"))
    return issues


@pytest.fixture(params=JS_FILES, ids=[p.name for p in JS_FILES])
def payload(request):
    """Load and parse one webapp/data/*.js file per test run."""
    path: Path = request.param
    var_name, data = _load_payload(path)
    return path, var_name, data


# ── Parse and structure ───────────────────────────────────────────────────────

class TestPayloadParseable:
    """Every .js file must parse as valid JSON after stripping the assignment."""

    def test_parses_as_json(self, payload):
        """File must round-trip through json.loads without error.

        Python's json.loads raises JSONDecodeError on literal NaN/Infinity
        tokens, so this is also the first-line guard against non-finite values
        introduced by json.dumps() without allow_nan=False.
        """
        path, var_name, data = payload
        assert data is not None, f"{path.name}: parsed to None"

    def test_var_name_is_known(self, payload):
        """Variable name must be one of the two expected globals."""
        _, var_name, _ = payload
        assert var_name in ("LEAGUE_DATA", "POWER_DATA"), (
            f"Unexpected JS variable name '{var_name}'"
        )


# ── Non-finite value guard ────────────────────────────────────────────────────

class TestNoNonFiniteValues:
    """No payload may contain NaN, Infinity, or -Infinity as Python floats.

    Note: if a payload contains the *literal* NaN token, TestPayloadParseable
    catches it first at the JSON parse stage. This class catches cases where
    a builder converts NaN to null or 0 correctly but then some other code
    path inserts a Python float NaN into the structure before serialisation.
    """

    def test_no_nan_or_infinity(self, payload):
        path, _, data = payload
        issues = _collect_non_finite(data)
        assert not issues, (
            f"{path.name} contains non-finite values:\n"
            + "\n".join(f"  {i}" for i in issues[:20])
        )


# ── LEAGUE_DATA required structure ───────────────────────────────────────────

_LEAGUE_FILES = [p for p in JS_FILES if p.name != "power.js"]


class TestLeaguePayloadRequiredFields:
    """LEAGUE_DATA payloads must have the minimum required structure."""

    @pytest.fixture(params=_LEAGUE_FILES, ids=[p.name for p in _LEAGUE_FILES])
    def league_payload(self, request):
        path = request.param
        var_name, data = _load_payload(path)
        if var_name != "LEAGUE_DATA":
            pytest.skip(f"{path.name} is not a LEAGUE_DATA payload (var={var_name})")
        return path, data

    def test_has_league_block(self, league_payload):
        path, data = league_payload
        assert "league" in data, f"{path.name}: missing top-level 'league' key"

    def test_has_league_id_for_non_knockout(self, league_payload):
        """Knockout payloads omit league.id by design; all others must have it."""
        path, data = league_payload
        mode = (data.get("outlook") or {}).get("mode")
        if mode == "knockout":
            pytest.skip(f"{path.name}: knockout payloads do not carry league.id")
        assert data["league"].get("id"), f"{path.name}: league.id is empty or missing"

    def test_has_top_level_status(self, payload):
        """Every payload must carry the top-level route `status` (B1).

        The route-state taxonomy (docs/CURRENT_STATE.md) defines it for league,
        continental, and power surfaces alike; the validator enforces the same.
        """
        path, var_name, data = payload
        assert isinstance(data, dict) and data.get("status"), (
            f"{path.name}: missing top-level 'status'")

    def test_has_generated_for_non_placeholder(self, league_payload):
        """Every non-placeholder surface must carry a generated timestamp."""
        path, data = league_payload
        status = (data.get("league") or {}).get("status") or data.get("status")
        if status in ("soon", "placeholder"):
            pytest.skip(f"{path.name}: placeholder payload, 'generated' not required")
        assert "generated" in data, (
            f"{path.name}: non-placeholder payload missing 'generated' timestamp"
        )

    def test_health_percentages_are_finite(self, league_payload):
        """Health completeness/nondefault values must be finite, not NaN.

        This is the specific pre-condition that caused NaN% in the health tab:
        mean() of an empty preseason frame produces NaN, which then leaks
        into the payload if not guarded at write time.
        """
        path, data = league_payload
        health = data.get("health") or {}
        features = health.get("features") or {}
        for family, fdata in (features.items() if isinstance(features, dict) else []):
            for metric in ("completeness", "nondefault"):
                val = fdata.get(metric) if isinstance(fdata, dict) else None
                if val is None:
                    continue
                assert isinstance(val, (int, float)), (
                    f"{path.name}: health.features.{family}.{metric} "
                    f"is not numeric: {val!r}"
                )
                assert math.isfinite(val), (
                    f"{path.name}: health.features.{family}.{metric} "
                    f"is non-finite: {val}"
                )


# ── POWER_DATA required structure ─────────────────────────────────────────────

class TestPowerPayload:
    """POWER_DATA payload must have the minimum required structure."""

    def test_power_has_groups(self):
        path = WEBAPP_DATA / "power.js"
        var_name, data = _load_payload(path)
        assert var_name == "POWER_DATA"
        assert "groups" in data, "power.js: missing 'groups' key"
        assert isinstance(data["groups"], list), "power.js: 'groups' must be a list"
        assert len(data["groups"]) > 0, "power.js: 'groups' is empty"
