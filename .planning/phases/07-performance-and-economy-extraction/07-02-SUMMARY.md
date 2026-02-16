---
phase: 07-performance-and-economy-extraction
plan: 02
subsystem: parsing
tags: [performance, fusionchart, json, beautifulsoup, kill-matrix, rating-detection]

# Dependency graph
requires:
  - phase: 03-page-reconnaissance
    provides: "12 performance HTML samples + selector map (map-performance.md)"
  - phase: 06-map-stats-extraction
    provides: "Pure-function parser pattern (map_stats_parser.py)"
provides:
  - "parse_performance() pure function for performance page extraction"
  - "PerformanceData, PlayerPerformance, KillMatrixEntry, TeamOverview dataclasses"
  - "Rating 2.0/3.0 detection via FusionChart last bar label"
  - "Kill matrix extraction for all 3 types (all, first_kill, awp)"
affects:
  - 07-04-performance-economy-orchestrator
  - future phases needing player rate metrics or kill matrix data

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FusionChart JSON extraction for player metrics via data-fusionchart-config attribute"
    - "displayValue (NOT value) for actual stat values from FusionChart bars"
    - "Safe float parsing with _safe_float() to handle dash '-' values in FusionChart displayValue"

key-files:
  created:
    - src/scraper/performance_parser.py
    - tests/test_performance_parser.py
  modified: []

key-decisions:
  - "Rating detection uses last FusionChart bar label ('Rating 2.0' or 'Rating 3.0') -- reliable across all 12 samples"
  - "Kill matrix uses combined regex for both player URL patterns: /player/{id}/ and /stats/players/{id}/"
  - "Dash '-' displayValue treated as 0.0 (found in sample 206393, player ben1337 ADR field)"
  - "Team names extracted from overview table header img.team-logo[alt] attribute"

patterns-established:
  - "FusionChart bar_map pattern: {bar['label']: bar['displayValue'] for bar in bars} for label-based metric lookup"

metrics:
  duration: "~8 min"
  completed: "2026-02-16"
  tests: 66
  test-time: "~139s"
---

# Phase 7 Plan 02: Performance Page Parser Summary

**One-liner:** Pure-function parser extracts KPR/DPR/KAST/ADR/rating from FusionChart JSON with Rating 2.0/3.0 detection, plus 3 kill matrices (75 entries/map) and team overview.

## What Was Done

### Task 1: Performance page parser implementation
Created `src/scraper/performance_parser.py` (445 lines) following the pure-function pattern from `map_stats_parser.py`.

**Dataclasses:** PlayerPerformance, KillMatrixEntry, TeamOverview, PerformanceData
**Main function:** `parse_performance(html: str, mapstatsid: int) -> PerformanceData`
**Internal helpers:**
- `_detect_rating_version()` -- checks first FusionChart element's last bar label
- `_parse_player_cards()` -- extracts 10 players from FusionChart JSON in .standard-box elements
- `_parse_kill_matrix()` -- parses 3 kill matrix types (all/first_kill/awp) from .killmatrix-content
- `_parse_team_overview()` -- extracts team kills/deaths/assists from .overview-table
- `_safe_float()` / `_safe_float_signed()` -- handles dash '-' displayValue edge case

**Commit:** `1f3ddbe`

### Task 2: Performance parser test suite
Created `tests/test_performance_parser.py` (195 lines) with 66 tests across 6 test classes.

**Test classes:**
- TestPlayerMetricsExtraction (8 tests, sample 164779 Rating 3.0)
- TestRating20Handling (6 tests, sample 162345 Rating 2.0)
- TestRating30Handling (5 tests, sample 219128 Rating 3.0)
- TestKillMatrixExtraction (6 tests, sample 164779)
- TestTeamOverview (5 tests, sample 164779)
- TestAllSamplesParseWithoutCrash (36 tests, parametrized across all 12 samples)

**Commit:** `b229de0`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Dash '-' displayValue in FusionChart JSON (sample 206393)**
- **Found during:** Task 2 test run
- **Issue:** Player `ben1337` in sample 206393 has ADR displayValue of "-" instead of a number, causing `float("-")` to fail (ValueError: could not convert string to float: '-')
- **Fix:** Added `_safe_float()` and `_safe_float_signed()` helper functions that treat "-" as 0.0 default. Applied to all metric parsing (KPR, DPR, KAST, ADR, rating, MK rating, Swing, Impact)
- **Files modified:** src/scraper/performance_parser.py
- **Commit:** b229de0 (included in Task 2 commit)

## Verification Results

All 3 verification checks from the plan passed:

1. `pytest tests/test_performance_parser.py -v --tb=short` -- 66/66 tests passed (139s)
2. Rating 3.0 sample 164779: Players=10, KM entries=75, Teams=2, Version=3.0
3. Rating 2.0 sample 162345: Version=2.0, Impact=1.33, MK=None

## Success Criteria Verification

- [x] parse_performance() extracts 10 players with valid KPR, DPR, KAST, ADR, rating
- [x] Rating 2.0 detected correctly (sample 162345): Impact present, MK rating/Swing absent
- [x] Rating 3.0 detected correctly (11 other samples): MK rating/Swing present, Impact absent
- [x] 3 kill matrix types extracted with 25 entries each (75 total per map)
- [x] Team overview extracts 2 teams with valid kill/death/assist totals
- [x] All 12 recon samples parse without errors
- [x] Uses displayValue (not value) from FusionChart JSON

## Next Steps

This parser is ready for integration in the Phase 7 orchestrator (07-04). The orchestrator will:
1. Fetch performance page HTML per mapstatsid
2. Call `parse_performance()` to get structured data
3. UPDATE existing player_stats rows (kpr, dpr, impact/mk_rating columns)
4. INSERT kill_matrix rows for head-to-head data
