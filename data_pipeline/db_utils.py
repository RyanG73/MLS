"""PostgreSQL helpers — schema management and read/write utilities."""

import os
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import pandas as pd

from config import SETTINGS

logger = logging.getLogger(__name__)

_DB_CFG = SETTINGS["database"]


def _conn_params() -> dict:
    """Build connection params, allowing env-var overrides."""
    return {
        "host":     os.environ.get("PG_HOST",     _DB_CFG["host"]),
        "port":     int(os.environ.get("PG_PORT", _DB_CFG["port"])),
        "dbname":   os.environ.get("PG_DBNAME",   _DB_CFG["name"]),
        "user":     os.environ.get("PG_USER",      _DB_CFG["user"]),
        "password": os.environ.get("PG_PASSWORD",  _DB_CFG.get("password", "")),
        "connect_timeout": int(os.environ.get("PGCONNECT_TIMEOUT", "10")),
    }


@contextmanager
def get_connection():
    """Context manager that yields a psycopg2 connection and commits on exit."""
    conn = psycopg2.connect(**_conn_params())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_schema() -> None:
    """Create all tables if they don't exist. Safe to run on every startup."""
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS matches (
            match_id          VARCHAR(20)  PRIMARY KEY,
            date              DATE         NOT NULL,
            season            INTEGER      NOT NULL,
            home_team         VARCHAR(10)  NOT NULL,
            away_team         VARCHAR(10)  NOT NULL,
            home_goals        INTEGER,
            away_goals        INTEGER,
            home_xg           DOUBLE PRECISION,
            away_xg           DOUBLE PRECISION,
            conference_h      VARCHAR(2),
            conference_a      VARCHAR(2),
            is_playoff        BOOLEAN      DEFAULT FALSE,
            referee_id        VARCHAR(40),
            status            VARCHAR(20)  DEFAULT 'scheduled',
            source            VARCHAR(20),
            competition       VARCHAR(20)  DEFAULT 'mls',
            kickoff_time      TIMESTAMP,
            weather_temp_c    DOUBLE PRECISION,
            weather_wind_kph  DOUBLE PRECISION,
            weather_precip_mm DOUBLE PRECISION,
            weather_humidity  DOUBLE PRECISION,
            pitch_surface     VARCHAR(10),
            is_post_fifa_break BOOLEAN     DEFAULT FALSE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_features (
            match_id                  VARCHAR(20)  NOT NULL,
            team_id                   VARCHAR(10)  NOT NULL,
            role                      VARCHAR(5)   NOT NULL,
            elo_pre                   DOUBLE PRECISION,
            xg_rolling_5              DOUBLE PRECISION,
            xg_rolling_10             DOUBLE PRECISION,
            xg_rolling_20             DOUBLE PRECISION,
            xga_rolling_5             DOUBLE PRECISION,
            xga_rolling_10            DOUBLE PRECISION,
            xga_rolling_20            DOUBLE PRECISION,
            xgd_rolling_10            DOUBLE PRECISION,
            xg_setpiece_rolling_10    DOUBLE PRECISION,
            xg_openplay_rolling_10    DOUBLE PRECISION,
            xga_setpiece_rolling_10   DOUBLE PRECISION,
            ppda_rolling_10           DOUBLE PRECISION,
            possession_rolling_10     DOUBLE PRECISION,
            travel_km                 DOUBLE PRECISION,
            days_rest                 INTEGER,
            games_in_14d              INTEGER,
            form_pts_5                DOUBLE PRECISION,
            dp1_available             BOOLEAN DEFAULT TRUE,
            dp2_available             BOOLEAN DEFAULT TRUE,
            dp3_available             BOOLEAN DEFAULT TRUE,
            gk_starting_available     BOOLEAN DEFAULT TRUE,
            key_player_suspended      BOOLEAN DEFAULT FALSE,
            n_internationals_unavail  INTEGER DEFAULT 0,
            days_under_mgr            INTEGER,
            news_sentiment_7d         DOUBLE PRECISION,
            match_importance_score    DOUBLE PRECISION,
            supporter_shield_locked   BOOLEAN DEFAULT FALSE,
            is_expansion              BOOLEAN DEFAULT FALSE,
            conference                VARCHAR(2),
            PRIMARY KEY (match_id, team_id, role)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS elo_history (
            team_id     VARCHAR(10)  NOT NULL,
            date        DATE         NOT NULL,
            elo_rating  DOUBLE PRECISION NOT NULL,
            PRIMARY KEY (team_id, date)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS referee_stats (
            referee_id          VARCHAR(40)  PRIMARY KEY,
            name                VARCHAR(100) NOT NULL,
            card_rate_per90     DOUBLE PRECISION,
            penalty_rate_per90  DOUBLE PRECISION,
            home_win_rate       DOUBLE PRECISION,
            matches_officiated  INTEGER DEFAULT 0,
            last_updated        TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS predictions (
            prediction_id   VARCHAR(24)  PRIMARY KEY,
            match_id        VARCHAR(20)  NOT NULL,
            model           VARCHAR(20)  NOT NULL,
            model_version   VARCHAR(20),
            prob_home       DOUBLE PRECISION NOT NULL,
            prob_draw       DOUBLE PRECISION NOT NULL,
            prob_away       DOUBLE PRECISION NOT NULL,
            prob_over       DOUBLE PRECISION,
            prob_under      DOUBLE PRECISION,
            predicted_at    TIMESTAMP    DEFAULT NOW(),
            features_hash   VARCHAR(16),
            claude_rationale TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS odds (
            odds_id         VARCHAR(24)  PRIMARY KEY,
            match_id        VARCHAR(20)  NOT NULL,
            bookmaker       VARCHAR(30)  NOT NULL,
            market          VARCHAR(10)  NOT NULL,
            outcome         VARCHAR(10)  NOT NULL,
            snapshot_type   VARCHAR(10)  DEFAULT 'open',
            open_odds       DOUBLE PRECISION,
            close_odds      DOUBLE PRECISION,
            fetched_at      TIMESTAMP    DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS news_items (
            item_id                     VARCHAR(24)  PRIMARY KEY,
            published_at                TIMESTAMP,
            source                      VARCHAR(50),
            headline                    TEXT,
            url                         TEXT,
            teams_mentioned             TEXT,
            claude_summary              TEXT,
            estimated_impact_home_atk   DOUBLE PRECISION DEFAULT 0.0,
            estimated_impact_home_def   DOUBLE PRECISION DEFAULT 0.0,
            estimated_impact_away_atk   DOUBLE PRECISION DEFAULT 0.0,
            estimated_impact_away_def   DOUBLE PRECISION DEFAULT 0.0,
            impact_confidence           VARCHAR(10),
            confirmed_by_user           BOOLEAN DEFAULT FALSE,
            applied_to_match_id         VARCHAR(20),
            created_at                  TIMESTAMP    DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS overrides (
            override_id         VARCHAR(20)  PRIMARY KEY,
            match_id            VARCHAR(20)  NOT NULL,
            applied_at          TIMESTAMP    DEFAULT NOW(),
            description         TEXT,
            home_strength_adj   DOUBLE PRECISION DEFAULT 0.0,
            away_strength_adj   DOUBLE PRECISION DEFAULT 0.0,
            source              VARCHAR(20)  DEFAULT 'manual',
            news_item_id        VARCHAR(24)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS simulated_bets (
            bet_id          VARCHAR(24)  PRIMARY KEY,
            match_id        VARCHAR(20)  NOT NULL,
            market          VARCHAR(10)  NOT NULL,
            outcome_backed  VARCHAR(10)  NOT NULL,
            model_prob      DOUBLE PRECISION NOT NULL,
            market_prob     DOUBLE PRECISION NOT NULL,
            edge_pct        DOUBLE PRECISION NOT NULL,
            open_odds       DOUBLE PRECISION,
            close_odds      DOUBLE PRECISION,
            clv             DOUBLE PRECISION,
            stake_kelly25   DOUBLE PRECISION,
            stake_kelly50   DOUBLE PRECISION,
            result          VARCHAR(10),
            pnl_kelly25     DOUBLE PRECISION,
            pnl_kelly50     DOUBLE PRECISION,
            placed_at       TIMESTAMP    DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_registry (
            team_id         VARCHAR(10)  PRIMARY KEY,
            name            VARCHAR(60)  NOT NULL,
            short_name      VARCHAR(10),
            conference      VARCHAR(2),
            first_season    INTEGER,
            stadium_lat     DOUBLE PRECISION,
            stadium_lon     DOUBLE PRECISION,
            stadium_name    VARCHAR(80),
            active          BOOLEAN DEFAULT TRUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS manager_history (
            team_id    VARCHAR(10)  NOT NULL,
            manager    VARCHAR(80)  NOT NULL,
            start_date DATE         NOT NULL,
            end_date   DATE,
            PRIMARY KEY (team_id, start_date)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS card_log (
            match_id   VARCHAR(20)  NOT NULL,
            player     VARCHAR(80)  NOT NULL,
            team_id    VARCHAR(10),
            card_color VARCHAR(10)  NOT NULL,
            PRIMARY KEY (match_id, player, card_color)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS predicted_lineups (
            match_id     VARCHAR(20)  NOT NULL,
            team_id      VARCHAR(10)  NOT NULL,
            source       VARCHAR(30),
            scraped_at   TIMESTAMP    DEFAULT NOW(),
            predicted_xi TEXT,
            PRIMARY KEY (match_id, team_id, source)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS backtest_results (
            run_id          VARCHAR(20)  PRIMARY KEY,
            parameters      TEXT,
            brier_mean      DOUBLE PRECISION,
            log_loss        DOUBLE PRECISION,
            roi_kelly25     DOUBLE PRECISION,
            roi_kelly50     DOUBLE PRECISION,
            avg_clv         DOUBLE PRECISION,
            max_drawdown    DOUBLE PRECISION,
            n_bets          INTEGER,
            generated_at    TIMESTAMP    DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS real_bets (
            bet_id      VARCHAR(20)  PRIMARY KEY,
            match_id    VARCHAR(20)  NOT NULL,
            bookmaker   VARCHAR(30),
            market      VARCHAR(10),
            outcome     VARCHAR(10),
            stake       DOUBLE PRECISION,
            odds        DOUBLE PRECISION,
            result      VARCHAR(10),
            pnl         DOUBLE PRECISION,
            placed_at   TIMESTAMP    DEFAULT NOW(),
            notes       TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS season_simulations (
            run_id       VARCHAR(20)  PRIMARY KEY,
            season       INTEGER      NOT NULL,
            simulated_at TIMESTAMP    DEFAULT NOW(),
            results_json TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS system_state (
            key         VARCHAR(40)  PRIMARY KEY,
            value       TEXT,
            updated_at  TIMESTAMP    DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id          VARCHAR(36)  PRIMARY KEY,
            run_type        VARCHAR(30)  NOT NULL,
            status          VARCHAR(20)  NOT NULL,
            started_at      TIMESTAMP    NOT NULL,
            finished_at     TIMESTAMP,
            step_name       VARCHAR(120),
            message         TEXT,
            stats           TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS source_runs (
            source_run_id   VARCHAR(36)  PRIMARY KEY,
            source_name     VARCHAR(30)  NOT NULL,
            endpoint        VARCHAR(120),
            fetched_at      TIMESTAMP    NOT NULL,
            raw_count       INTEGER      DEFAULT 0,
            parsed_count    INTEGER      DEFAULT 0,
            matched_count   INTEGER      DEFAULT 0,
            unmatched_count INTEGER      DEFAULT 0,
            schema_hash     VARCHAR(16),
            null_rate_json  TEXT,
            success         BOOLEAN      DEFAULT TRUE,
            error_message   TEXT
        )
        """,
        "ALTER TABLE odds ADD COLUMN IF NOT EXISTS snapshot_type VARCHAR(10) DEFAULT 'open'",
        # Indexes for common query patterns
        "CREATE INDEX IF NOT EXISTS idx_matches_date ON matches (date)",
        "CREATE INDEX IF NOT EXISTS idx_matches_status ON matches (status)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_match ON predictions (match_id)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_model ON predictions (model)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_latest ON predictions (match_id, model, predicted_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_odds_lookup ON odds (match_id, bookmaker, market, outcome, snapshot_type)",
        "CREATE INDEX IF NOT EXISTS idx_elo_team ON elo_history (team_id, date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_bets_match ON simulated_bets (match_id)",
        "CREATE INDEX IF NOT EXISTS idx_news_confirmed ON news_items (confirmed_by_user)",
        "CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON pipeline_runs (started_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_source_runs_latest ON source_runs (source_name, fetched_at DESC)",
    ]

    with get_connection() as conn:
        with conn.cursor() as cur:
            for stmt in ddl_statements:
                cur.execute(stmt)

    logger.info("PostgreSQL schema initialised.")


def upsert_dataframe(df: pd.DataFrame, table: str, primary_keys: list[str]) -> int:
    """
    Insert rows, updating non-PK columns on primary key conflict.
    Returns the number of rows processed.
    """
    if df.empty:
        return 0

    # Serialise list/array columns to JSON strings for TEXT storage
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda v: str(v) if isinstance(v, (list, dict)) else v
            )

    cols = list(df.columns)
    update_cols = [c for c in cols if c not in primary_keys]

    placeholders = ", ".join(["%s"] * len(cols))
    col_list = ", ".join(cols)

    if update_cols:
        conflict_action = "DO UPDATE SET " + ", ".join(
            f"{c} = EXCLUDED.{c}" for c in update_cols
        )
    else:
        conflict_action = "DO NOTHING"

    pk_str = ", ".join(primary_keys)
    sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT ({pk_str}) {conflict_action}"
    )

    rows = [
        tuple(None if pd.isna(v) else v for v in row)
        for row in df.itertuples(index=False, name=None)
    ]

    with get_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows, page_size=500)

    return len(rows)


def query(sql: str, params: list | None = None) -> pd.DataFrame:
    """Execute a SELECT query and return results as a DataFrame."""
    with get_connection() as conn:
        return pd.read_sql(sql, conn, params=params)


def execute(sql: str, params: list | None = None) -> None:
    """Execute a non-SELECT statement (INSERT / UPDATE / DELETE)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or [])


def get_state(key: str, default: str | None = None) -> str | None:
    """Read a value from the system_state key-value table."""
    df = query("SELECT value FROM system_state WHERE key = %s", [key])
    return df["value"].iloc[0] if not df.empty else default


def set_state(key: str, value: str) -> None:
    """Upsert a value in system_state (e.g. betting_paused, last_optuna_run)."""
    execute(
        """
        INSERT INTO system_state (key, value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """,
        [key, str(value)],
    )


def start_pipeline_run(run_type: str) -> str:
    """Create a status row for an orchestrated pipeline run."""
    run_id = str(uuid.uuid4())
    execute(
        """
        INSERT INTO pipeline_runs (run_id, run_type, status, started_at)
        VALUES (%s, %s, %s, %s)
        """,
        [run_id, run_type, "running", datetime.now(timezone.utc).isoformat()],
    )
    return run_id


def update_pipeline_run(
    run_id: str,
    status: str,
    step_name: str | None = None,
    message: str | None = None,
    stats: str | None = None,
    finished: bool = False,
) -> None:
    """Update the latest status details for a pipeline run."""
    finished_at = datetime.now(timezone.utc).isoformat() if finished else None
    execute(
        """
        UPDATE pipeline_runs
        SET status = %s,
            step_name = COALESCE(%s, step_name),
            message = COALESCE(%s, message),
            stats = COALESCE(%s, stats),
            finished_at = COALESCE(%s, finished_at)
        WHERE run_id = %s
        """,
        [status, step_name, message, stats, finished_at, run_id],
    )
