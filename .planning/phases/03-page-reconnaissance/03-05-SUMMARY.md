---
phase: 03-page-reconnaissance
plan: 05
subsystem: page-analysis
tags: [hltv, performance-page, css-selectors, rating-version, fusionchart, beautifulsoup]

dependency_graph:
  requires: [03-01]
  provides: [performance-page-selector-map, rating-version-detection]
  affects: [03-07, phase-7-performance-extraction]

tech_stack:
  added: []
  patterns: [fusionchart-json-extraction, dual-rating-version-detection]

key_files:
  created:
    - .planning/phases/03-page-reconnaissance/recon/map-performance.md
  modified: []

decisions:
  - id: "03-05-rating-2-still-exists"
    description: "Rating 2.0 pages still exist on HLTV (1/12 samples: mapstatsid 162345, Sep 2023 tier-3 match) -- parser MUST handle both formats"
  - id: "03-05-fusionchart-primary-source"
    description: "Player performance metrics stored in FusionChart JSON (data-fusionchart-config attribute), not in HTML tables -- use json.loads() for extraction"
  - id: "03-05-eco-adjusted-not-on-performance"
    description: "Eco-adjusted stats (eK-eD, eADR, eKAST) are on the map stats overview page, NOT on the performance page"
  - id: "03-05-rating-detection-via-chart-labels"
    description: "Rating version detected from last FusionChart bar label: 'Rating 2.0' (6 bars) vs 'Rating 3.0' (7 bars)"
  - id: "03-05-no-multikill-clutch-counts"
    description: "Per-map multi-kill round counts (2k-5k) and clutch stats (1v1-1v5) are NOT on the performance page -- may require player stats aggregate pages"

metrics:
  duration: "~14 min"
  completed: "2026-02-15"
---

# Phase 3 Plan 05: Map Performance Page Selector Map Summary

**One-liner:** Complete CSS selector map for HLTV performance page with dual-format Rating 2.0/3.0 detection via FusionChart JSON labels, verified across 12 samples spanning 2023-2026.

## What Was Done

### Task 1: Programmatic selector discovery for performance page with rating version analysis

Loaded all 12 `performance-*.html.gz` samples with BeautifulSoup and systematically discovered, documented, and verified CSS selectors for every element on the HLTV map performance page.

**Key sections documented:**

1. **Page-level metadata** -- sub-page navigation menu (`.stats-match-menu`), map tabs (`.stats-match-maps`), event name
2. **Performance overview table** -- `.overview-table` with Kills/Deaths/Assists per team, team logos in header
3. **Kill matrix** -- 3 types (All/First kills/AWP kills) in `.killmatrix-content` divs (all present in initial HTML, hidden ones toggled by CSS class); 5x5 player-vs-player grid with `.team1-player-score` and `.team2-player-score` spans
4. **Player performance overview** -- 10 player cards (5 per team) each with FusionChart bar graph data in `data-fusionchart-config` JSON attribute
5. **Eco-adjusted stats** -- confirmed NOT present on performance page (exists only on map stats overview page)
6. **Rating version comparison** -- side-by-side column analysis with concrete HTML evidence

**Output:** `.planning/phases/03-page-reconnaissance/recon/map-performance.md` (872 lines)

## Key Findings

1. **Rating 2.0 pages still exist on HLTV.** Sample 162345 (n00rg vs FALKE, September 2023, tier-3 match) uses Rating 2.0 format with 6 bars: KPR, DPR, KAST, Impact, ADR, Rating 2.0. All other 11 samples use Rating 3.0 with 7 bars: KPR, DPR, KAST, MK rating, Swing, ADR, Rating 3.0. The retroactive Rating 3.0 application was NOT universal -- the parser must handle both formats.

   **This CORRECTS the prior 03-01 finding** that "all pages use Rating 3.0." The 03-01 conclusion was based on the map stats overview page headline text ("Performance - rating 3.0"), which is present on all pages. However, the actual performance page chart data can still show Rating 2.0 metrics for some older matches.

2. **FusionChart JSON is the primary data source.** Unlike other HLTV pages where data lives in HTML tables with CSS classes (`.st-kills`, `.st-rating`), the performance page stores ALL per-player metrics in JSON embedded in `data-fusionchart-config` attributes. Key distinction: `value` is the normalized chart bar height, `displayValue` is the actual statistic to extract.

3. **Eco-adjusted stats are NOT on the performance page.** Exhaustive search across all 12 samples found zero instances of eK-eD, eADR, eKAST, or eco-adjusted toggle. These exist only on the map stats overview page. Phase 7 should not attempt eco-adjusted extraction from performance pages.

4. **Multi-kill counts and clutch stats are NOT on the performance page.** The plan expected columns for opening kills/deaths, 2k/3k/4k/5k counts, and 1v1-1v5 clutch stats. These are absent. The performance page provides only rates (KPR, DPR, KAST%) and ratings (MK rating, Swing, ADR, overall Rating), plus kill matrices.

5. **All selectors are consistent across all 12 samples.** Every selector tested returned the expected count on every sample. The only variation is map tab count (0 for BO1, 3-4 for BO3) and page size (1 sample at 219K chars vs 11 at ~6.2M chars, but structure is identical).

6. **Player ID extraction uses two different URL patterns.** Player cards use `/player/{id}/{slug}` while kill matrix uses `/stats/players/{id}/{slug}`. Both contain the same numeric ID.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Parser must handle Rating 2.0 AND 3.0 | 1/12 samples (tier-3, Sep 2023) retains Rating 2.0 format |
| Detect rating via FusionChart JSON last bar label | "Rating 2.0" vs "Rating 3.0" is unambiguous; bar count (6 vs 7) is secondary signal |
| Extract metrics from FusionChart JSON, not DOM text | All metrics are in `data-fusionchart-config` JSON with clean key-value structure |
| Skip eco-adjusted extraction from performance page | Data simply does not exist here; map stats overview page is the source |
| Skip multi-kill counts and clutch stats from performance page | Not present; may need player aggregate pages |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Prior Rating 3.0 universality assumption incorrect**
- **Found during:** Task 1 cross-era comparison
- **Issue:** STATE.md and 03-01-SUMMARY.md stated "all pages use Rating 3.0" based on page headline text. However, sample 162345 (Sep 2023) has Rating 2.0 FusionChart data (6 bars with "Impact" and "Rating 2.0" labels), contradicting this assumption.
- **Fix:** Documented the dual-format requirement and provided a concrete detection strategy. The parser now needs dual-format handling.
- **Impact:** Phase 7 performance parser must implement rating version detection and handle both 6-bar and 7-bar formats.

**2. [Rule 2 - Missing Critical] Plan expected columns not present on performance page**
- **Found during:** Task 1 DOM analysis
- **Issue:** The plan expected opening kills/deaths, multi-kill round counts (2k-5k), and clutch stats (1v1-1v5) on the performance page. These columns do not exist here.
- **Fix:** Documented which data IS available (rates and ratings via FusionChart, kill matrices) and noted where the missing data might be found (map stats overview page or player aggregate pages).
- **Impact:** Phase 7 scope adjustment needed -- some expected data requires different source pages.

## Verification Results

| Check | Result |
|-------|--------|
| File exists and is 200+ lines | 872 lines -- PASS |
| All performance metrics have CSS selectors | 9/9 metrics documented -- PASS |
| Rating version section has concrete HTML evidence | Side-by-side 2.0 vs 3.0 with JSON snippets -- PASS |
| Detection strategy is specific and implementable | `detect_rating_version()` with JSON parsing -- PASS |
| Eco-adjusted stats toggle behavior documented | Confirmed absent from performance page -- PASS |
| Selectors tested against samples from 2+ eras | All 12 samples (2023-2026) verified -- PASS |
| Document sufficient for Phase 7 parser | Includes extraction pseudocode and field tables -- PASS |

## Next Phase Readiness

The performance page selector map is complete. Remaining Phase 3 plans:
- 03-03 (Match overview): Can proceed independently
- 03-04 (Map stats): Can proceed independently
- 03-07 (Edge cases + cross-page synthesis): Blocked on 03-03, 03-04, and 03-05 (this plan)

**Blocker for Phase 7:** The Rating 2.0 finding means the performance parser needs dual-format handling. This affects DB schema decisions (separate columns for Impact vs MK rating + Swing).
