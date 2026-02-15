---
phase: 04-match-discovery
plan: 01
subsystem: database
tags: [sqlite, migration, upsert, scrape-queue, discovery, storage]

# Dependency graph
requires:
  - phase: 02-storage-foundation
    provides: "Database with migration support, MatchRepository pattern, HtmlStorage"
provides:
  - "scrape_queue and discovery_progress tables (migration 002)"
  - "DiscoveryRepository with UPSERT queue operations"
  - "HtmlStorage results page methods (offset-based)"
  - "ScraperConfig discovery pagination fields (max_offset, results_per_page)"
affects: [04-02-results-parser, 04-03-discovery-runner, 05-match-overview]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Offset-based storage separate from match-based storage (results/ vs matches/)"
    - "UPSERT preserves status on re-discovery (ON CONFLICT omits status column)"
    - "persist_page atomic transaction combining batch upsert + offset progress"

key-files:
  created:
    - "migrations/002_scrape_queue.sql"
    - "src/scraper/discovery_repository.py"
    - "tests/test_discovery_repository.py"
    - "tests/test_storage_results.py"
  modified:
    - "src/scraper/config.py"
    - "src/scraper/storage.py"
    - "tests/test_db.py"

key-decisions:
  - "UPSERT ON CONFLICT does NOT update status column -- re-discovery preserves scraped/failed state"
  - "Results pages stored under base_dir/results/ with offset-based naming, separate from matches/ hierarchy"
  - "persist_page combines batch upsert + offset marking in single transaction for atomicity"

patterns-established:
  - "DiscoveryRepository follows MatchRepository pattern: raw sqlite3.Connection, module-level SQL constants, with conn: transactions"
  - "Offset-based HtmlStorage methods: save_results_page, load_results_page, results_page_exists"

# Metrics
duration: 4min
completed: 2026-02-15
---

# Phase 4 Plan 1: Discovery Infrastructure Summary

**SQLite scrape_queue + discovery_progress tables with UPSERT-preserving-status semantics, offset-based HTML storage, and DiscoveryRepository following MatchRepository pattern**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-15T20:40:14Z
- **Completed:** 2026-02-15T20:43:45Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Created migration 002 with scrape_queue (6 columns, 2 indexes) and discovery_progress tables
- Built DiscoveryRepository with UPSERT that preserves status on re-discovery (critical invariant verified by test)
- Extended HtmlStorage with offset-based results page methods, fully decoupled from match-based storage
- Extended ScraperConfig with max_offset=9900 and results_per_page=100
- 19 new tests (7 storage + 12 repository), all 105 unit tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Migration, config extension, and HtmlStorage results page methods** - `60e0cda` (feat)
2. **Task 2: DiscoveryRepository with UPSERT semantics and unit tests** - `6c23dcf` (feat)

## Files Created/Modified
- `migrations/002_scrape_queue.sql` - scrape_queue and discovery_progress table definitions with 2 indexes
- `src/scraper/discovery_repository.py` - DiscoveryRepository with upsert_batch, persist_page, count/read methods
- `src/scraper/config.py` - Added max_offset and results_per_page fields to ScraperConfig
- `src/scraper/storage.py` - Added save_results_page, load_results_page, results_page_exists methods
- `tests/test_discovery_repository.py` - 12 tests covering UPSERT semantics, offset progress, counts, reads
- `tests/test_storage_results.py` - 7 tests covering round-trip, exists, path structure, gzip compression
- `tests/test_db.py` - Updated assertions for schema version 2 and 8 total indexes

## Decisions Made
- UPSERT ON CONFLICT clause intentionally omits `status` column so re-running discovery does not reset already-scraped matches back to 'pending'
- Results pages use offset-based paths under `base_dir/results/` rather than being shoehorned into the match-based `matches/` hierarchy
- `persist_page` method wraps both batch upsert and offset marking in a single `with self.conn:` transaction for crash safety

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_db.py assertions for new schema version**
- **Found during:** Task 1 (verification step)
- **Issue:** 4 existing tests in test_db.py hardcoded schema version 1 and expected 6 indexes. Adding migration 002 changes version to 2 and adds 2 new indexes.
- **Fix:** Updated assertions: schema version 1->2, migration count 1->2, index set expanded to include idx_scrape_queue_status and idx_scrape_queue_offset
- **Files modified:** tests/test_db.py
- **Verification:** All 13 test_db.py tests pass
- **Committed in:** 60e0cda (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Expected consequence of adding a migration. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- scrape_queue and discovery_progress tables ready for parser (Plan 02) and runner (Plan 03)
- DiscoveryRepository provides all persistence methods needed by the discovery runner
- HtmlStorage results page methods ready for archiving fetched results pages
- Full unit test suite (105 tests) passing with zero regressions

---
*Phase: 04-match-discovery*
*Completed: 2026-02-15*
