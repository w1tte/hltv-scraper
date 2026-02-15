---
phase: 03-page-reconnaissance
plan: 07
subsystem: page-analysis
tags: [hltv, cross-page, edge-cases, synthesis, reconnaissance]

dependency_graph:
  requires: [03-02, 03-03, 03-04, 03-05, 03-06]
  provides: [cross-page-data-map, consolidated-edge-cases, extraction-order, rating-detection-strategy]
  affects: [phase-4-results-parser, phase-5-overview-parser, phase-6-stats-parser, phase-7-perf-econ-parser]

tech_stack:
  added: []
  patterns: [canonical-source-recommendation, data-flow-pipeline]

key_files:
  created:
    - .planning/phases/03-page-reconnaissance/recon/cross-page-summary.md
    - .planning/phases/03-page-reconnaissance/recon/edge-cases.md
  modified: []

decisions:
  - id: "03-07-canonical-sources"
    description: "Each overlapping field has a single canonical extraction source: team names from Match Overview, player roster from Match Overview, scoreboard stats from Map Stats, rate metrics from Performance, economy from Economy page"
  - id: "03-07-extraction-order"
    description: "Recommended parser execution order: Results Listing (Phase 4) -> Match Overview (Phase 5) -> Map Stats (Phase 6) -> Performance + Economy (Phase 7). Each phase produces IDs required by the next."
  - id: "03-07-rating-detection"
    description: "Finalized rating version detection: primary signal is th.st-rating text on map stats page ('Rating2.0' vs 'Rating3.0'); secondary is FusionChart last bar label on performance page. Map stats header is preferred because it requires no JSON parsing."
  - id: "03-07-forfeit-early-detection"
    description: "Forfeit maps must be detected at Match Overview parsing time (mapname == 'Default' or missing stats link) to avoid fetching non-existent sub-pages."

metrics:
  duration: "5 min"
  completed: "2026-02-15"
---

# Phase 03 Plan 07: Edge Cases and Cross-Page Synthesis Summary

**Cross-page data overlap map and consolidated edge case reference covering all 5 HLTV page types with canonical source recommendations and detection cheatsheet**

## What Was Done

### Task 1: Cross-Page Data Overlap Map (cross-page-summary.md, 401 lines)

Synthesized findings from all 5 page-type selector maps into a comprehensive data overlap document with 5 sections:

1. **Master Field Inventory** -- Every extractable field listed with checkmarks showing which of the 5 page types it appears on, plus the recommended canonical extraction source with reasoning.

2. **Overlapping Fields Detail** -- For each field appearing on 2+ page types (team names, player IDs, ratings, ADR, KAST, round outcomes, starting side, map scores), documented all selectors, format differences, and recommended extraction source.

3. **Exclusive Fields** -- Fields unique to each page type, categorized by criticality (Critical/Important/Optional). Highlights: mapstatsid and team_id exclusive to Match Overview; KPR/DPR exclusive to Performance; equipment values exclusive to Economy.

4. **Data Flow Diagram** -- Text-based pipeline showing how data flows from Results Listing through Match Overview, Map Stats, and Performance/Economy pages, with the specific fields extracted at each stage.

5. **Extraction Order Recommendation** -- Phases 4-7 should execute in order: Results -> Overview -> Map Stats -> Performance+Economy. Includes duplicate avoidance table specifying which page to extract overlapping fields from and which to skip.

### Task 2: Consolidated Edge Case Reference (edge-cases.md, 531 lines)

Consolidated edge case findings from all 5 analyses into a single reference with 6 sections:

1. **BO1/BO3/BO5 Differences** -- Map holder counts, veto structures, unplayed map detection, results listing format encoding, and performance/economy tab behavior by format.

2. **Overtime Handling** -- Three distinct round history patterns (no OT, single OT inline, extended OT in separate container). Half-score span parsing differences (OT spans lack ct/t classes). Economy OT data availability (present for MR15, missing for MR12).

3. **Forfeit/Walkover Handling** -- Full forfeit vs partial forfeit detection. DOM differences table showing which elements are present/absent. Per-page-type impact matrix. Early detection code pattern for parser implementation.

4. **Rating Version Handling** -- Finalized detection strategy using map stats `th.st-rating` header as primary signal, FusionChart last bar label as secondary. Database storage impact (which columns are NULL by version). Known scope: only 1/12 samples retains Rating 2.0.

5. **Other Edge Cases** -- Big-results duplication, missing timestamps, unranked teams, day/night logos, bare text map name, missing map pick indicators, dual veto-box elements, performance page size variation, economy "Beta" label, different player ID href patterns.

6. **Detection Cheatsheet** -- Quick-reference table with 16 edge cases, their detection method, CSS selector/check, and recommended parser action. Designed for quick lookup during parser development.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Map stats page is canonical for scoreboard data (kills, deaths, ADR, rating, etc.) | All per-player count stats are in one table; avoids FusionChart JSON parsing for redundant data |
| Match overview is canonical for team identity and IDs | Only page with `/team/{id}/` hrefs and `data-player-id` attributes |
| Rating detection uses map stats header as primary signal | Simple CSS selector check (`th.st-rating`), no JSON parsing, available before per-player extraction |
| Forfeit detection at overview parsing time | Prevents wasted requests for non-existent map sub-pages |
| Extraction order: Results -> Overview -> Stats -> Performance/Economy | Each phase produces IDs and context needed by the next |

## Deviations from Plan

None -- plan executed exactly as written.

## Next Phase Readiness

Phase 3 (Page Reconnaissance) is now **complete**. All 7 plans delivered:
- 03-01: Sample fetching and manifest
- 03-02: Results listing selector map
- 03-03: Match overview selector map
- 03-04: Map stats selector map
- 03-05: Performance page selector map
- 03-06: Economy page selector map
- 03-07: Cross-page synthesis and edge cases (this plan)

**Phase 4 can begin immediately.** The following artifacts are ready for parser development:
- 5 page-type selector maps in `recon/`
- Cross-page data overlap map with canonical source recommendations
- Consolidated edge case reference with detection cheatsheet
- 48 HTML samples in `data/recon/` for parser testing (gitignored)
