-- Add eco-adjusted stats columns to player_stats.
-- These are NULL for Rating 2.0 matches (pre-2024) where HLTV shows "null"/"-".

ALTER TABLE player_stats ADD COLUMN e_kills INTEGER;
ALTER TABLE player_stats ADD COLUMN e_deaths INTEGER;
ALTER TABLE player_stats ADD COLUMN e_hs_kills INTEGER;
ALTER TABLE player_stats ADD COLUMN e_kd_diff INTEGER;
ALTER TABLE player_stats ADD COLUMN e_adr REAL;
ALTER TABLE player_stats ADD COLUMN e_kast REAL;
ALTER TABLE player_stats ADD COLUMN e_opening_kills INTEGER;
ALTER TABLE player_stats ADD COLUMN e_opening_deaths INTEGER;
ALTER TABLE player_stats ADD COLUMN e_fk_diff INTEGER;
ALTER TABLE player_stats ADD COLUMN e_traded_deaths INTEGER;
