---
phase: 06-map-stats-extraction
plan: 01
subsystem: parsing
tags: [beautifulsoup, html-parsing, scoreboard, round-history, rating-detection, dataclasses]

# Dependency graph
requires:
  - phase: 03-page-reconnaissance
    provides: "CSS selector map (map-stats.md) and 12 HTML samples"
  - phase: 05-match-overview-extraction
    provides: "match_parser.py pattern (pure function, dataclasses, BeautifulSoup)"
provides:
  - "parse_map_stats(html, mapstatsid) -> MapStats pure function"
  - "PlayerStats, RoundOutcome, MapStats dataclasses"
  - "Rating 2.0 vs 3.0 detection and handling"
  - "Round history extraction for all 3 OT patterns"
affects:
  - 06-map-stats-extraction (plans 02, 03 -- repository and orchestrator)
  - 07-performance-and-economy (parser pattern)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure function parser: HTML + ID in, dataclass out"
    - "Compound stat parsing: '14(9)' -> (kills, hs_kills)"
    - "OUTCOME_MAP dict for round history image-to-enum mapping"
    - "NavigableString iteration for bare text nodes (map name)"

key-files:
  created:
    - src/scraper/map_stats_parser.py
    - tests/test_map_stats_parser.py
  modified: []

key-decisions:
  - "All td selectors use short class (e.g. td.st-kills) not full compound class -- works for both traditional-data and non-suffixed columns"
  - "KAST has two td elements per row (gtSmartphone-only and smartphone-only); select_one picks first (gtSmartphone-only) which is correct"
  - "Rating 2.0 pages have all traditional-data columns except st-roundSwing; no special fallback logic needed beyond None for round_swing"

patterns-established:
  - "Map stats parser follows identical pattern to match_parser.py: pure function, _extract_* helpers, dataclass return"
  - "Test file mirrors test_match_parser.py: load_sample helper, class-per-concern, parametrized smoke test"

# Metrics
duration: 8min
completed: 2026-02-16
---

# Phase 6 Plan 1: Map Stats Parser Summary

**Pure-function parser extracting per-player scoreboards (10 players, 18+ fields each) and round-by-round history from HLTV map stats pages, handling Rating 2.0/3.0 and all 3 overtime patterns**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-15T22:58:59Z
- **Completed:** 2026-02-15T23:07:18Z
- **Tasks:** 2/2
- **Files created:** 2

## Accomplishments
- Pure function `parse_map_stats(html, mapstatsid)` returning structured `MapStats` dataclass with full scoreboard and round history
- Rating 2.0 vs 3.0 auto-detection via `th.st-rating` text, with `round_swing=None` for 2.0 pages
- Round history handles all 3 patterns: standard (1 container, <=24 rounds), single OT (1 container, 30 rounds), extended OT (2 containers, 36 rounds)
- 51 tests across 9 classes, all passing against 12 real HTML samples

## Task Commits

Each task was committed atomically:

1. **Task 1: Create map_stats_parser.py with dataclasses and pure function parser** - `8d4684b` (feat)
2. **Task 2: Create comprehensive tests against all 12 recon samples** - `8be6c9d` (test)

## Files Created/Modified
- `src/scraper/map_stats_parser.py` - Pure function parser with 3 dataclasses (MapStats, PlayerStats, RoundOutcome), 5 internal _extract helpers, OUTCOME_MAP constant
- `tests/test_map_stats_parser.py` - 51 tests: scoreboard extraction (11 tests), Rating 2.0 (5), Rating 3.0 (3), round history standard (6), single OT (3), extended OT (3), metadata (5), half breakdown (3), parametrized smoke (12)

## Decisions Made
- Used short CSS selectors (e.g., `td.st-kills` instead of `td.st-kills.traditional-data`) which correctly match the first occurrence in both Rating 2.0 and 3.0 pages
- Compound stats like "14(9)" parsed via regex `(\d+)\((\d+)\)` rather than navigating span children -- simpler and works consistently
- Rating 2.0 pages confirmed to have all traditional-data columns (opkd, mks, clutches, kast, etc.) except st-roundSwing -- no special-case fallback needed beyond `round_swing=None`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Parser ready for Plan 06-02 (repository layer) and Plan 06-03 (orchestrator)
- MapStats dataclass provides all fields needed for database persistence
- All 12 recon samples verified; parser is production-ready

---
*Phase: 06-map-stats-extraction*
*Completed: 2026-02-16*
