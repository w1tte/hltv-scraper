-- migrations/002_scrape_queue.sql
-- Phase 4: Match Discovery - scrape queue and progress tracking
--
-- Tables: scrape_queue, discovery_progress
-- scrape_queue tracks discovered matches for later scraping.
-- discovery_progress tracks which results page offsets have been processed.

CREATE TABLE IF NOT EXISTS scrape_queue (
    match_id      INTEGER PRIMARY KEY,
    url           TEXT NOT NULL,                   -- Relative match URL
    offset        INTEGER NOT NULL,                -- Which results page (0, 100, 200, ...)
    discovered_at TEXT NOT NULL,                   -- ISO 8601 timestamp
    is_forfeit    INTEGER NOT NULL DEFAULT 0,      -- 1 if map-text was "def"
    status        TEXT NOT NULL DEFAULT 'pending'  -- pending | scraped | failed
);

CREATE TABLE IF NOT EXISTS discovery_progress (
    offset       INTEGER PRIMARY KEY,    -- Results page offset (0, 100, 200, ...)
    completed_at TEXT NOT NULL           -- When this page was fully processed
);

CREATE INDEX IF NOT EXISTS idx_scrape_queue_status ON scrape_queue(status);
CREATE INDEX IF NOT EXISTS idx_scrape_queue_offset ON scrape_queue(offset);
