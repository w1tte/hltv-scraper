-- migrations/011_scrape_attempts.sql
-- Track per-match scrape attempt count for automatic retry limiting.
--
-- Matches auto-retry up to 5 times. After 5 failures they stay 'failed'
-- for manual review on the dashboard. A manual retry that also fails
-- is marked 'failed_permanent'.

ALTER TABLE scrape_queue ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
