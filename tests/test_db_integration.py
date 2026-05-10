import os

import pandas as pd
import pytest


@pytest.mark.skipif(
    os.environ.get("MLS_RUN_PG_TESTS") != "1",
    reason="Set MLS_RUN_PG_TESTS=1 with PG_* env vars to run PostgreSQL integration tests.",
)
def test_schema_initialization_and_team_registry_upsert():
    pytest.importorskip("psycopg2")
    from data_pipeline import db_utils

    db_utils.initialize_schema()
    row = pd.DataFrame([{
        "team_id": "TST",
        "name": "Test Club",
        "short_name": "TST",
        "conference": "E",
        "first_season": 2026,
        "stadium_lat": 0.0,
        "stadium_lon": 0.0,
        "stadium_name": "Test Stadium",
        "active": True,
    }])

    assert db_utils.upsert_dataframe(row, "team_registry", ["team_id"]) == 1
    fetched = db_utils.query("SELECT name FROM team_registry WHERE team_id = %s", ["TST"])
    assert fetched.iloc[0]["name"] == "Test Club"
