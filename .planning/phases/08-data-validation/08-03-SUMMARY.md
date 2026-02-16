---
phase: 08-data-validation
plan: 03
subsystem: validation
tags: [validation, orchestrators, quarantine, pydantic, integration]
depends_on:
  requires: [08-01-validation-models, 08-02-validation-wrapper]
  provides: [validated-orchestrators, orchestrator-quarantine-tests]
  affects: [08-04-retroactive-validation]
tech_stack:
  added: []
  patterns: [validate-before-persist, partial-data-insertion, forfeit-model-routing]
key_files:
  created: []
  modified:
    - src/scraper/match_overview.py
    - src/scraper/map_stats.py
    - src/scraper/performance_economy.py
    - tests/test_match_overview.py
    - tests/test_map_stats.py
    - tests/test_performance_economy.py
decisions:
  - id: 08-03-01
    decision: "Partial data insertion on quarantine -- if some maps/vetoes/players fail validation, persist the valid ones and quarantine the bad ones"
    rationale: "Partial data is better than no data; quarantine already has the failed records for later review"
  - id: 08-03-02
    decision: "Forfeit detection routes to ForfeitMatchModel (no score consistency checks) vs MatchModel based on result.is_forfeit"
    rationale: "Forfeit matches have irregular scores that would fail normal MatchModel validation"
metrics:
  duration: "31 min"
  completed: "2026-02-16"
---

# Phase 8 Plan 03: Orchestrator Validation Integration Summary

Pydantic validation wired into all 3 orchestrators (match_overview, map_stats, performance_economy) so every record is validated before database insertion, with quarantine for failures and 3 new quarantine-specific tests.

## What Was Built

### Validation Integration in Orchestrators

**match_overview.py** -- 6 validation steps added before upsert:
1. Determines model class: `ForfeitMatchModel` if `result.is_forfeit`, else `MatchModel`
2. `validate_and_quarantine()` on match dict -- if None, marks match as failed and skips
3. `validate_batch()` on maps, vetoes, and players lists
4. Logs warnings if any child records quarantined (partial data still persisted)
5. `check_player_count()` for batch-level player count check (warn-and-insert)
6. Persists validated dicts via `upsert_match_overview()`

**map_stats.py** -- 4 validation steps added before upsert:
1. `validate_batch()` on player_stats and round_history lists
2. If all player_stats quarantined: marks map as failed, skips persist
3. `check_player_count()` for batch-level check (warn-and-insert)
4. Persists validated dicts via `upsert_map_stats_complete()`

**performance_economy.py** -- 5 validation steps added before upsert:
1. `validate_batch()` on perf_stats, economy, and kill_matrix lists
2. If all perf_stats quarantined: marks map as failed, skips persist
3. `check_economy_alignment()` for economy/round_history FK alignment
4. Persists validated dicts via `upsert_perf_economy_complete()`

### New Quarantine Tests (3 tests)

- **test_match_overview_quarantines_invalid_match**: Patches parser to produce team1_id==team2_id, verifies match fails validation, gets quarantined, marked as failed in queue
- **test_map_stats_quarantines_invalid_stats**: Patches parser to set kills=-1 on one player, verifies that player is quarantined while 9 valid players still persist
- **test_perf_economy_quarantines_invalid_economy**: Patches economy parser to set buy_type="pistol" (invalid), verifies economy row quarantined while perf stats and kill matrix still persist

### Key Properties Verified

- **No function signature changes**: run_match_overview, run_map_stats, run_performance_economy signatures unchanged
- **Never halts on validation failures**: All orchestrators log, quarantine, and continue
- **All 29 existing tests pass unchanged**: Validation is transparent to happy-path data from real HTML samples
- **All 32 orchestrator tests pass**: 29 existing + 3 new quarantine tests

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 08-03-01 | Partial data insertion on quarantine | Partial data is better than no data; quarantine has failed records for review |
| 08-03-02 | Forfeit detection routes to ForfeitMatchModel vs MatchModel | Forfeit matches have irregular scores that would fail normal validation |

## Deviations from Plan

None -- plan executed exactly as written.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | f389f00 | Wire Pydantic validation into all 3 orchestrators |
| 2 | be73744 | Add quarantine tests for all 3 orchestrators (3 new tests) |

## Verification Results

All verification criteria passed:
1. `pytest tests/ -m "not integration"` -- 454 passed (4 pre-existing test_db.py failures unrelated to changes)
2. All 3 orchestrators import cleanly with validation imports
3. Invalid data is quarantined (verified by 3 quarantine-specific tests)
4. Valid data flows through to upsert methods unchanged (verified by 29 existing tests)
5. Pipeline never halts on validation failure (verified by test continuation behavior)

## Next Phase Readiness

Ready for 08-04 (retroactive validation). All 3 orchestrators now:
- Validate every record through Pydantic models before database insertion
- Quarantine invalid records with full error details
- Run batch-level integrity checks (player count, economy alignment)
- Continue processing on validation failures (never halt the pipeline)
