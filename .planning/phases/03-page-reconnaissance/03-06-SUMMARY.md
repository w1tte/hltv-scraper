---
phase: 03-page-reconnaissance
plan: 06
subsystem: page-analysis
tags: [hltv, economy, fusionchart, selectors, reconnaissance]

dependency_graph:
  requires: [03-01]
  provides: [economy-selector-map, economy-extraction-feasibility]
  affects: [03-07, phase-7-economy-extraction]

tech_stack:
  added: []
  patterns: [fusionchart-json-extraction, svg-icon-classification]

key_files:
  created:
    - .planning/phases/03-page-reconnaissance/recon/map-economy.md
    - scripts/analyze_economy_page.py
    - scripts/analyze_economy_deep.py
    - scripts/analyze_economy_ot.py
  modified: []

decisions:
  - id: "03-06-fusionchart-primary"
    description: "FusionCharts JSON in data-fusionchart-config attribute is the primary extraction source for economy data -- contains all per-round values, outcomes, and sides in one parseable blob"
  - id: "03-06-ot-economy-missing-mr12"
    description: "OT economy data is absent for MR12 matches -- economy page only shows regulation rounds (24 max). MR15 era matches show all rounds including OT."
  - id: "03-06-buy-type-thresholds"
    description: "HLTV buy type classification: Full eco <$5K, Semi-eco $5K-$10K, Semi-buy $10K-$20K, Full buy $20K+"
  - id: "03-06-economy-all-eras"
    description: "Economy data available for all sampled eras (2023-2026) with identical DOM structure"
  - id: "03-06-static-html-sufficient"
    description: "All economy data extractable from static HTML -- no JS execution or nodriver interaction needed"

metrics:
  duration: "~12 min"
  completed: "2026-02-15"
---

# Phase 3 Plan 06: Map Economy Page Analysis Summary

**One-liner:** FusionCharts JSON in data-fusionchart-config attribute provides complete per-round equipment values, buy types (4 tiers at $5K/$10K/$20K thresholds), and round outcomes -- all extractable from static HTML, available since 2023, but MR12 OT rounds are missing.

## What Was Done

### Task 1: Exploratory selector discovery for economy page

Analyzed all 12 economy page HTML samples using BeautifulSoup. Performed systematic DOM reconnaissance including:
- Full CSS class frequency analysis (filtered ~6M chars of page chrome/cookies)
- All `data-*` attributes catalogued (found `data-fusionchart-config`)
- Script tag analysis (identified FusionCharts library reference)
- Economy-specific element search by keyword
- Equipment table structure analysis
- Team economy stats breakdown parsing
- Overtime round comparison (critical finding)
- Historical availability verification (2023 vs 2026)

Created three analysis scripts (`analyze_economy_page.py`, `analyze_economy_deep.py`, `analyze_economy_ot.py`) and the comprehensive selector map document.

## Key Findings

1. **Primary data source is FusionCharts JSON:** A single `<worker-ignore class="graph" data-fusionchart-config="...">` element contains all per-round economy data as a JSON blob. This includes equipment values (integer dollar amounts), team names, round outcomes (via anchor image URLs), and side information (CT/T prefix). No JavaScript execution is needed -- the JSON is embedded directly in the HTML attribute.

2. **Buy type classification uses 4 tiers:** HLTV classifies rounds into Full eco (<$5K), Semi-eco ($5K-$10K), Semi-buy ($10K-$20K), and Full buy ($20K+). These thresholds are embedded in the chart's trendlines and are consistent across all eras.

3. **15 unique SVG icons encode buy type granularly:** Equipment category tables use SVG filenames like `ctRifleArmorWin.svg` that encode side (CT/T), buy type (Pistol/ForcePistol/Forcebuy/RifleArmor), and outcome (Win/Loss). These provide a more granular classification than the threshold-based approach.

4. **OT economy data is MISSING for MR12 matches:** The match economy-206389 (score 19-17 = 36 rounds) only shows 24 rounds (regulation). All 12 overtime rounds are absent from both the FusionCharts data and the equipment tables. However, MR15-era matches (like economy-162345, score 16-14 = 30 rounds) show all rounds including OT. This is a platform limitation, not a scraping issue.

5. **Economy data exists for all eras (2023-2026):** The earliest sample (September 2023) has identical DOM structure and complete economy data. The "Beta" label on the economy tab has been present since at least 2023.

6. **Three redundant data representations:** The page provides the same core data in three forms: (1) FusionCharts JSON chart, (2) per-round SVG icon tables, (3) aggregate team stats summary. The FusionCharts JSON is the most complete and easiest to parse.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| FusionCharts JSON as primary extraction source | Single JSON blob contains all fields; no DOM traversal needed |
| OT economy data infeasible for MR12 | Not present on the page; no known workaround |
| Buy type from thresholds, not SVG icons | Thresholds are explicit in the data; SVG icons require filename parsing |
| All eras have economy data | Verified: Sep 2023 through Feb 2026, identical structure |
| Static HTML extraction (no nodriver needed) | All data in HTML attributes, not JS-loaded |

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

| Check | Result |
|-------|--------|
| map-economy.md exists and is 100+ lines | 615 lines -- PASS |
| Primary data source identified | FusionCharts JSON in data-fusionchart-config -- PASS |
| Per-round equipment values documented | Selector + parsing code provided -- PASS |
| Buy type classifications documented | 4-tier threshold system + 15 SVG icons -- PASS |
| Historical availability checked | All eras (2023-2026) have data -- PASS |
| Extraction feasibility assessed | Fully extractable from static HTML -- PASS |
| Selectors verified programmatically | BeautifulSoup .select() against 12 samples -- PASS |

## Next Phase Readiness

This plan resolves the "Economy data availability for historical matches" concern from STATE.md. Phase 7 (Economy Extraction) can proceed with confidence:

- **Extract from static HTML:** No live browser interaction needed beyond the initial page fetch
- **Parse FusionCharts JSON:** `json.loads(element['data-fusionchart-config'])` gives all per-round data
- **Handle OT gracefully:** Check if chart round count matches expected total; flag missing OT data
- **Buy type is derivable:** Apply thresholds from the trendlines data

**One limitation to document for Phase 7:** MR12 overtime economy data is unavailable. The parser should detect this case (chart rounds < total match rounds) and record it, but not treat it as an error.
