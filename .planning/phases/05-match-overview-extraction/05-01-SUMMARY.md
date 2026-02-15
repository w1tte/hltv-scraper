---
phase: 05-match-overview-extraction
plan: 01
subsystem: storage
tags: [sqlite, migration, repository, vetoes, rosters, queue]
depends_on:
  requires: [02-01, 02-02, 04-01]
  provides: [vetoes-table, match_players-table, upsert_match_overview, queue-management]
  affects: [05-02, 05-03, 06-01]
tech_stack:
  added: []
  patterns: [composite-pk-upsert, atomic-multi-table-transaction, queue-status-management]
key_files:
  created:
    - migrations/003_vetoes_rosters.sql
  modified:
    - src/scraper/repository.py
    - src/scraper/discovery_repository.py
    - tests/test_repository.py
    - tests/test_discovery_repository.py
decisions:
  - id: 05-01-01
    description: "Vetoes table uses match_id+step_number composite PK; match_players uses match_id+player_id composite PK"
  - id: 05-01-02
    description: "upsert_match_overview writes match+maps+vetoes+players in single transaction for atomicity"
  - id: 05-01-03
    description: "get_pending_matches ordered by match_id ascending for deterministic processing order"
metrics:
  duration: "~3 min"
  completed: "2026-02-15"
---

# Phase 5 Plan 1: Schema Extensions and Queue Management Summary

**One-liner:** Migration 003 adds vetoes/match_players tables with composite PKs; repository gains atomic multi-table upsert and queue pull/status methods.

## What Was Done

### Task 1: Migration 003 + Repository Methods
- Created `migrations/003_vetoes_rosters.sql` with two new tables:
  - `vetoes`: match_id + step_number composite PK, FK to matches, nullable team_name for "left_over" steps
  - `match_players`: match_id + player_id composite PK, FK to matches, team_num for positional identification
  - Two indexes: `idx_match_players_player` and `idx_match_players_team`
- Added `UPSERT_VETO` and `UPSERT_MATCH_PLAYER` SQL constants to repository.py following the exact pattern of existing constants (scraped_at for both timestamps on insert, excluded.scraped_at for updated_at on conflict)
- Added `upsert_match_overview()` -- atomic transaction writing match + maps + vetoes + players in a single `with self.conn:` block
- Added `get_vetoes()` and `get_match_players()` read methods with proper ordering
- Added `UPDATE_STATUS` SQL constant and `get_pending_matches()` / `update_status()` methods to DiscoveryRepository

### Task 2: Comprehensive Tests
- Added `make_veto_data()` and `make_match_player_data()` helper functions
- Added 3 tests in `TestUpsertMatchOverview`: full insert (match+3 maps+7 vetoes+10 players), atomicity (rollback on failure), update-on-conflict
- Added 3 tests in `TestVetoes`: ordered steps, empty match, null team_name
- Added 2 tests in `TestMatchPlayers`: ordered by team_num+player_id, empty match
- Added 6 tests in `TestQueueManagement`: pending-only filter, limit respect, match_id ordering, scraped/failed transitions, empty result

**Test results:** 49/49 passing (31 repository + 18 discovery), zero regressions.

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 05-01-01 | Composite PKs on both new tables | Matches existing pattern (maps, player_stats, etc.); natural UPSERT conflict targets |
| 05-01-02 | Single-transaction upsert_match_overview | Atomicity prevents partial writes; match overview parser produces all data at once |
| 05-01-03 | get_pending_matches ordered by match_id | Deterministic processing order; lowest IDs (oldest matches) processed first |

## Deviations from Plan

None -- plan executed exactly as written.

## Commit Log

| Hash | Type | Description |
|------|------|-------------|
| 9b13f68 | feat | Add vetoes/roster tables and repository methods |
| 0860fb5 | test | Add tests for vetoes, match_players, and queue management |

## Next Phase Readiness

Plan 05-02 (match overview parser) can proceed immediately. All database infrastructure is in place:
- Tables exist for all data the parser will extract (matches, maps, vetoes, match_players)
- `upsert_match_overview()` provides the single atomic write method the orchestrator needs
- `get_pending_matches()` and `update_status()` provide queue pull/update for the orchestrator
- Migration 003 is automatically applied by `Database.initialize()` via the migration system
