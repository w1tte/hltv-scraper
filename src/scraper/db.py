"""PostgreSQL database connection manager with schema initialization.

Manages the connection lifecycle and applies the schema DDL on first run.
"""

import logging
import os

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# Default connection parameters (override via env vars or constructor)
DEFAULT_DSN = {
    "host": os.getenv("HLTV_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("HLTV_DB_PORT", "5433")),
    "dbname": os.getenv("HLTV_DB_NAME", "HLTV-Historical-Data"),
    "user": os.getenv("HLTV_DB_USER", "hltv"),
    "password": os.getenv("HLTV_DB_PASSWORD", "hltv"),
}

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS matches (
    match_id      INTEGER PRIMARY KEY,
    date          TEXT,
    event_id      INTEGER,
    event_name    TEXT,
    team1_id      INTEGER,
    team1_name    TEXT,
    team2_id      INTEGER,
    team2_name    TEXT,
    team1_score   INTEGER,
    team2_score   INTEGER,
    best_of       INTEGER,
    is_lan        INTEGER,
    match_url     TEXT,
    scraped_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    source_url    TEXT,
    parser_version TEXT,
    date_unix_ms  BIGINT
);

CREATE TABLE IF NOT EXISTS maps (
    match_id        INTEGER NOT NULL REFERENCES matches(match_id),
    map_number      INTEGER NOT NULL,
    mapstatsid      INTEGER,
    map_name        TEXT,
    team1_rounds    INTEGER,
    team2_rounds    INTEGER,
    team1_ct_rounds INTEGER,
    team1_t_rounds  INTEGER,
    team2_ct_rounds INTEGER,
    team2_t_rounds  INTEGER,
    scraped_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    source_url      TEXT,
    parser_version  TEXT,
    perf_attempts   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (match_id, map_number)
);

CREATE TABLE IF NOT EXISTS player_stats (
    match_id       INTEGER NOT NULL,
    map_number     INTEGER NOT NULL,
    player_id      INTEGER NOT NULL,
    player_name    TEXT,
    team_id        INTEGER,
    kills          INTEGER,
    deaths         INTEGER,
    assists        INTEGER,
    flash_assists  INTEGER,
    hs_kills       INTEGER,
    kd_diff        INTEGER,
    adr            REAL,
    kast           REAL,
    fk_diff        INTEGER,
    rating         REAL,
    kpr            REAL,
    dpr            REAL,
    opening_kills  INTEGER,
    opening_deaths INTEGER,
    multi_kills    INTEGER,
    clutch_wins    INTEGER,
    traded_deaths  INTEGER,
    round_swing    REAL,
    mk_rating      REAL,
    scraped_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL DEFAULT '',
    source_url     TEXT,
    parser_version TEXT,
    e_kills        INTEGER,
    e_deaths       INTEGER,
    e_hs_kills     INTEGER,
    e_kd_diff      INTEGER,
    e_adr          REAL,
    e_kast         REAL,
    e_opening_kills  INTEGER,
    e_opening_deaths INTEGER,
    e_fk_diff      INTEGER,
    e_traded_deaths  INTEGER,
    PRIMARY KEY (match_id, map_number, player_id),
    FOREIGN KEY (match_id) REFERENCES matches(match_id),
    FOREIGN KEY (match_id, map_number) REFERENCES maps(match_id, map_number)
);

CREATE TABLE IF NOT EXISTS round_history (
    match_id       INTEGER NOT NULL,
    map_number     INTEGER NOT NULL,
    round_number   INTEGER NOT NULL,
    winner_side    TEXT,
    win_type       TEXT,
    winner_team_id INTEGER,
    scraped_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    source_url     TEXT,
    parser_version TEXT,
    PRIMARY KEY (match_id, map_number, round_number),
    FOREIGN KEY (match_id, map_number) REFERENCES maps(match_id, map_number)
);

CREATE TABLE IF NOT EXISTS economy (
    match_id        INTEGER NOT NULL,
    map_number      INTEGER NOT NULL,
    round_number    INTEGER NOT NULL,
    team_id         INTEGER NOT NULL,
    equipment_value INTEGER,
    buy_type        TEXT,
    scraped_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    source_url      TEXT,
    parser_version  TEXT,
    PRIMARY KEY (match_id, map_number, round_number, team_id),
    FOREIGN KEY (match_id, map_number, round_number)
        REFERENCES round_history(match_id, map_number, round_number)
);

CREATE TABLE IF NOT EXISTS kill_matrix (
    match_id       INTEGER NOT NULL,
    map_number     INTEGER NOT NULL,
    matrix_type    TEXT NOT NULL,
    player1_id     INTEGER NOT NULL,
    player2_id     INTEGER NOT NULL,
    player1_kills  INTEGER NOT NULL,
    player2_kills  INTEGER NOT NULL,
    scraped_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    source_url     TEXT,
    parser_version TEXT,
    PRIMARY KEY (match_id, map_number, matrix_type, player1_id, player2_id),
    FOREIGN KEY (match_id, map_number) REFERENCES maps(match_id, map_number)
);

CREATE TABLE IF NOT EXISTS vetoes (
    match_id       INTEGER NOT NULL REFERENCES matches(match_id),
    step_number    INTEGER NOT NULL,
    team_name      TEXT,
    action         TEXT NOT NULL,
    map_name       TEXT NOT NULL,
    scraped_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    source_url     TEXT,
    parser_version TEXT,
    PRIMARY KEY (match_id, step_number)
);

CREATE TABLE IF NOT EXISTS quarantine (
    id              SERIAL PRIMARY KEY,
    entity_type     TEXT NOT NULL,
    match_id        INTEGER,
    map_number      INTEGER,
    raw_data        TEXT NOT NULL,
    error_details   TEXT NOT NULL,
    quarantined_at  TEXT NOT NULL,
    resolved        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scrape_queue (
    match_id      INTEGER PRIMARY KEY,
    url           TEXT NOT NULL,
    "offset"      INTEGER NOT NULL,
    discovered_at TEXT NOT NULL,
    is_forfeit    INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'pending',
    started_at    TEXT
);

CREATE TABLE IF NOT EXISTS discovery_progress (
    "offset"     INTEGER PRIMARY KEY,
    completed_at TEXT NOT NULL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_event ON matches(event_id);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(team1_id, team2_id);
CREATE INDEX IF NOT EXISTS idx_maps_mapstatsid ON maps(mapstatsid);
CREATE INDEX IF NOT EXISTS idx_player_stats_player ON player_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_team ON player_stats(team_id);
CREATE INDEX IF NOT EXISTS idx_kill_matrix_players ON kill_matrix(player1_id, player2_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_match ON quarantine(match_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_resolved ON quarantine(resolved);
CREATE INDEX IF NOT EXISTS idx_quarantine_type ON quarantine(entity_type);
CREATE INDEX IF NOT EXISTS idx_scrape_queue_offset ON scrape_queue("offset");
CREATE INDEX IF NOT EXISTS idx_scrape_queue_status ON scrape_queue(status);

CREATE TABLE IF NOT EXISTS scraper_logs (
    id          SERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    level       TEXT NOT NULL,
    logger      TEXT,
    message     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scraper_logs_ts ON scraper_logs(ts DESC);
"""


class Database:
    """PostgreSQL connection manager.

    Usage::

        db = Database()
        db.initialize()  # connect + create schema
        # ... use db.conn ...
        db.close()
    """

    def __init__(self, dsn: dict | None = None, **kwargs) -> None:
        self.dsn = {**DEFAULT_DSN, **(dsn or {}), **kwargs}
        self._conn = None

    def connect(self):
        """Open connection to PostgreSQL."""
        self._conn = psycopg2.connect(**self.dsn)
        self._conn.autocommit = False
        return self._conn

    @property
    def conn(self):
        """Return the active connection or raise if not connected."""
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def initialize(self):
        """Connect and create schema if needed."""
        self.connect()
        with self._conn:
            with self._conn.cursor() as cur:
                cur.execute(SCHEMA_DDL)
        logger.info("Database schema initialized")
        return self._conn
