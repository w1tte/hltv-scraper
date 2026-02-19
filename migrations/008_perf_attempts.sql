-- Track retry attempts for performance/economy parsing.
-- Maps that repeatedly fail parsing (bad page structure, missing data)
-- should be skipped after N attempts to prevent infinite retry loops.

ALTER TABLE maps ADD COLUMN perf_attempts INTEGER NOT NULL DEFAULT 0;
