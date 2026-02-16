---
phase: 08-data-validation
plan: 02
subsystem: validation
tags: [validation, quarantine, pydantic, testing, data-integrity]
depends_on:
  requires: [08-01-validation-models]
  provides: [validation-wrapper, model-tests, validation-tests]
  affects: [08-03-orchestrator-integration, 08-04-retroactive-validation]
tech_stack:
  added: []
  patterns: [validate-and-quarantine, warn-and-insert, batch-validation]
key_files:
  created:
    - src/scraper/validation.py
    - tests/test_models.py
    - tests/test_validation.py
  modified: []
decisions:
  - id: 08-02-01
    decision: "validate_and_quarantine wraps exception handling around repo.insert_quarantine to prevent quarantine failures from blocking pipeline"
    rationale: "Quarantine is a safety net, not a critical path -- if it fails, log and continue"
metrics:
  duration: "3 min"
  completed: "2026-02-16"
---

# Phase 8 Plan 02: Validation Wrapper and Tests Summary

Validation wrapper layer with quarantine integration, plus 42 unit tests covering all 9 Pydantic models and the validation functions.

## What Was Built

### Validation Wrapper (src/scraper/validation.py)

Four functions bridging parsers and persistence:

- **validate_and_quarantine(data, model_cls, context, repo)**: Validates a single dict against a Pydantic model. On success returns model_dump() dict. On failure logs the error, builds a quarantine record (entity_type, match_id, map_number, raw_data as JSON, error_details, quarantined_at, resolved=0), inserts via repo.insert_quarantine if repo is not None, returns None. Auto-fills updated_at from scraped_at if missing. Captures and logs any soft-validation warnings from catch_warnings.
- **validate_batch(items, model_cls, context, repo)**: Validates a list of dicts, returns tuple of (valid_dicts, quarantine_count). Simple loop calling validate_and_quarantine per item.
- **check_player_count(stats_dicts, match_id, map_number)**: Warns when map has != 10 player stats rows. Returns list of warning strings (empty = clean). Warn-and-insert, not reject.
- **check_economy_alignment(economy_dicts, valid_round_numbers, match_id, map_number)**: Warns when any economy round_number is not in the round_history valid set. Defense-in-depth check.

### Test Suite (42 tests)

**tests/test_models.py** (29 tests, 409 lines):
- MatchModel: valid match, match_id=0 rejected, same team IDs rejected, score exceeds best_of rejected, winner low score warns, forfeit model allows irregular scores
- MapModel: valid map, half scores exceed total rejected, OT half scores allowed, extreme OT warns
- PlayerStatsModel: valid stats, negative kills rejected, kd_diff mismatch rejected, fk_diff mismatch rejected, hs_kills exceed kills rejected, unusual rating warns, unusual ADR warns, nulls allowed for performance fields
- RoundHistoryModel: valid round, invalid winner_side rejected, invalid win_type rejected
- EconomyModel: valid economy, invalid buy_type rejected
- VetoModel: valid veto, invalid action rejected
- MatchPlayerModel: valid match player, invalid team_num rejected
- KillMatrixModel: valid kill matrix, invalid matrix_type rejected

**tests/test_validation.py** (13 tests, 241 lines):
- validate_and_quarantine: valid returns dict, invalid returns None and quarantines, no-repo does not crash, auto-fills updated_at
- validate_batch: mixed batch correct counts, all valid, all invalid
- check_player_count: exactly 10 clean, not 10 warns, zero players warns
- check_economy_alignment: clean alignment, extra round warns, multiple misaligned

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 08-02-01 | Exception handling around repo.insert_quarantine | Quarantine is safety net, not critical path -- log and continue if it fails |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_hs_kills_exceed_kills_rejected kd_diff consistency**
- **Found during:** Task 2
- **Issue:** Changing kills to 15 without updating kd_diff caused kd_diff validator to fire first instead of hs_kills validator
- **Fix:** Also update kd_diff to match new kills - deaths value in the test
- **Files modified:** tests/test_models.py
- **Commit:** 554bbb1

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | e33e1d4 | Validation wrapper module (validate_and_quarantine, validate_batch, checks) |
| 2 | 554bbb1 | Unit tests for all 9 models and validation wrapper (42 tests) |

## Verification Results

All 5 verification checks passed:
1. validate_and_quarantine returns dict on success, None on failure
2. Quarantine records contain entity_type, match_id, raw_data, error_details
3. Batch-level checks (player count, economy alignment) return appropriate warnings
4. Warning capture works: unusual values emit warnings that are logged
5. All 42 tests pass with pytest (0 failures)

## Next Phase Readiness

Ready for 08-03 (orchestrator integration). The validation wrapper provides:
- validate_and_quarantine for single-record validation in all orchestrators
- validate_batch for list validation (player stats, economy rows)
- check_player_count and check_economy_alignment for batch-level integrity
- Full test coverage proving models catch what they claim to catch
