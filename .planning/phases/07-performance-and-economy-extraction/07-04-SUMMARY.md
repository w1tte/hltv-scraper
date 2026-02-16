---
phase: 07-performance-and-economy-extraction
plan: 04
subsystem: orchestration
tags: [orchestrator, performance, economy, kill-matrix, batch-pipeline, read-merge-write]

# Dependency graph
requires:
  - phase: 07-01
    provides: "Schema migration 004, repository methods (get_pending_perf_economy, upsert_perf_economy_complete, get_valid_round_numbers)"
  - phase: 07-02
    provides: "parse_performance() pure function, PerformanceData/KillMatrixEntry dataclasses"
  - phase: 07-03
    provides: "parse_economy() pure function, EconomyData/RoundEconomy dataclasses"
  - phase: 06-map-stats-extraction
    provides: "Pattern reference (map_stats.py orchestrator), Phase 6 player_stats + round_history data"
provides:
  - "run_performance_economy() async orchestrator for Phase 7 extraction"
  - "Complete Phase 7 pipeline: fetch performance+economy pages, parse, merge, persist"
affects:
  - future phases needing full player_stats with all columns populated
  - pipeline runner that chains all phases together

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Read-merge-write: read existing Phase 6 player_stats, merge Phase 7 fields, UPSERT back (prevents overwriting Phase 6 values)"
    - "Dual-page fetch: fetch both performance and economy pages per map in single batch loop"
    - "FK-safe economy insertion: filter economy rounds to those in round_history before persisting"

key-files:
  created:
    - src/scraper/performance_economy.py
    - tests/test_performance_economy.py
  modified: []

key-decisions:
  - "Read-merge-write approach for UPSERT: reads existing player_stats, preserves Phase 6 columns (kills, deaths, etc.), adds Phase 7 columns (kpr, dpr, impact, mk_rating)"
  - "Team ID resolution for economy: match team names from FusionChart seriesname against match_data, with positional fallback for name mismatches"
  - "Economy FK filtering: queries get_valid_round_numbers() before building economy dicts, skips rounds not in round_history"
  - "Kill matrix persisted alongside player_stats and economy in single atomic transaction via upsert_perf_economy_complete()"

metrics:
  duration: "20 min"
  completed: "2026-02-16"
  tasks_completed: 2
  tasks_total: 2
  tests_passed: 413
  tests_failed: 0
  tests_skipped: 4
---

# Phase 7 Plan 04: Performance + Economy Orchestrator Summary

**Async orchestrator wiring performance parser, economy parser, and repository into a batch pipeline with read-merge-write to preserve Phase 6 data and FK-safe economy insertion**

## What Was Done

### Task 1: Performance + economy orchestrator
Created `src/scraper/performance_economy.py` (230 lines) following the `map_stats.py` orchestrator pattern.

**Main function:** `run_performance_economy(client, match_repo, storage, config) -> dict`

**Pipeline stages:**
1. Get pending maps via `get_pending_perf_economy()` (Phase 6 complete, kpr=NULL)
2. Fetch phase: fetch both performance and economy pages per map, save to storage; discard entire batch on any fetch failure
3. Parse + persist phase (per-map failure handling):
   - Parse both pages with `parse_performance()` and `parse_economy()`
   - Read existing player_stats, merge Phase 7 fields (kpr, dpr, impact, mk_rating) while preserving Phase 6 values
   - Resolve economy team_ids from match_data with positional fallback
   - Filter economy rounds to valid round_history entries (FK safety)
   - Build kill_matrix dicts from performance parser output
   - Persist atomically via `upsert_perf_economy_complete()`

**Commit:** `b5f998a`

### Task 2: Orchestrator test suite
Created `tests/test_performance_economy.py` (370 lines) with 16 tests across 6 test classes.

**Test classes:**
- TestHappyPath (9 tests): full pipeline stats, kpr/dpr/mk_rating populated, economy rows created, both teams present, kill matrix with 3 types, Phase 6 values preserved
- TestEconomyFKFiltering (2 tests): economy rounds subset of round_history, skips invalid rounds without FK errors
- TestFetchFailure (2 tests): batch discard on fetch error, no data persisted
- TestParseFailure (1 test): per-map failure with continuation
- TestNoPendingMaps (1 test): empty batch returns zeros
- TestAlreadyProcessed (1 test): maps with non-NULL kpr skipped

**Seed helper:** `seed_match_with_map_stats()` parses real map stats sample to seed match, map, player_stats, and round_history rows (simulating Phase 6 completion).

**Commit:** `184c9b5`

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

All 3 verification checks from the plan passed:

1. `pytest tests/test_performance_economy.py -v --tb=short` -- 16/16 tests passed (91s)
2. `pytest tests/ -v --tb=short -x` -- 413 passed, 0 failed, 4 skipped (no regressions)
3. `python -c "from scraper.performance_economy import run_performance_economy; print('Full module chain importable')"` -- success

## Success Criteria Verification

- [x] run_performance_economy() fetches both performance and economy pages per map
- [x] Performance data correctly merges onto existing player_stats rows via read-merge-write (Phase 6 values preserved)
- [x] Economy data inserted only for rounds that exist in round_history (FK-safe filtering)
- [x] Team IDs for economy resolved from match_data with positional fallback
- [x] Kill matrix data inserted with correct player pair mappings (3 types, 25 entries each)
- [x] Fetch failure discards entire batch (entries remain pending)
- [x] Parse failure is per-map (other maps continue)
- [x] Maps already processed (kpr not NULL) are not re-fetched
- [x] test_existing_stats_preserved explicitly verifies Phase 6 columns are not overwritten
- [x] test_economy_rounds_match_round_history verifies FK safety
- [x] All existing tests from prior phases continue to pass (413/413)

## Next Phase Readiness

Phase 7 is now **complete** (all 4 plans executed). The full extraction pipeline covers:
- Phase 4: Match discovery (results listing)
- Phase 5: Match overview (metadata, vetoes, rosters)
- Phase 6: Map stats (scoreboard, round history)
- Phase 7: Performance + Economy (rate metrics, kill matrix, economy data)

Ready for Phase 8 (Pipeline Runner) which chains all phases into an end-to-end pipeline.

---
*Phase: 07-performance-and-economy-extraction*
*Completed: 2026-02-16*
