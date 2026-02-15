---
phase: 03-page-reconnaissance
plan: 03
subsystem: page-analysis
tags: [hltv, css-selectors, match-overview, beautifulsoup, reconnaissance]

dependency_graph:
  requires: [03-01]
  provides: [match-overview-selector-map]
  affects: [05-match-overview-extraction]

tech_stack:
  added: []
  patterns: [programmatic-selector-verification, annotated-html-snippets]

key_files:
  created:
    - .planning/phases/03-page-reconnaissance/recon/match-overview.md
    - scripts/analyze_match_overview.py
    - scripts/analyze_vetoes_detail.py
  modified: []

decisions:
  - id: "03-03-rankings-in-lineups"
    description: "Team rankings are inside .lineups .box-headline .teamRanking, NOT inside .team{1,2}-gradient -- must use lineup container for ranking extraction"
  - id: "03-03-two-veto-boxes"
    description: "Page has two .veto-box elements: first is format/metadata, second is actual veto sequence -- use index [1] to target vetoes"
  - id: "03-03-team1-always-left"
    description: "Team 1 (.team1-gradient) is always .results-left in map holders; team 2 is always .results-right -- consistent across all 9 samples"
  - id: "03-03-forfeit-no-score-divs"
    description: "Full forfeit matches have NO .won/.lost divs in team gradients, no stats links, no half scores -- countdown text shows 'Match deleted'"
  - id: "03-03-half-score-span-classes"
    description: "Half-score spans use class='ct' and class='t' to indicate sides; overtime spans lack side classes entirely"
  - id: "03-03-no-pick-indicator-on-maps"
    description: "No visual map pick indicator exists on map holder elements -- map picks are only available from veto text"
  - id: "03-03-played-vs-optional"
    description: "Played maps have .played class, unplayed have .optional class; forfeit maps (Default) use .played but lack stats links"

metrics:
  duration: "~14 min"
  completed: "2026-02-15"
---

# Phase 3 Plan 03: Match Overview Page Analysis Summary

**One-liner:** Complete CSS selector map for HLTV match overview pages covering 677 lines across 5 sections (metadata, maps, vetoes, rosters, other), verified against 9 HTML samples including BO1/BO3/BO5/overtime/forfeit edge cases.

## What Was Done

### Task 1: Programmatic selector discovery for match overview metadata

Created two analysis scripts (`scripts/analyze_match_overview.py` and `scripts/analyze_vetoes_detail.py`) that loaded all 9 match overview HTML samples from `data/recon/match-*-overview.html.gz` and systematically discovered and verified CSS selectors using BeautifulSoup.

Produced `.planning/phases/03-page-reconnaissance/recon/match-overview.md` (677 lines) containing:

**Section 1 -- Match Metadata (17 fields):**
- Team names, IDs, scores, winner indicator
- Match date (unix milliseconds), event name/ID
- Match format (BO1/3/5), LAN/Online, match context
- Rankings (discovered they live inside `.lineups`, not `.team{1,2}-gradient`)
- Forfeit detection signals

**Section 2 -- Map Holders and Scores (10 fields):**
- Map name, played/unplayed status, scores, half-score structure
- MapStatsID extraction from stats links
- Detailed half-score span parsing including CT/T side classes and overtime
- Annotated HTML for played, unplayed, and forfeit map holders

**Section 3 -- Veto Sequence:**
- Two `.veto-box` elements: format box vs actual veto lines
- Veto line parsing regex for removed/picked/left-over actions
- Complete veto structure documented for BO1 (6 bans + 1 left), BO3 (2 bans + 2 picks + 2 bans + 1 left), BO5 (2 bans + 4 picks + 1 left)
- Annotated HTML for all three formats

**Section 4 -- Player Rosters (8 fields):**
- Player ID via `data-player-id` attribute, player name via `.text-ellipsis`
- Player nationality from `img.flag[title]`
- Team attribution via lineup block position (first = team1, second = team2)
- Table structure: Row 1 has player photos, Row 2 has names/IDs/flags

**Section 5 -- Other Elements (12 fields):**
- Head-to-head history, streams, demo links, highlight embeds
- All fields marked with extraction status (extract/skip/future)
- Elements NOT found documented (.match-info-box, GOTV links, pick indicators)

**Forfeit/Walkover Section:**
- Detailed comparison table: forfeit vs normal across 20 selectors
- Forfeit detection checklist (5 independent signals)
- Partial forfeit analysis (BO5 with forfeited map 3)

## Key Findings

1. **Rankings are NOT in `.team{1,2}-gradient`.** They are inside `.lineups .box-headline .teamRanking a`. The gigobyte/HLTV reference selectors implied they were in the team gradient area -- this is incorrect for current HLTV HTML.

2. **Two `.veto-box` elements per page.** The first contains format/metadata text (also used for match format extraction); the second contains the actual veto sequence. Must use index-based selection.

3. **Half-score spans encode CT/T side information.** Each numeric span has `class="ct"` or `class="t"` for regulation halves. Overtime spans lack these classes. This is more reliable than text parsing.

4. **No map pick indicator on map holders.** Despite checking `.pick`, `.picked`, `.left-border`, `.right-border`, and `.map-pick` selectors, no visual pick indicator exists on map holder elements. Map picks are only conveyed through the veto text.

5. **Full forfeit matches lack score divs entirely.** No `.won`/`.lost` children exist in the team gradient containers. Countdown text is "Match deleted" (vs "Match over" for normal matches). However, player rosters and veto sequence ARE still present.

6. **Played maps use `.played` class; unplayed use `.optional`.** Forfeit maps ("Default") use `.played` but have empty stats-link and half-score elements.

7. **`.text-ellipsis` appears 190-370 times per page** (in various contexts like navigation, head-to-head, etc.). For player names, MUST scope to `[data-player-id] .text-ellipsis` to get the clean 10-player roster.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Rankings inside .lineups, not team-gradient | Verified against all 9 samples; ranking is in .box-headline .teamRanking a |
| Two .veto-box elements: index [1] for vetoes | First is format info; second is actual veto sequence |
| team1 = always left (.results-left) | Consistent across all 9 samples, all formats |
| Half-score parsing via span classes not text | span class="ct"/"t" is more reliable than regex on "(7:5;6:6)" text |
| No map pick indicator on map holders | Searched 5+ potential selectors across all samples; picks only in veto text |
| Forfeit detection: 5 independent signals | Multiple detection paths ensures robustness |
| data-player-id as primary player identifier | Cleaner than href parsing; available on all samples including forfeits |

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

| Check | Result |
|-------|--------|
| match-overview.md exists | Yes (677 lines) -- PASS |
| 200+ lines | 677 lines -- PASS |
| All 5 sections covered | Metadata, maps, vetoes, rosters, other -- PASS |
| Veto structure for BO1, BO3, BO5 | All three documented with annotated HTML -- PASS |
| Forfeit/walkover differences documented | Dedicated section with 20-row comparison table -- PASS |
| mapstatsid extraction documented | Regex `/mapstatsid/(\d+)/` with selector `.mapholder a.results-stats[href]` -- PASS |
| Every selector tested against multiple samples | Verification matrix: all 9 samples -- PASS |
| All fields have extraction status | extract/skip/future on every field -- PASS |
| Annotated HTML snippets | Team container, played/unplayed/forfeit map holders, veto boxes (all 3 formats), player roster -- PASS |

## Next Phase Readiness

The match-overview.md selector map is ready for consumption by Phase 5 (Match Overview Extraction). The document is detailed enough to build the parser without needing to inspect raw HTML.

**No blockers identified.** All selectors verified, all edge cases documented.
