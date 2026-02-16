---
phase: 07-performance-and-economy-extraction
plan: 01
subsystem: data-layer
tags: [sqlite, migration, repository, schema, upsert]
completed: 2026-02-16
duration: "26 min"
dependency_graph:
  requires: [phase-02, phase-06]
  provides: [kill_matrix-table, perf-economy-columns, pending-perf-economy-query, upsert-perf-economy-method]
  affects: [07-02, 07-03, 07-04]
tech_stack:
  added: []
  patterns: [schema-migration-004, extended-upsert-sql]
key_files:
  created:
    - migrations/004_performance_economy.sql
  modified:
    - src/scraper/repository.py
    - src/scraper/config.py
    - src/scraper/map_stats.py
    - tests/test_repository.py
    - tests/test_db.py
decisions:
  - "UPSERT_PLAYER_STATS includes all 7 new columns in INSERT, VALUES, and ON CONFLICT -- both Phase 6 and Phase 7 callers must provide all keys"
  - "GET_PENDING_PERF_ECONOMY uses kpr IS NULL as the Phase 7 pending indicator (Phase 6 sets kpr=None, Phase 7 fills it in)"
  - "Phase 6 orchestrator now persists opening_kills through round_swing from map_stats_parser; mk_rating set to None (Phase 7 fills it)"
  - "kill_matrix FK references maps(match_id, map_number) -- same pattern as player_stats and round_history"
metrics:
  tasks_completed: 2
  tasks_total: 2
  tests_passed: 397
  tests_failed: 0
  tests_skipped: 4
---

# Phase 7 Plan 01: Schema & Repository Extension Summary

Migration 004 adds 7 new columns to player_stats (opening_kills, opening_deaths, multi_kills, clutch_wins, traded_deaths, round_swing, mk_rating) and creates the kill_matrix table with composite PK and FK to maps. Repository extended with UPSERT_KILL_MATRIX, GET_PENDING_PERF_ECONOMY, and 4 new methods. Phase 6 orchestrator now persists the 6 fields it was already extracting but silently dropping.

## What Was Done

### Task 1: Schema migration and config extension
- Created `migrations/004_performance_economy.sql` with 7 ALTER TABLE statements and CREATE TABLE for kill_matrix
- Added `perf_economy_batch_size: int = 10` to ScraperConfig dataclass
- Schema version advances from 3 to 4

### Task 2: Repository extension and Phase 6 orchestrator update
- Updated UPSERT_PLAYER_STATS to include all 7 new columns in INSERT, VALUES, and ON CONFLICT clauses
- Added UPSERT_KILL_MATRIX SQL constant with 5-column composite PK conflict target
- Added GET_PENDING_PERF_ECONOMY SQL constant (finds maps with player_stats but NULL kpr)
- Added 4 new MatchRepository methods:
  - `get_pending_perf_economy(limit)` -- returns maps ready for Phase 7 extraction
  - `get_valid_round_numbers(match_id, map_number)` -- returns set of round numbers from round_history
  - `upsert_perf_economy_complete(perf_stats, economy_data, kill_matrix_data)` -- atomic triple-upsert
  - `upsert_kill_matrix(data)` -- single-row kill matrix upsert
- Updated Phase 6 orchestrator dict to include opening_kills, opening_deaths, multi_kills, clutch_wins, traded_deaths, round_swing, mk_rating=None
- Updated test helpers (make_player_stats_data) with new column defaults
- Updated test_db.py assertions for schema v4 (version number, index count, migration count)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_db.py hard-coded schema version and index set**
- **Found during:** Task 2 verification
- **Issue:** test_db.py had hard-coded `assert db.get_schema_version() == 3` (4 locations) and a fixed set of 10 expected indexes, failing after migration 004 added schema v4 and idx_kill_matrix_players
- **Fix:** Updated schema version assertions to 4, migration count to 4, and added idx_kill_matrix_players to expected index set
- **Files modified:** tests/test_db.py
- **Commit:** 256f648

## Verification

All 4 plan verification checks pass:
1. Schema version 4 confirmed
2. All 6 map_stats tests pass
3. All 40 repository tests pass
4. All Phase 7 SQL constants and config fields verified via import

Full regression suite: 397 passed, 0 failed, 4 skipped (integration tests)

## Next Phase Readiness

Plan 07-01 provides the complete data layer foundation for the remaining Phase 7 plans:
- 07-02 (Performance Parser): uses UPSERT_PLAYER_STATS with mk_rating column
- 07-03 (Economy Parser): uses UPSERT_ECONOMY (already existed) + get_valid_round_numbers for FK safety
- 07-04 (Orchestrator): uses get_pending_perf_economy + upsert_perf_economy_complete + UPSERT_KILL_MATRIX

No blockers. All dependencies satisfied.
