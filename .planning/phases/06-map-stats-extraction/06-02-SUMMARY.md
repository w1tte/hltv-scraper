---
phase: 06-map-stats-extraction
plan: 02
subsystem: database
tags: [sqlite, repository, upsert, batch, query]

# Dependency graph
requires:
  - phase: 02-storage-foundation
    provides: "DB schema with maps, player_stats, round_history tables"
  - phase: 05-match-overview
    provides: "Maps table populated with mapstatsid values"
provides:
  - "get_pending_map_stats() query for unprocessed maps"
  - "upsert_map_stats_complete() atomic write for player_stats + round_history"
  - "map_stats_batch_size config field"
affects: [06-map-stats-extraction plan 03 orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns: ["NOT EXISTS subquery for pending item detection", "multi-table atomic upsert in single transaction"]

key-files:
  created: []
  modified:
    - src/scraper/repository.py
    - src/scraper/config.py
    - tests/test_repository.py

key-decisions:
  - "get_pending_map_stats uses NOT EXISTS subquery against player_stats to detect unprocessed maps"
  - "upsert_map_stats_complete writes player_stats + round_history in single transaction for atomicity"

patterns-established:
  - "Pending query pattern: SELECT from parent WHERE child NOT EXISTS + mapstatsid IS NOT NULL"
  - "Combined upsert pattern: multiple table writes in single with self.conn: block"

# Metrics
duration: 2min
completed: 2026-02-15
---

# Phase 6 Plan 02: Map Stats Repository Extension Summary

**NOT EXISTS pending-maps query and atomic player_stats + round_history upsert with batch size config**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-15T22:59:04Z
- **Completed:** 2026-02-15T23:01:03Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added get_pending_map_stats() method that finds maps with mapstatsid but no player_stats rows via NOT EXISTS subquery
- Added upsert_map_stats_complete() method that atomically writes player_stats and round_history in a single transaction
- Added map_stats_batch_size config field (default 10) for orchestrator batch control
- 9 new tests covering filtering, ordering, limit, atomicity, and rollback behavior

## Task Commits

Each task was committed atomically:

1. **Task 1: Add repository methods and config** - `f0fc873` (feat)
2. **Task 2: Add tests for new repository methods** - `b998dd7` (test)

## Files Created/Modified
- `src/scraper/repository.py` - Added GET_PENDING_MAP_STATS SQL constant, get_pending_map_stats() read method, upsert_map_stats_complete() batch write method
- `src/scraper/config.py` - Added map_stats_batch_size field with default 10
- `tests/test_repository.py` - Added TestGetPendingMapStats (6 tests) and TestUpsertMapStatsComplete (3 tests)

## Decisions Made
- get_pending_map_stats uses NOT EXISTS subquery (consistent with how the overview orchestrator checks pending matches)
- upsert_map_stats_complete placed in batch UPSERT section, above existing individual batch methods, since it combines two table writes
- Ordering by (match_id, map_number) for deterministic processing order (same pattern as get_pending_matches)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Repository methods ready for the map stats parser (06-01) and orchestrator (06-03) to use
- get_pending_map_stats provides the queue; upsert_map_stats_complete provides the atomic write
- Config field ready for orchestrator batch size control

---
*Phase: 06-map-stats-extraction*
*Completed: 2026-02-15*
