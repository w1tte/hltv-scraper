-- Migration 010: add date_unix_ms (epoch ms) to matches for exact start time
ALTER TABLE matches ADD COLUMN date_unix_ms INTEGER;
