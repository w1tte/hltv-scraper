---
phase: 03-page-reconnaissance
plan: 02
subsystem: page-analysis
tags: [hltv, css-selectors, results-listing, reconnaissance, beautifulsoup]

dependency_graph:
  requires: [03-01]
  provides: [results-listing-selector-map]
  affects: [04-match-discovery]

tech_stack:
  added: []
  patterns: [programmatic-selector-verification, annotated-html-documentation]

key_files:
  created:
    - .planning/phases/03-page-reconnaissance/recon/results-listing.md
  modified: []

decisions:
  - id: "03-02-skip-big-results"
    description: "Big-results featured section (page 1 only) should be skipped by parsers -- entries are exact duplicates of regular results"
  - id: "03-02-map-text-encodes-format"
    description: "map-text field encodes both format (bo3/bo5) and BO1 map name (nuke/ovp/mrg) and forfeit status (def)"
  - id: "03-02-last-results-all"
    description: "Parser should select the LAST .results-all container on the page to skip big-results on page 1"
  - id: "03-02-timestamp-on-result-con"
    description: "data-zonedgrouping-entry-unix is on each .result-con div (not date sublist), absent on big-results entries"

metrics:
  duration: "~7 min"
  completed: "2026-02-15"
---

# Phase 3 Plan 02: Results Listing Page Analysis Summary

**One-liner:** Complete CSS selector map for HLTV /results pages -- 20 selectors verified across 3 samples, pagination mechanics documented, big-results duplication and forfeit detection patterns identified.

## What Was Done

### Task 1: Programmatic selector discovery and verification

Loaded all 3 results listing HTML samples (offset 0, 100, 5000) with BeautifulSoup and systematically discovered and verified CSS selectors for every visible field on the page.

**Analysis covered:**
1. **Page structure:** `.results-all`, `.results-sublist`, `.big-results`, `.result-con` hierarchy
2. **Per-match fields:** team names, scores, winner indicator, map/format, stars, event name, match URL, timestamp
3. **Pagination:** `.pagination-component` with offset mechanics, stop conditions, total count
4. **Structural observations:** big-results duplication, day/night logo variants, forfeit entries, BO1 map abbreviations

**Output:** 458-line selector map document at `.planning/phases/03-page-reconnaissance/recon/results-listing.md` with:
- Field-by-field selector table with CSS paths, data types, optionality, and example values
- Annotated HTML snippets for regular entries, starred entries, BO1 entries, forfeit entries, date groups, and pagination
- Selector verification table showing counts across all 3 samples
- Recommended extraction strategy with Python code sketch
- Edge case documentation and map abbreviation reference

## Key Findings

1. **Big-results entries are duplicates:** The featured section on page 1 (offset=0) contains 8 entries that are exact duplicates of entries in the regular listing. Parsers must skip `.big-results` or use the last `.results-all` container to avoid double-counting.

2. **Map-text encodes format AND map name:** For BO3/BO5 series the value is `bo3`/`bo5`. For BO1 matches it shows an abbreviated map name (e.g., `nuke`, `ovp`, `mrg`). For forfeits it shows `def`. This single field replaces what would otherwise be separate "format" and "map" fields.

3. **Timestamps only on regular entries:** The `data-zonedgrouping-entry-unix` attribute exists on each regular `.result-con` but is absent on big-results entries. This is a millisecond Unix timestamp.

4. **Star-cell structure varies by star count:** When 0 stars, the `.map-and-stars` wrapper and `.stars` div are entirely absent -- `.map-text` sits directly in `.star-cell`. When stars > 0, the structure nests `.map-text` inside `.map-and-stars`. This doesn't affect extraction (`.stars i` count returns 0 correctly) but is worth noting.

5. **No LAN/online indicator on results page:** The results listing does not expose whether a match was LAN or online. This information is only available on the match overview page.

6. **Day/night logo variants:** ~30% of teams have two logo images (`.day-only` and `.night-only`), explaining why `img.team-logo` counts exceed entry counts. Not relevant for data extraction.

7. **Forfeit entries use normal score format:** Forfeits show `1 - 0` with standard `score-won`/`score-lost` classes. The only distinguishing feature is `map-text == "def"`.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Skip `.big-results`, use last `.results-all` | Avoids double-counting; big-results entries are exact duplicates |
| Map-text as single format/map field | HLTV overloads this field; parser can branch on value (bo3/bo5/def/map-name) |
| Timestamp from `data-zonedgrouping-entry-unix` on `.result-con` | More precise than date headline; per-entry rather than per-group |
| Pagination stop: check `.pagination-next.inactive` | Simplest and most reliable; also parse total from `.pagination-data` text |

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

| Check | Result |
|-------|--------|
| results-listing.md exists | 458 lines -- PASS |
| Selector table with CSS selectors, types, optionality, examples | Present for all fields -- PASS |
| Annotated HTML snippets | 6 annotated snippets -- PASS |
| Pagination section with offset mechanics and stop conditions | Documented with 3 stop conditions -- PASS |
| Selectors verified across all 3 samples | Verification table with counts -- PASS |
| All fields marked with extraction status | extract/skip/future markers on every field -- PASS |
| 100+ lines minimum | 458 lines -- PASS |

## Next Phase Readiness

The results listing selector map is ready for Phase 4 (Match Discovery) to consume directly. No blockers identified. The document includes a Python code sketch showing the recommended extraction pattern.
