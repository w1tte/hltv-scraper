---
phase: 07-performance-and-economy-extraction
plan: 03
subsystem: parsing
tags: [economy, fusionchart, json, beautifulsoup, buy-type, ct-t-side]

# Dependency graph
requires:
  - phase: 03-page-reconnaissance
    provides: "12 economy HTML samples + selector map (map-economy.md)"
  - phase: 06-map-stats-extraction
    provides: "Pure-function parser pattern (map_stats_parser.py)"
provides:
  - "parse_economy() pure function for economy page extraction"
  - "EconomyData and RoundEconomy dataclasses"
  - "Buy type classification using HLTV thresholds (full_eco/semi_eco/semi_buy/full_buy)"
  - "CT/T side inference from FusionChart anchor images"
affects:
  - 07-04-performance-economy-orchestrator
  - future phases needing economy data

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FusionChart JSON extraction for economy data via data-fusionchart-config attribute"
    - "Side inference: winner's anchorImageUrl determines both teams' CT/T sides per round"

key-files:
  created:
    - src/scraper/economy_parser.py
    - tests/test_economy_parser.py
  modified: []

key-decisions:
  - "Buy type categories: full_eco/semi_eco/semi_buy/full_buy replace original placeholder names (eco/force/full/pistol) from schema comment"
  - "Equipment values from FusionChart 'value' field (not 'displayValue') -- economy chart stores actual dollar amounts directly"
  - "Side inference via round_sides dict: winner's anchor determines both teams' sides for each round"

patterns-established:
  - "Economy FusionChart extraction: select worker-ignore.graph[data-fusionchart-config], json.loads, iterate dataset[].data[]"
  - "Buy type thresholds: <$5K=full_eco, $5K-$10K=semi_eco, $10K-$20K=semi_buy, $20K+=full_buy"

# Metrics
duration: 4min
completed: 2026-02-16
---

# Phase 7 Plan 3: Economy Page Parser Summary

**Pure-function economy parser extracting per-round equipment values, buy types, and CT/T side from FusionChart JSON across all 12 recon samples**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-16T00:20:59Z
- **Completed:** 2026-02-16T00:24:42Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- Economy parser extracts per-round equipment values for both teams from FusionChart JSON embedded in HTML
- Buy type classification using HLTV's own threshold trendlines: full_eco (<$5K), semi_eco ($5K-$10K), semi_buy ($10K-$20K), full_buy ($20K+)
- CT/T side inference from anchorImageUrl -- winner's anchor determines both teams' sides per round
- OT handling: MR15 matches show all rounds (30 for 16-14), MR12 OT shows regulation only (24 max)
- 71 tests across 6 test classes, all passing against 12 real HTML samples

## Task Commits

Each task was committed atomically:

1. **Task 1: Economy page parser implementation** - `b84ae9c` (feat)
2. **Task 2: Economy parser test suite** - `b81da08` (test)

## Files Created/Modified
- `src/scraper/economy_parser.py` - Pure function parser: parse_economy(html, mapstatsid) -> EconomyData with per-round equipment values, buy types, side inference
- `tests/test_economy_parser.py` - 71 tests: per-round extraction, buy type boundaries, round outcomes, OT handling, team attribution, all-samples smoke tests

## Decisions Made
- Buy type categories use `full_eco`, `semi_eco`, `semi_buy`, `full_buy` (canonical names derived from HLTV trendlines, replacing placeholder names `eco`/`force`/`full`/`pistol` from original schema comment)
- Economy FusionChart uses `value` directly as equipment value (unlike performance page where `value` is normalized and `displayValue` has the actual stat)
- Side inference builds a round_sides dict from winner anchors, then assigns both teams' sides -- loser's side is opposite of winner's
- `_classify_buy_type` exposed for direct unit testing of threshold boundaries

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Economy parser ready for integration into Phase 7 orchestrator (07-04)
- Exports: `parse_economy`, `EconomyData`, `RoundEconomy` from `scraper.economy_parser`
- Economy FK to round_history means orchestrator must only process maps where Phase 6 has already completed (round_history rows exist)

---
*Phase: 07-performance-and-economy-extraction*
*Completed: 2026-02-16*
