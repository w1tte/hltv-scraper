---
phase: 05-match-overview-extraction
plan: 02
subsystem: parser
tags: [beautifulsoup, html-parsing, dataclasses, match-overview, css-selectors]
depends_on:
  requires: [03-03, 05-01]
  provides: [parse_match_overview, MatchOverview, MapResult, VetoStep, PlayerEntry]
  affects: [05-03, 06-01, 06-02]
tech_stack:
  added: []
  patterns: [pure-function-parser, dataclass-return-types, regulation-only-half-scores]
key_files:
  created:
    - src/scraper/match_parser.py
    - tests/test_match_parser.py
  modified: []
decisions:
  - id: 05-02-01
    description: "Scores stored as raw .won/.lost values (BO1 gets round scores like 16/14, BO3/BO5 gets maps-won like 2/1; best_of column disambiguates)"
  - id: 05-02-02
    description: "Half scores are regulation-only; OT spans (no ct/t class) excluded from team1_ct/t and team2_ct/t columns"
  - id: 05-02-03
    description: "Unplayed map detection uses .optional child element inside .mapholder (not a class on mapholder itself)"
metrics:
  duration: "~8 min"
  completed: "2026-02-15"
---

# Phase 5 Plan 2: Match Overview Parser Summary

**One-liner:** Pure-function parser extracting teams, scores, maps, vetoes, rosters, and half-scores from HLTV match overview HTML using BeautifulSoup CSS selectors verified against 9 real samples.

## What Was Done

### Task 1: Create match_parser.py with parse_match_overview function
- Created `src/scraper/match_parser.py` (316 lines) with 4 dataclasses and 1 public function:
  - `MatchOverview`: top-level result with match metadata, maps, vetoes, players, forfeit flag
  - `MapResult`: per-map data including mapstatsid, scores, half-score CT/T breakdown, unplayed/forfeit flags
  - `VetoStep`: step number, team name (None for "left over"), action, map name
  - `PlayerEntry`: player ID, name, team ID, team number (1 or 2)
  - `parse_match_overview(html, match_id) -> MatchOverview`: pure function, no side effects
- Internal helpers: `_extract_match_metadata`, `_extract_maps`, `_parse_half_scores`, `_extract_vetoes`, `_extract_rosters`
- Half-score parsing correctly identifies regulation-only CT/T rounds by checking span CSS classes (ct/t for regulation, no class for OT)
- Forfeit detection: `is_forfeit = any(m.map_name == "Default" for m in maps)`
- Score extraction handles both .won and .lost elements, returns None when neither exists (full forfeit)
- Error handling: ValueError on missing required fields (team names, IDs, date, event); warnings + defaults on optional fields

### Task 2: Comprehensive tests against 9 real HTML samples
- Created `tests/test_match_parser.py` (320 lines) with 68 tests across 11 test classes:
  - `TestMatchMetadata` (10 tests): team names, IDs, scores, best_of, LAN flag, date, event, match_id
  - `TestBO1Match` (5 tests): best_of=1, single map, round scores, mapstatsid, online flag
  - `TestBO5Match` (6 tests): best_of=5, 5 maps, unplayed maps, forfeit map, scores
  - `TestForfeitMatch` (6 tests): forfeit flag, None scores, forfeit map detection, no mapstatsids, players still present, vetoes present
  - `TestMapExtraction` (5 tests): map count, names, scores, mapstatsids, sequential numbers
  - `TestUnplayedMaps` (5 tests): null scores, null mapstatsid, is_unplayed flag, played maps have scores
  - `TestHalfScores` (3 tests): all played maps have half scores, sum validation, reasonable values (0-13)
  - `TestOvertimeHalfScores` (4 tests): regulation halves present, total > 24, ct+t <= 12 per team, regulation < total
  - `TestVetoExtraction` (7 tests): vetoes present, 7 steps, sequential, valid actions, team names, left_over null team, map names
  - `TestRosterExtraction` (5 tests): 10 players, 5 per team, positive IDs, non-empty names, team IDs match
  - `TestAllSamplesParseWithoutCrash` (9 tests): parametrized smoke test across all 9 samples
  - `TestBO1LAN` (3 tests): LAN flag, best_of=1, single map

**Test results:** 68/68 passing in ~272 seconds, zero failures.

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 05-02-01 | Store raw .won/.lost values as team scores | Simpler parser (no special BO1 translation to 1/0); best_of column disambiguates whether value means "maps won" or "round score" |
| 05-02-02 | Half scores regulation-only | OT spans have no ct/t CSS class, making them structurally distinct; total rounds (team1_rounds/team2_rounds) already include OT |
| 05-02-03 | Unplayed detection via .optional child element | Verified against real samples: `.optional` is a child div, not a class on `.mapholder` itself |

## Deviations from Plan

None -- plan executed exactly as written.

## Commit Log

| Hash | Type | Description |
|------|------|-------------|
| 03dfa32 | feat | Create match overview parser with dataclasses |
| 3156560 | test | Add comprehensive match parser tests against 9 HTML samples |

## Next Phase Readiness

Plan 05-03 (overview orchestrator) can proceed immediately. All components are ready:
- `parse_match_overview()` returns structured data for any match overview HTML
- Repository `upsert_match_overview()` from 05-01 accepts the parsed data for atomic DB writes
- `get_pending_matches()` and `update_status()` from 05-01 provide queue management
- Parser handles all edge cases: forfeit, BO1, BO3, BO5, overtime, unplayed maps, unranked teams
- All 9 recon samples parse without crash
