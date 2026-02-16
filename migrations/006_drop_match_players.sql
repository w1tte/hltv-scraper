-- Migration 006: Drop match_players table
-- Player rosters are now derived from per-map player_stats (scoreboard data)
-- which correctly handles substitutions between maps in a series.

DROP TABLE IF EXISTS match_players;
