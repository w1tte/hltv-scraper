-- migrations/005_quarantine.sql
-- Phase 8: Data Validation - Quarantine table
--
-- Stores records that fail Pydantic validation for later investigation.
-- Each row captures the raw data dict, the validation error, and
-- contextual IDs for easy lookup.

CREATE TABLE IF NOT EXISTS quarantine (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type     TEXT NOT NULL,       -- Model class name ("MatchModel", "PlayerStatsModel", etc.)
    match_id        INTEGER,             -- For easy lookup (nullable if match itself failed)
    map_number      INTEGER,             -- Nullable (not all entities are per-map)
    raw_data        TEXT NOT NULL,       -- JSON dump of the dict that failed validation
    error_details   TEXT NOT NULL,       -- str(ValidationError) or error message
    quarantined_at  TEXT NOT NULL,       -- ISO 8601 timestamp
    resolved        INTEGER DEFAULT 0   -- 0=pending, 1=resolved (re-processed or dismissed)
);

CREATE INDEX IF NOT EXISTS idx_quarantine_match ON quarantine(match_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_type ON quarantine(entity_type);
CREATE INDEX IF NOT EXISTS idx_quarantine_resolved ON quarantine(resolved);
