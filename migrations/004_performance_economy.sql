-- migrations/004_performance_economy.sql
-- Phase 7: Performance & Economy Extraction
--
-- 1. Add missing columns to player_stats (fields already extracted by Phase 6
--    parser but silently dropped because DB columns did not exist).
-- 2. Add mk_rating column for Phase 7 performance page data.
-- 3. Create kill_matrix table for head-to-head kill data.

-- Player stats columns already extracted by Phase 6 parser (map stats page)
ALTER TABLE player_stats ADD COLUMN opening_kills INTEGER;
ALTER TABLE player_stats ADD COLUMN opening_deaths INTEGER;
ALTER TABLE player_stats ADD COLUMN multi_kills INTEGER;
ALTER TABLE player_stats ADD COLUMN clutch_wins INTEGER;
ALTER TABLE player_stats ADD COLUMN traded_deaths INTEGER;
ALTER TABLE player_stats ADD COLUMN round_swing REAL;       -- Rating 3.0 only, nullable

-- Phase 7 performance page column
ALTER TABLE player_stats ADD COLUMN mk_rating REAL;         -- Rating 3.0 MK rating, nullable

-- Kill matrix: head-to-head kill counts between players on a map
CREATE TABLE IF NOT EXISTS kill_matrix (
    match_id      INTEGER NOT NULL,
    map_number    INTEGER NOT NULL,
    matrix_type   TEXT NOT NULL,          -- "all", "first_kill", "awp"
    player1_id    INTEGER NOT NULL,       -- Row player
    player2_id    INTEGER NOT NULL,       -- Column player
    player1_kills INTEGER NOT NULL,       -- Row player's kills against column player
    player2_kills INTEGER NOT NULL,       -- Column player's kills against row player
    scraped_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    source_url    TEXT,
    parser_version TEXT,
    PRIMARY KEY (match_id, map_number, matrix_type, player1_id, player2_id),
    FOREIGN KEY (match_id, map_number) REFERENCES maps(match_id, map_number)
);

CREATE INDEX IF NOT EXISTS idx_kill_matrix_players ON kill_matrix(player1_id, player2_id);
