---
phase: 09-pipeline-orchestration
plan: 02
subsystem: incremental-discovery
tags: [discovery, incremental, early-termination, config, pipeline]

dependency_graph:
  requires:
    - "04-03 (run_discovery orchestrator)"
    - "04-01 (DiscoveryRepository with scrape_queue UPSERT)"
  provides:
    - "Incremental discovery with early termination (count_new_matches)"
    - "Failed match reset to pending (reset_failed_matches)"
    - "Pipeline config fields (start_offset, consecutive_failure_threshold)"
    - "Shutdown flag support in run_discovery"
  affects:
    - "09-03 (pipeline runner will pass shutdown flag and incremental parameter)"
    - "09-04 (CLI will map --start-offset to config.start_offset)"

tech_stack:
  added: []
  patterns:
    - "count_new_matches BEFORE persist_page to avoid UPSERT corrupting the count"
    - "Duck-typed shutdown parameter (any object with .is_set property)"
    - "stats dict extended with new_matches key for incremental tracking"

key_files:
  created: []
  modified:
    - src/scraper/config.py
    - src/scraper/discovery.py
    - src/scraper/discovery_repository.py

decisions:
  - id: "09-02-01"
    decision: "count_new_matches called BEFORE persist_page in the discovery loop"
    reason: "persist_page does UPSERT which would make all matches 'existing' -- checking before persisting gives accurate new-match count"
  - id: "09-02-02"
    decision: "max_offset NOT renamed to end_offset"
    reason: "Existing code (discovery.py, tests) uses max_offset throughout; CLI will map --end-offset to config.max_offset"
  - id: "09-02-03"
    decision: "shutdown parameter uses duck typing (any object with .is_set property)"
    reason: "Avoids circular imports and tight coupling to asyncio.Event or ShutdownHandler"
  - id: "09-02-04"
    decision: "In non-incremental mode, new_matches set equal to matches_found at end"
    reason: "Simplifies stats reporting -- callers always have a new_matches key"

metrics:
  duration: "~21 min"
  completed: "2026-02-16"
  tasks: "2/2"
---

# Phase 9 Plan 02: Incremental Discovery Summary

**One-liner:** Incremental discovery mode with early termination when all matches on a page are already known, plus failed-match auto-reset and pipeline config fields.

## What Was Done

### Task 1: Extend ScraperConfig with pipeline fields
Added two new fields to the `ScraperConfig` dataclass in `src/scraper/config.py`:

- `start_offset: int = 0` -- Start offset for results pagination (companion to existing `max_offset`)
- `consecutive_failure_threshold: int = 3` -- Halt pipeline after N consecutive failures

The existing `max_offset` field (default 9900) was intentionally NOT renamed to `end_offset` to avoid breaking existing code. The CLI will map `--end-offset` to `config.max_offset`.

**Commit:** `1c5df22`

### Task 2: Incremental discovery + failed match reset
Modified two files with five changes:

**discovery_repository.py** -- Two new methods:

1. `count_new_matches(match_ids)` -- Counts how many match IDs are NOT already in `scrape_queue`. Uses `SELECT COUNT(*) ... WHERE match_id IN (...)` and subtracts from input length. Handles empty list edge case.

2. `reset_failed_matches()` -- Updates all `status='failed'` rows back to `'pending'`. Returns `cursor.rowcount` for logging. Uses `with self.conn:` for transaction safety.

**discovery.py** -- Three changes to `run_discovery`:

1. **New parameters:** `incremental: bool = True` and `shutdown=None` (duck-typed, any object with `.is_set` property).

2. **Pagination range:** Changed from `range(0, ...)` to `range(config.start_offset, ...)` to respect the new config field.

3. **Shutdown check:** At the start of each loop iteration, checks `shutdown.is_set` and breaks cleanly with a log message.

4. **Incremental early termination:** Before `persist_page`, calls `repo.count_new_matches(match_ids)`. If zero new matches found, logs and breaks. This ordering is critical -- checking AFTER persist would always find zero new matches due to UPSERT.

5. **Stats dict:** Added `new_matches` key. In incremental mode, tracks truly new discoveries. In non-incremental mode, set equal to `matches_found` at end.

**Commit:** `4cf7d97`

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

| Check | Result |
|-------|--------|
| `ScraperConfig().start_offset == 0` | Pass |
| `ScraperConfig().consecutive_failure_threshold == 3` | Pass |
| `ScraperConfig(start_offset=100).start_offset == 100` | Pass |
| `hasattr(DiscoveryRepository, 'count_new_matches')` | Pass |
| `hasattr(DiscoveryRepository, 'reset_failed_matches')` | Pass |
| Existing 18 discovery_repository tests | Pass (0.76s) |
| Full test suite (458 tests, non-integration) | Pass (994.75s) |
| Functional test: count_new_matches accuracy | Pass (all/some/none new) |
| Functional test: reset_failed_matches idempotent | Pass |
| run_discovery signature has incremental + shutdown params | Pass |

## Next Phase Readiness

Plan 03 (pipeline runner) can proceed. It will:
- Call `repo.reset_failed_matches()` at pipeline start
- Pass `incremental=not args.full` and `shutdown=shutdown_handler` to `run_discovery`
- Use `config.start_offset` and `config.max_offset` from CLI args
