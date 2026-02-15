-- migrations/003_vetoes_rosters.sql
-- Phase 5: Match Overview Extraction - vetoes and match rosters
--
-- Tables: vetoes, match_players
-- vetoes tracks map veto sequences (remove/pick/left_over steps).
-- match_players tracks the 10 players (5 per team) in each match.
-- Both tables support UPSERT via ON CONFLICT on their composite PKs.

CREATE TABLE IF NOT EXISTS vetoes (
    match_id       INTEGER NOT NULL REFERENCES matches(match_id),
    step_number    INTEGER NOT NULL,       -- 1-7
    team_name      TEXT,                   -- Team performing action (NULL for "left over")
    action         TEXT NOT NULL,          -- "removed", "picked", "left_over"
    map_name       TEXT NOT NULL,          -- Map being acted upon
    scraped_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    source_url     TEXT,
    parser_version TEXT,
    PRIMARY KEY (match_id, step_number)
);

CREATE TABLE IF NOT EXISTS match_players (
    match_id       INTEGER NOT NULL REFERENCES matches(match_id),
    player_id      INTEGER NOT NULL,       -- HLTV player ID
    player_name    TEXT,                   -- Nickname at time of match
    team_id        INTEGER,               -- HLTV team ID
    team_num       INTEGER,               -- 1 or 2 (positional: team1 or team2)
    scraped_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    source_url     TEXT,
    parser_version TEXT,
    PRIMARY KEY (match_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_match_players_player ON match_players(player_id);
CREATE INDEX IF NOT EXISTS idx_match_players_team ON match_players(team_id);
