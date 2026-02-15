---
phase: 03-page-reconnaissance
plan: 04
subsystem: documentation
tags: [hltv, css-selectors, map-stats, scoreboard, round-history, beautifulsoup]

dependency_graph:
  requires:
    - phase: 03-01
      provides: "12 gzipped map stats HTML samples in data/recon/"
  provides:
    - "Complete CSS selector map for /stats/matches/mapstatsid/{id}/{slug} pages"
    - "Per-player scoreboard column documentation (17 columns, Rating 2.0 vs 3.0 differences)"
    - "Round history DOM structure with 3 overtime patterns"
    - "CT/T side round extraction method via breakdown row color spans"
  affects: [06-map-stats-extraction, 07-edge-cases]

tech_stack:
  added: []
  patterns: [programmatic-selector-verification, sample-manifest-cross-reference]

key_files:
  created:
    - .planning/phases/03-page-reconnaissance/recon/map-stats.md
    - scripts/analyze_map_stats.py
  modified: []

key-decisions:
  - "Rating 2.0 page (162345) lacks st-roundSwing column and has null eco-adjusted values -- parsers must detect rating version"
  - "Map name is a bare text node in match-info-box (no CSS class) -- requires NavigableString iteration"
  - "Single OT inline in one container (30 outcomes); extended OT has separate 'Overtime' container"
  - "OT breakdown in match-info-row is plain text (no ct/t-color spans) unlike regulation halves"
  - "First .stats-table.totalstats = team-left, second = team-right (verified across all 12 samples)"
  - "6 stats tables per page: 2 totalstats (visible) + 2 ctstats (hidden) + 2 tstats (hidden)"

patterns-established:
  - "Selector verification: test every selector against ALL samples programmatically before documenting"
  - "Rating version detection: check th.st-rating text or presence of th.st-roundSwing"

duration: "~13 min"
completed: "2026-02-15"
---

# Phase 3 Plan 04: Map Stats Page Selector Map Summary

**524-line CSS selector map for HLTV map stats pages covering 17 scoreboard columns, 3 OT patterns, 6 round outcome types, and Rating 2.0/3.0 structural differences -- verified against all 12 HTML samples**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-02-15T00:34:58Z
- **Completed:** 2026-02-15T00:47:31Z
- **Tasks:** 1
- **Files created:** 2

## Accomplishments

- Complete CSS selector map with 8 sections covering every extractable field on the map stats page
- Discovered and documented Rating 2.0 vs 3.0 structural differences (1/12 samples uses Rating 2.0 -- no Swing column, null eco-adjusted values)
- Documented 3 distinct overtime patterns: none, single OT (all rounds inline), extended OT (separate container with "Overtime" headline)
- Identified 6 round outcome image types and their game-semantic meanings
- Documented CT/T side extraction from breakdown row color spans with explicit starting-side detection
- Mapped all 17 scoreboard columns including eco-adjusted hidden variants
- Quick reference section for Phase 6 parser development

## Task Commits

Each task was committed atomically:

1. **Task 1: Programmatic selector discovery for map stats page** - `889ea31` (feat)

## Files Created/Modified

- `.planning/phases/03-page-reconnaissance/recon/map-stats.md` - Complete selector map (524 lines) with 8 sections, annotated HTML snippets, verification summary, and Phase 6 quick reference
- `scripts/analyze_map_stats.py` - Temporary analysis script that loads all 12 map stats samples and systematically discovers CSS selectors via BeautifulSoup

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Rating version detected from `th.st-rating` text ("Rating2.0" vs "Rating3.0") | More reliable than match date heuristic; 162345 (Sep 2023) shows 2.0 while later matches show 3.0 |
| Map name extracted via bare text node iteration (not CSS selector) | The map name has no wrapping element -- it's a raw NavigableString child of `.match-info-box` |
| Single OT uses same container as regulation; extended OT gets separate container | Observed directly: 162345 (30 rounds) has 1 container, 206389 (36 rounds) has 2 containers with "Overtime" headline |
| Eco-adjusted data already in HTML (no JS interaction needed) | All 12 samples have `eco-adjusted-data hidden` elements with values; only Rating 2.0 has null values |
| Extract from `.totalstats` tables only (skip `.ctstats`/`.tstats`) | CT/T side breakdowns are available but can be derived from round data; simplifies initial parser |
| Skip stat leader boxes, highlighted player, FusionChart | All are derivable from scoreboard data; not independent data sources |

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

- **`.teamName` selector does not exist on map stats pages:** The plan's expected selector for team names was wrong. Map stats pages use `.team-left a` / `.team-right a` instead of `.teamName` (which exists only on match overview pages). Discovered and documented correctly.
- **Rating 2.0 vs 3.0 divergence:** Sample 162345 (Sep 2023) uses Rating 2.0 with different column structure (no Swing column, null eco-adjusted values). This contradicts the 03-01 finding that "all pages use Rating 3.0". The 03-01 observation was about the "Performance - rating X.X" headline text, but sample 162345 shows "Performance - rating 2.0" in its headline AND Rating 2.0 column structure. The discrepancy is documented for Phase 6 to handle.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Map stats selector map is complete and ready for Phase 6 (Map Stats Extraction) parser development
- The document is self-contained: Phase 6 can build the parser without inspecting HTML
- Rating 2.0/3.0 differences are documented -- parser must handle both column layouts
- Overtime patterns are fully documented with detection strategies

**Concern:** The Rating 2.0 finding on sample 162345 means parsers need conditional logic for the Swing column and eco-adjusted data. This adds complexity but is now well-documented.

---
*Phase: 03-page-reconnaissance*
*Completed: 2026-02-15*
