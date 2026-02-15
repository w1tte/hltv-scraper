---
phase: 06-map-stats-extraction
plan: 03
subsystem: orchestration
tags: [async, orchestrator, fetch-first, batch, pipeline, mocked-client]

# Dependency graph
requires:
  - phase: 06-map-stats-extraction
    plan: 01
    provides: "parse_map_stats() pure parser function"
  - phase: 06-map-stats-extraction
    plan: 02
    provides: "get_pending_map_stats() and upsert_map_stats_complete() repository methods"
  - phase: 05-match-overview-extraction
    plan: 03
    provides: "match_overview.py orchestrator pattern (fetch-first batch, stats dict)"
provides:
  - "run_map_stats() async orchestrator wiring fetch-store-parse-persist pipeline"
  - "Full test coverage with mocked client and real DB (6 tests)"
affects:
  - 07-performance-and-economy (orchestrator pattern reuse)
  - 08-pipeline-composition (run_map_stats integration into main loop)

# Tech tracking
tech-stack:
  added: []
  patterns: ["fetch-first batch orchestrator", "per-item error handling with batch-level fetch discard"]

# File tracking
key-files:
  created:
    - src/scraper/map_stats.py
    - tests/test_map_stats.py
  modified: []

# Decisions
decisions:
  - id: "06-03-url-slug"
    summary: "MAP_STATS_URL_TEMPLATE uses '/x' as placeholder slug -- HLTV routes by numeric mapstatsid only"
  - id: "06-03-no-discovery-repo"
    summary: "run_map_stats takes no discovery_repo parameter (unlike match_overview.py) -- pending state derived from data presence, not scrape_queue status"
  - id: "06-03-seed-helper"
    summary: "Test seed helper uses direct SQL INSERT with all NOT NULL columns (match_id, date, team IDs/names, scraped_at, updated_at) rather than repository convenience methods"

# Metrics
metrics:
  duration: "24 min"
  completed: "2026-02-16"
  tasks_completed: 2
  tasks_total: 2
  test_count: 6
  test_pass: 6
---

# Phase 6 Plan 3: Map Stats Orchestrator Summary

Async orchestrator wiring fetch-store-parse-persist pipeline for map stats pages using fetch-first batch strategy with per-map error handling.

## What Was Built

### src/scraper/map_stats.py (170 lines)
- `run_map_stats(client, match_repo, storage, config) -> dict` async orchestrator
- Follows exact `match_overview.py` pattern: fetch-first batching, stats dict return
- Fetch phase: gets all pending maps via `get_pending_map_stats()`, fetches HTML from HLTV, stores raw via `HtmlStorage.save()`
- On ANY fetch failure: discard entire batch, return stats with `fetch_errors=1` (maps remain pending for retry)
- Parse phase: per-map error handling -- `parse_map_stats()` extracts scoreboard + round history
- Persist phase: builds player_stats and round_history dicts, writes atomically via `upsert_map_stats_complete()`
- Rating 2.0/3.0 handling: routes `ps.rating` to `rating_2` or `rating_3` column based on `ps.rating_version`
- Phase 7 columns (kpr, dpr, impact) left as None -- populated by performance page parser later

### tests/test_map_stats.py (266 lines)
- 6 tests covering full pipeline with mocked `HLTVClient` and real SQLite database
- `test_fetches_parses_persists_map_stats`: full pipeline, verifies 10 player_stats rows and round_history rows written
- `test_no_pending_maps_returns_early`: empty batch, `client.fetch` never called
- `test_fetch_failure_discards_batch`: second fetch raises, no data persisted, both maps remain pending
- `test_parse_failure_continues_batch`: garbage HTML for one map, good map still persisted, bad map stays pending
- `test_raw_html_stored`: verifies `storage.exists()` and `storage.load()` after run
- `test_stats_dict_has_all_keys`: verifies returned dict shape

## Decisions Made

1. **URL slug placeholder**: `MAP_STATS_URL_TEMPLATE = "/stats/matches/mapstatsid/{mapstatsid}/x"` uses `/x` as slug -- HLTV routes by numeric ID, slug is cosmetic.
2. **No discovery_repo parameter**: Unlike `match_overview.py` which updates `scrape_queue` status, `run_map_stats` derives processing state from data presence (maps with player_stats = done). Simpler interface.
3. **Test seed uses raw SQL**: `seed_match_with_maps()` inserts directly via `conn.execute()` with all NOT NULL columns. This avoids coupling tests to repository write methods being tested elsewhere.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed seed helper missing NOT NULL updated_at column**
- **Found during:** Task 2 (first test run)
- **Issue:** Seed SQL for matches and maps tables omitted `updated_at` column which has NOT NULL constraint in schema
- **Fix:** Added `updated_at` parameter to both INSERT statements in `seed_match_with_maps()`
- **Files modified:** tests/test_map_stats.py
- **Commit:** 3f24b9f (included in Task 2 commit)

## Verification

1. `python -c "from scraper.map_stats import run_map_stats"` -- OK
2. `pytest tests/test_map_stats.py -v` -- 6/6 passed (13.4s)
3. `pytest tests/test_map_stats_parser.py tests/test_map_stats.py tests/test_repository.py -v` -- 97/97 passed
4. `pytest tests/ -m "not integration" -q` -- 260 passed, 4 deselected (755s)

## Next Phase Readiness

Phase 6 (Map Stats Extraction) is now complete (3/3 plans delivered):
- 06-01: Parser (`parse_map_stats()` pure function)
- 06-02: Repository (`get_pending_map_stats()`, `upsert_map_stats_complete()`, config field)
- 06-03: Orchestrator (`run_map_stats()` async pipeline)

Ready for Phase 7 (Performance + Economy extraction) which will:
- Add performance page parser for kpr, dpr, impact, kill matrix
- Add economy page parser for per-round equipment values and buy types
- Update player_stats rows (fill in kpr/dpr/impact Phase 7 columns)
- Insert economy table rows
