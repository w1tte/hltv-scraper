-- Migration 007: Simplify for CS2-only (Rating 3.0 always present)
-- Merge rating_2/rating_3 into single "rating" column, drop "impact" (Rating 2.0 only).
-- round_swing and mk_rating are now always expected (no longer "3.0 only").

-- SQLite doesn't support DROP COLUMN pre-3.35 or RENAME COLUMN merges cleanly,
-- so we recreate the table. Copy data, preferring rating_3 over rating_2.

CREATE TABLE player_stats_new (
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
    PRIMARY KEY (match_id, map_number, player_id),
    FOREIGN KEY (match_id) REFERENCES matches(match_id),
    FOREIGN KEY (match_id, map_number) REFERENCES maps(match_id, map_number)
);

INSERT INTO player_stats_new
SELECT
    match_id, map_number, player_id, player_name, team_id,
    kills, deaths, assists, flash_assists, hs_kills, kd_diff,
    adr, kast, fk_diff,
    COALESCE(rating_3, rating_2) AS rating,
    kpr, dpr,
    opening_kills, opening_deaths, multi_kills, clutch_wins,
    traded_deaths, round_swing, mk_rating,
    scraped_at, updated_at, source_url, parser_version
FROM player_stats;

DROP TABLE player_stats;
ALTER TABLE player_stats_new RENAME TO player_stats;

-- Recreate indexes
CREATE INDEX IF NOT EXISTS idx_player_stats_player ON player_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_team ON player_stats(team_id);
