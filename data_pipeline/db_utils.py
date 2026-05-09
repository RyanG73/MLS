"""DuckDB schema management and read/write helpers."""

import duckdb
import pandas as pd
from pathlib import Path
from config import SETTINGS


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    db_path = SETTINGS["data"]["db_path"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(db_path, read_only=read_only)


def initialize_schema() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    con = get_connection()
    con.executemany("PRAGMA journal_mode=WAL", [])

    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS matches (
            match_id        VARCHAR PRIMARY KEY,
            date            DATE NOT NULL,
            season          INTEGER NOT NULL,
            home_team       VARCHAR NOT NULL,
            away_team       VARCHAR NOT NULL,
            home_goals      INTEGER,
            away_goals      INTEGER,
            home_xg         DOUBLE,
            away_xg         DOUBLE,
            conference_h    VARCHAR,
            conference_a    VARCHAR,
            is_playoff      BOOLEAN DEFAULT FALSE,
            referee_id      VARCHAR,
            status          VARCHAR DEFAULT 'scheduled',
            source          VARCHAR
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_features (
            match_id                VARCHAR NOT NULL,
            team_id                 VARCHAR NOT NULL,
            role                    VARCHAR NOT NULL,
            elo_pre                 DOUBLE,
            xg_rolling_5            DOUBLE,
            xg_rolling_10           DOUBLE,
            xg_rolling_20           DOUBLE,
            xga_rolling_5           DOUBLE,
            xga_rolling_10          DOUBLE,
            xga_rolling_20          DOUBLE,
            xgd_rolling_10          DOUBLE,
            travel_km               DOUBLE,
            days_rest               INTEGER,
            games_in_14d            INTEGER,
            form_pts_5              DOUBLE,
            dp1_available           BOOLEAN DEFAULT TRUE,
            dp2_available           BOOLEAN DEFAULT TRUE,
            dp3_available           BOOLEAN DEFAULT TRUE,
            supporter_shield_locked BOOLEAN DEFAULT FALSE,
            is_expansion            BOOLEAN DEFAULT FALSE,
            conference              VARCHAR,
            PRIMARY KEY (match_id, team_id, role)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS elo_history (
            team_id     VARCHAR NOT NULL,
            date        DATE NOT NULL,
            elo_rating  DOUBLE NOT NULL,
            PRIMARY KEY (team_id, date)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS referee_stats (
            referee_id          VARCHAR PRIMARY KEY,
            name                VARCHAR NOT NULL,
            card_rate_per90     DOUBLE,
            penalty_rate_per90  DOUBLE,
            home_win_rate       DOUBLE,
            matches_officiated  INTEGER DEFAULT 0,
            last_updated        TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS predictions (
            prediction_id   VARCHAR PRIMARY KEY,
            match_id        VARCHAR NOT NULL,
            model           VARCHAR NOT NULL,
            prob_home       DOUBLE NOT NULL,
            prob_draw       DOUBLE NOT NULL,
            prob_away       DOUBLE NOT NULL,
            prob_over       DOUBLE,
            prob_under      DOUBLE,
            predicted_at    TIMESTAMP DEFAULT current_timestamp,
            features_hash   VARCHAR
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS odds (
            odds_id         VARCHAR PRIMARY KEY,
            match_id        VARCHAR NOT NULL,
            bookmaker       VARCHAR NOT NULL,
            market          VARCHAR NOT NULL,
            outcome         VARCHAR NOT NULL,
            open_odds       DOUBLE,
            close_odds      DOUBLE,
            fetched_at      TIMESTAMP DEFAULT current_timestamp
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS news_items (
            item_id                     VARCHAR PRIMARY KEY,
            published_at                TIMESTAMP,
            source                      VARCHAR,
            headline                    VARCHAR,
            url                         VARCHAR,
            teams_mentioned             VARCHAR[],
            claude_summary              TEXT,
            estimated_impact_home_atk   DOUBLE DEFAULT 0.0,
            estimated_impact_home_def   DOUBLE DEFAULT 0.0,
            estimated_impact_away_atk   DOUBLE DEFAULT 0.0,
            estimated_impact_away_def   DOUBLE DEFAULT 0.0,
            impact_confidence           VARCHAR,
            confirmed_by_user           BOOLEAN DEFAULT FALSE,
            applied_to_match_id         VARCHAR,
            created_at                  TIMESTAMP DEFAULT current_timestamp
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS overrides (
            override_id         VARCHAR PRIMARY KEY,
            match_id            VARCHAR NOT NULL,
            applied_at          TIMESTAMP DEFAULT current_timestamp,
            description         TEXT,
            home_strength_adj   DOUBLE DEFAULT 0.0,
            away_strength_adj   DOUBLE DEFAULT 0.0,
            source              VARCHAR DEFAULT 'manual',
            news_item_id        VARCHAR
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS simulated_bets (
            bet_id          VARCHAR PRIMARY KEY,
            match_id        VARCHAR NOT NULL,
            market          VARCHAR NOT NULL,
            outcome_backed  VARCHAR NOT NULL,
            model_prob      DOUBLE NOT NULL,
            market_prob     DOUBLE NOT NULL,
            edge_pct        DOUBLE NOT NULL,
            open_odds       DOUBLE,
            close_odds      DOUBLE,
            clv             DOUBLE,
            stake_kelly25   DOUBLE,
            stake_kelly50   DOUBLE,
            result          VARCHAR,
            pnl_kelly25     DOUBLE,
            pnl_kelly50     DOUBLE,
            placed_at       TIMESTAMP DEFAULT current_timestamp
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_registry (
            team_id         VARCHAR PRIMARY KEY,
            name            VARCHAR NOT NULL,
            short_name      VARCHAR,
            conference      VARCHAR,
            first_season    INTEGER,
            stadium_lat     DOUBLE,
            stadium_lon     DOUBLE,
            stadium_name    VARCHAR,
            active          BOOLEAN DEFAULT TRUE
        )
        """,
    ]

    for stmt in ddl_statements:
        con.execute(stmt)

    con.close()


def upsert_dataframe(df: pd.DataFrame, table: str, primary_keys: list[str]) -> int:
    """Insert rows, updating on primary key conflict. Returns row count."""
    if df.empty:
        return 0
    con = get_connection()
    tmp = f"_tmp_{table}"
    con.execute(f"CREATE OR REPLACE TEMP TABLE {tmp} AS SELECT * FROM df LIMIT 0")
    con.execute(f"INSERT INTO {tmp} SELECT * FROM df")
    pk_clause = " AND ".join(f"t.{k} = s.{k}" for k in primary_keys)
    update_cols = [c for c in df.columns if c not in primary_keys]
    set_clause = ", ".join(f"{c} = s.{c}" for c in update_cols)
    insert_cols = ", ".join(df.columns)
    insert_vals = ", ".join(f"s.{c}" for c in df.columns)
    con.execute(f"""
        INSERT INTO {table} ({insert_cols})
        SELECT {insert_vals} FROM {tmp} s
        WHERE NOT EXISTS (
            SELECT 1 FROM {table} t WHERE {pk_clause}
        )
    """)
    if update_cols:
        con.execute(f"""
            UPDATE {table} t
            SET {set_clause}
            FROM {tmp} s
            WHERE {pk_clause}
        """)
    count = len(df)
    con.close()
    return count


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    con = get_connection(read_only=True)
    result = con.execute(sql, params or []).df()
    con.close()
    return result


def execute(sql: str, params: list | None = None) -> None:
    con = get_connection()
    con.execute(sql, params or [])
    con.close()
