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
# Cross-league data files (logos, drift, edge-board, model-slices, …) are not
# league/power payloads. The exclusion list lives in one place — the production
# validator — so it can't drift out of sync with the tests again.
from scripts.validate_payloads import _NON_PAYLOAD
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

    def test_no_club_is_ranked_twice(self):
        """A club appears once, and a shared NAME is disambiguated by country.

        Nine names were duplicated before 2026-08-07, and they were two problems
        with one symptom. Seven were a single club listed in two divisions at
        once — Athletico-PR, Coritiba, Remo and Chapecoense were promoted out of
        Brazil's Série B in 2025, and that payload still describes the completed
        2025 season, which is right for the Série B page and wrong for a global
        ladder. Two were genuinely different clubs sharing a name.

        Since 2026-08-07 the BEST-RANKED club of a shared name renders bare and
        only the others carry their country, so `display` is no longer the thing
        to assert on. What still has to hold — and is what actually catches a
        club listed twice — is that every row of a shared name carries a
        `country` and that those countries are all different. One club in two
        divisions has the SAME country twice and fails here.
        """
        path = WEBAPP_DATA / "power.js"
        _, data = _load_payload(path)
        seen = {}
        for row in data["teams"]:
            seen.setdefault(row["team"], []).append(row)
        for name, group in seen.items():
            if len(group) == 1:
                continue
            countries = [r.get("country") for r in group]
            assert all(countries), (
                f"power.js: {len(group)} rows named {name!r} and at least one "
                f"carries no `country` — either it is one club listed twice, or "
                f"the disambiguation is missing: "
                f"{[(r['league'], r['global_rank']) for r in group]}")
            assert len(set(countries)) == len(group), (
                f"power.js: {name!r} appears {len(group)} times but resolves to "
                f"only {len(set(countries))} countries {sorted(set(countries))} — "
                f"that is one club listed twice, not two namesakes: "
                f"{[(r['league'], r['global_rank']) for r in group]}")
            # Exactly one renders bare, and it is the best-ranked of the group:
            # "everyone knows the big liverpool" (2026-08-07).
            bare = [r for r in group if not r.get("display")]
            assert len(bare) == 1, (
                f"power.js: {name!r} has {len(bare)} untagged rows, expected 1: "
                f"{[(r['league'], r.get('display')) for r in group]}")
            assert bare[0]["global_rank"] == min(r["global_rank"] for r in group), (
                f"power.js: the untagged {name!r} is rank "
                f"{bare[0]['global_rank']}, but rank "
                f"{min(r['global_rank'] for r in group)} shares the name and is "
                f"the one a reader means")

    def test_global_ranks_are_dense_and_unique(self):
        path = WEBAPP_DATA / "power.js"
        _, data = _load_payload(path)
        ranks = [r["global_rank"] for r in data["teams"]]
        assert ranks == list(range(1, len(ranks) + 1)), (
            "power.js: global_rank must be 1..n with no gaps or repeats — "
            "dropping a duplicate row without renumbering leaves a hole")

    def test_power_has_groups(self):
        path = WEBAPP_DATA / "power.js"
        var_name, data = _load_payload(path)
        assert var_name == "POWER_DATA"
        assert "groups" in data, "power.js: missing 'groups' key"
        assert isinstance(data["groups"], list), "power.js: 'groups' must be a list"
        assert len(data["groups"]) > 0, "power.js: 'groups' is empty"

    def test_power_is_one_continuous_global_ladder(self):
        _, data = _load_payload(WEBAPP_DATA / "power.js")
        teams = data["teams"]
        assert teams, "power.js: 'teams' is empty"
        assert [row["global_rank"] for row in teams] == list(range(1, len(teams) + 1))
        assert [row["strength"] for row in teams] == sorted(
            (row["strength"] for row in teams), reverse=True)
        assert len({row["league"] for row in teams}) == len(data["leagues"])


class TestGlobalEloPayload:
    """Domestic payloads expose one reconciled published-rating contract."""

    @pytest.fixture(params=_LEAGUE_FILES, ids=[p.name for p in _LEAGUE_FILES])
    def domestic_payload(self, request):
        path = request.param
        var_name, data = _load_payload(path)
        domestic_mode = data.get("outlook", {}).get("mode") in {"table", "mls"}
        if var_name != "LEAGUE_DATA" or not domestic_mode or not data.get("standings"):
            pytest.skip(f"{path.name} has no domestic standings")
        return path, data

    def test_one_team_id_yields_one_standings_row(self, domestic_payload):
        """A club must appear once. canonical_team_id is name-derived, so two
        source entries whose display names canonicalise the same emit two rows
        for one club — putting a club that does not exist on the global ladder
        and linking it twice on the league page.

        Regression: austria-bundesliga carried 15 rows for 13 team_ids on
        2026-08-04 (Rapid Vienna and Austria Vienna each twice, the second a
        zero-game placeholder at the default seed).
        """
        path, data = domestic_payload
        seen = {}
        for row in data["standings"]:
            seen.setdefault(row["team_id"], []).append(row.get("team"))
        dupes = {k: v for k, v in seen.items() if len(v) > 1}
        assert not dupes, (
            f"{path.name}: {len(dupes)} team_id(s) appear on more than one "
            f"standings row: {dupes}")

    def test_global_elo_reconciles_with_raw_rating(self, domestic_payload):
        """global_elo must be reproducible from elo and the published elo_scale.

        The translation was a pure shift until 2026-08-07 and is now shift plus
        a spread term for lower divisions, because a second tier's rating gaps
        overstate the favourite relative to its parent league's. `dispersion`
        and `pivot` are published alongside `offset` precisely so this stays
        checkable from the payload alone — a reader must never have to know a
        constant that only lives in the repository.
        """
        path, data = domestic_payload
        scale = data.get("elo_scale")
        assert scale, f"{path.name}: missing elo_scale"
        offset = scale["offset"]
        disp = scale.get("dispersion", 1.0)
        pivot = scale.get("pivot", 0.0)
        assert 0.5 <= disp <= 1.0, f"{path.name}: implausible dispersion {disp}"
        for row in data["standings"]:
            if isinstance(row.get("elo"), (int, float)):
                assert "global_elo" in row, f"{path.name}: {row['team']} missing global_elo"
                # global_elo_adj is this club's OWN continental record, published
                # on the row precisely so the total stays reproducible from the
                # payload rather than needing a file only the repo has.
                adj = row.get("global_elo_adj", 0.0)
                expected = pivot + disp * (row["elo"] - pivot) + offset + adj
                assert row["global_elo"] == pytest.approx(expected, abs=.51)

    def test_club_adjustments_are_bounded_and_only_on_played_clubs(self, domestic_payload):
        """A per-club adjustment must stay a correction, never a rewrite.

        It is shrunk toward zero by the evidence behind it (club_bridge), so a
        club with a handful of European matches should barely move. Anything
        past 150 ELO means the shrinkage is not doing its job.
        """
        path, data = domestic_payload
        for row in data["standings"]:
            adj = row.get("global_elo_adj")
            if adj is None:
                continue
            assert abs(adj) <= 150, (
                f"{path.name}: {row['team']} carries a {adj:+.0f} club adjustment")

    def test_only_lower_divisions_carry_a_spread_correction(self, domestic_payload):
        """A top flight must be translated by a shift alone.

        tier_dispersion composes along the promotion chain and returns 1.0 for
        anything that is not below a modelled top flight, so a dispersion other
        than 1.0 on a top-flight payload means the chain has picked up a hop it
        should not have.
        """
        from data_pipeline import coefficients as co
        path, data = domestic_payload
        lid = (data.get("league") or {}).get("id") or path.stem
        disp = (data.get("elo_scale") or {}).get("dispersion", 1.0)
        if lid not in co._TIER1_FOR:
            assert disp == pytest.approx(1.0), (
                f"{path.name}: {lid} is not a second tier but carries "
                f"dispersion {disp}")


# ── Public payload privacy contract ───────────────────────────────────────────

class TestPublicPayloadPrivacy:
    """Detailed model features must never be downloadable from the static site."""

    @pytest.fixture(params=_LEAGUE_FILES, ids=[p.name for p in _LEAGUE_FILES])
    def league_payload(self, request):
        path = request.param
        var_name, data = _load_payload(path)
        if var_name != "LEAGUE_DATA":
            pytest.skip(f"{path.name} is not a LEAGUE_DATA payload (var={var_name})")
        return path, data

    def test_league_payload_omits_model_inputs(self, league_payload):
        path, data = league_payload
        assert "team_inputs" not in data, f"{path.name}: public team_inputs leak"
        assert "team_inputs_full" not in data, f"{path.name}: public team_inputs_full leak"

    def test_home_fixtures_omit_model_inputs(self):
        path = WEBAPP_DATA / "home.js"
        _, data = _load_payload(path)
        leaked = [
            f for f in data.get("fixtures", [])
            if "hinp" in f or "ainp" in f
        ]
        assert not leaked, "home.js: fixture-level model inputs are public"


class TestMlsSeasonCompleteness:
    """The MLS payload must carry the complete 34-match regular season."""

    def test_every_team_has_34_fixtures_and_latest_crew_result(self):
        _, data = _load_payload(WEBAPP_DATA / "mls.js")
        counts: dict[str, int] = {}
        for game in data["games"]:
            counts[game["home"]] = counts.get(game["home"], 0) + 1
            counts[game["away"]] = counts.get(game["away"], 0) + 1

        assert len(counts) == 30
        assert set(counts.values()) == {34}
        assert data["played"] + data["upcoming"] == 510

        crew_nycfc = [
            game
            for game in data["games"]
            if game["date"] == "2026-07-22"
            and game["home"] == "Columbus Crew"
            and game["away"] == "New York City FC"
        ]
        assert len(crew_nycfc) == 1
        assert (crew_nycfc[0]["hg"], crew_nycfc[0]["ag"], crew_nycfc[0]["result"]) == (
            1,
            2,
            "A",
        )
