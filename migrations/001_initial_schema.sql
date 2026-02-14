-- migrations/001_initial_schema.sql
-- Phase 2: Storage Foundation - Initial schema
--
-- Tables: matches, maps, player_stats, round_history, economy
-- All tables support UPSERT via ON CONFLICT on their unique keys.
-- Provenance columns (scraped_at, updated_at, source_url) track data lineage.

CREATE TABLE IF NOT EXISTS matches (
    match_id      INTEGER PRIMARY KEY,  -- HLTV match ID (from URL)
    date          TEXT,                  -- ISO 8601 match date
    event_id      INTEGER,              -- HLTV event ID
    event_name    TEXT,                  -- Event/tournament name
    team1_id      INTEGER,              -- HLTV team ID
    team1_name    TEXT,                  -- Team name at time of match
    team2_id      INTEGER,
    team2_name    TEXT,
    team1_score   INTEGER,              -- Maps won by team 1
    team2_score   INTEGER,              -- Maps won by team 2
    best_of       INTEGER,              -- 1, 3, or 5
    is_lan        INTEGER,              -- 0=online, 1=LAN
    match_url     TEXT,                 -- Full HLTV URL
    -- Provenance
    scraped_at    TEXT NOT NULL,         -- When data was fetched
    updated_at    TEXT NOT NULL,         -- When data was last written
    source_url    TEXT,                  -- URL this data was parsed from
    parser_version TEXT                  -- Version of parser that produced this
);

CREATE TABLE IF NOT EXISTS maps (
    match_id        INTEGER NOT NULL REFERENCES matches(match_id),
    map_number      INTEGER NOT NULL,     -- 1-based position in series
    mapstatsid      INTEGER,              -- HLTV mapstatsid (from stats URL)
    map_name        TEXT,                 -- "Mirage", "Inferno", etc.
    -- Scores
    team1_rounds    INTEGER,              -- Total rounds won by team 1
    team2_rounds    INTEGER,
    team1_ct_rounds INTEGER,              -- Rounds won on CT side
    team1_t_rounds  INTEGER,              -- Rounds won on T side
    team2_ct_rounds INTEGER,
    team2_t_rounds  INTEGER,
    -- Provenance
    scraped_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    source_url      TEXT,
    parser_version  TEXT,
    --
    PRIMARY KEY (match_id, map_number)
);

CREATE TABLE IF NOT EXISTS player_stats (
    match_id      INTEGER NOT NULL,
    map_number    INTEGER NOT NULL,
    player_id     INTEGER NOT NULL,       -- HLTV player ID
    player_name   TEXT,                   -- Name at time of match
    team_id       INTEGER,                -- Which team this player was on
    -- Core stats
    kills         INTEGER,
    deaths        INTEGER,
    assists       INTEGER,
    flash_assists INTEGER,
    hs_kills      INTEGER,                -- Headshot kills
    kd_diff       INTEGER,                -- Kill-death difference
    adr           REAL,                   -- Average damage per round
    kast          REAL,                   -- KAST percentage (0-100)
    fk_diff       INTEGER,                -- First kills difference
    -- Rating (nullable -- old matches may lack Rating 3.0)
    rating_2      REAL,                   -- HLTV Rating 2.0/2.1
    rating_3      REAL,                   -- HLTV Rating 3.0 (Aug 2025+)
    -- Performance page stats (populated in Phase 7)
    kpr           REAL,                   -- Kills per round
    dpr           REAL,                   -- Deaths per round
    impact        REAL,                   -- Impact rating
    -- Provenance
    scraped_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    source_url    TEXT,
    parser_version TEXT,
    --
    PRIMARY KEY (match_id, map_number, player_id),
    FOREIGN KEY (match_id, map_number) REFERENCES maps(match_id, map_number)
);

CREATE TABLE IF NOT EXISTS round_history (
    match_id      INTEGER NOT NULL,
    map_number    INTEGER NOT NULL,
    round_number  INTEGER NOT NULL,       -- 1-based round number
    winner_side   TEXT,                   -- "CT" or "T"
    win_type      TEXT,                   -- "bomb_planted", "elimination", "defuse", "time"
    winner_team_id INTEGER,               -- HLTV team ID of round winner
    -- Provenance
    scraped_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    source_url    TEXT,
    parser_version TEXT,
    --
    PRIMARY KEY (match_id, map_number, round_number),
    FOREIGN KEY (match_id, map_number) REFERENCES maps(match_id, map_number)
);

CREATE TABLE IF NOT EXISTS economy (
    match_id      INTEGER NOT NULL,
    map_number    INTEGER NOT NULL,
    round_number  INTEGER NOT NULL,
    team_id       INTEGER NOT NULL,       -- HLTV team ID
    equipment_value INTEGER,              -- Total team equipment value
    buy_type      TEXT,                   -- "eco", "force", "full", "pistol"
    -- Provenance
    scraped_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    source_url    TEXT,
    parser_version TEXT,
    --
    PRIMARY KEY (match_id, map_number, round_number, team_id),
    FOREIGN KEY (match_id, map_number, round_number)
        REFERENCES round_history(match_id, map_number, round_number)
);

-- Indexes for common query patterns (ad-hoc SQL exploration)
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_event ON matches(event_id);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(team1_id, team2_id);
CREATE INDEX IF NOT EXISTS idx_maps_mapstatsid ON maps(mapstatsid);
CREATE INDEX IF NOT EXISTS idx_player_stats_player ON player_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_team ON player_stats(team_id);
