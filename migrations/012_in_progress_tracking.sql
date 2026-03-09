-- migrations/012_in_progress_tracking.sql
-- Track in-flight matches for crash recovery debugging.
--
-- Adds 'in_progress' as an intermediate status between 'pending' and 'scraped'.
-- On startup, any matches left in 'in_progress' (from a crash) are reset to
-- 'pending' so they get re-processed.

ALTER TABLE scrape_queue ADD COLUMN IF NOT EXISTS started_at TEXT;
