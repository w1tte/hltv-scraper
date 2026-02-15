---
phase: 05-match-overview-extraction
plan: 03
subsystem: orchestrator
tags: [async, orchestrator, fetch-first-batch, pipeline, mocked-tests]
depends_on:
  requires: [05-01, 05-02]
  provides: [run_match_overview, overview-pipeline]
  affects: [06-01, 07-01, 08-01]
tech_stack:
  added: []
  patterns: [fetch-first-batch, batch-discard-on-fetch-failure, per-match-parse-failure, async-orchestrator]
key_files:
  created:
    - src/scraper/match_overview.py
    - tests/test_match_overview.py
  modified:
    - src/scraper/config.py
decisions:
  - id: 05-03-01
    description: "Fetch failures discard entire batch; queue entries remain pending for retry"
  - id: 05-03-02
    description: "Parse/persist failures are per-match; failed matches get status='failed', others continue"
  - id: 05-03-03
    description: "Date conversion from unix ms to ISO 8601 YYYY-MM-DD for DB storage"
metrics:
  duration: "~9 min"
  completed: "2026-02-15"
---

# Phase 5 Plan 3: Overview Orchestrator Summary

**One-liner:** Async orchestrator wiring fetch/store/parse/persist into fetch-first batch pipeline with batch-level fetch failure discard and per-match parse failure handling.

## What Was Done

### Task 1: Add batch_size config and create orchestrator
- Added `overview_batch_size: int = 10` field to ScraperConfig dataclass
- Created `src/scraper/match_overview.py` (161 lines) with `run_match_overview()` async function
- Follows the same pattern as `run_discovery` in `discovery.py`: untyped parameters, logging, stats dict return
- **Fetch phase**: Iterates pending queue entries, builds full URL from base_url + relative URL, fetches via client.fetch(), saves raw HTML via storage.save(). On ANY fetch failure, logs error, returns stats with fetch_errors count, does NOT update queue statuses (entire batch discarded).
- **Parse/persist phase**: Loads stored HTML, parses with parse_match_overview(), converts date from unix ms to ISO 8601, builds match/maps/vetoes/players dicts with provenance fields, calls match_repo.upsert_match_overview() atomically, updates queue status to 'scraped'. On parse/persist failure, marks individual match as 'failed' and continues.
- Returns stats dict: batch_size, fetched, parsed, failed, fetch_errors

### Task 2: Create orchestrator unit tests
- Created `tests/test_match_overview.py` (318 lines) with 7 tests in TestRunMatchOverview class
- Tests use mocked HLTVClient (AsyncMock for fetch) with real HTML samples from data/recon/
- Real in-memory database instances for repository/storage (full parse-to-persist verification)
- Tests cover:
  - `test_fetches_parses_persists_match`: Full pipeline with match/maps/vetoes/players in DB, queue status='scraped'
  - `test_no_pending_matches_returns_early`: Empty queue, client.fetch never called
  - `test_fetch_failure_discards_batch`: Second fetch fails, both entries remain 'pending', no data in DB
  - `test_parse_failure_marks_individual_failed`: Good HTML for first match, garbage for second; first='scraped', second='failed'
  - `test_forfeit_match_persisted_correctly`: Forfeit match with Default map, no mapstatsids
  - `test_stats_dict_returned`: All expected keys present in returned dict
  - `test_date_converted_to_iso`: Date column is YYYY-MM-DD format

**Test results:** 7/7 passing, 190/194 total unit tests passing (4 pre-existing test_db.py failures from migration 003 schema version count mismatch).

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 05-03-01 | Batch-level fetch failure discard | Per CONTEXT.md: fetch failures may indicate Cloudflare detection; safer to discard batch and retry later than persist partial results |
| 05-03-02 | Per-match parse/persist failure | Parse failures are likely data-specific (bad HTML structure for one match); other matches in batch are unaffected |
| 05-03-03 | Date as YYYY-MM-DD string | Matches table date column stores ISO 8601 date; unix ms timestamp converted via datetime.fromtimestamp() |

## Deviations from Plan

None -- plan executed exactly as written.

## Commit Log

| Hash | Type | Description |
|------|------|-------------|
| 9464681 | feat | Add overview orchestrator with fetch-first batch strategy |
| 267b03a | test | Add orchestrator unit tests with mocked client and real DB |

## Next Phase Readiness

Phase 5 is now COMPLETE. All three plans delivered:
- 05-01: Schema extensions (vetoes, match_players tables) and queue management methods
- 05-02: Match overview parser (parse_match_overview pure function)
- 05-03: Overview orchestrator (run_match_overview async pipeline)

Phase 6 (Map Stats Extraction) can proceed. The orchestrator pattern established here (fetch-first batch, per-match error handling, stats dict return) can be reused for map stats, performance, and economy page orchestrators.
