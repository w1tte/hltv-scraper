# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-14)

**Core value:** Reliably extract every available stat from HLTV match pages into a structured, queryable dataset -- without getting blocked.
**Current focus:** Phase 4 (Match Discovery) in progress. Infrastructure and parser complete, discovery runner next.

## Current Position

Phase: 4 of 9 (Match Discovery)
Plan: 2 of N in current phase (01 and 02 complete)
Status: In progress
Last activity: 2026-02-15 -- Completed 04-01-PLAN.md (discovery infrastructure)

Progress: [████------] 35% (14/40 plans across all phases)

## Performance Metrics

**Velocity:**
- Total plans completed: 14
- Average duration: ~10 min
- Total execution time: ~2.2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-http-client | 3/3 | ~45 min | ~15 min |
| 02-storage-foundation | 2/2 | ~6 min | ~3 min |
| 03-page-reconnaissance | 7/7 | ~82 min | ~12 min |
| 04-match-discovery | 2/N | ~6 min | ~3 min |

**Recent Trend:**
- Last 5 plans: 04-01 (4 min), 04-02 (2 min), 03-07 (5 min), 03-02 (7 min), 03-06 (12 min)
- Phase 4 plans are fast -- building on established patterns from Phases 1-2

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 9-phase pipeline architecture following fetch-before-parse pattern (raw HTML stored to disk before parsing)
- [Roadmap]: Phase 3 (Page Reconnaissance) inserted to understand HTML structure and edge cases before writing parsers
- [01-01]: Used stdlib dataclass for ScraperConfig (not pydantic) -- lightweight, no extra dependency
- [01-01]: All exceptions carry url and status_code as keyword-only attributes
- [01-01]: RateLimiter uses time.monotonic() for elapsed accounting
- [01-02]: tenacity @retry decorator inline on fetch() method; _patch_retry() overrides stop with config.max_retries
- **[01-03 DEVIATION]: curl_cffi replaced with nodriver** -- HLTV performance pages serve active Cloudflare JavaScript challenges (Turnstile) that no HTTP-only client can solve. nodriver (real Chrome, off-screen window) solves all 5 page types. user_agents.py deleted (real Chrome UA is superior to rotation).
- [01-03]: Off-screen Chrome: headless=False + --window-position=-32000,-32000 --window-size=1,1 (headless modes detected by Cloudflare)
- [01-03]: Minimum content threshold: 10,000 chars (detects incomplete page loads and Cloudflare interstitials)
- [01-03]: Extraction retry: if HTML < 10K chars, wait page_load_wait and re-extract before failing
- [02-01]: No separate entity lookup tables -- inline team/player IDs with names-at-time-of-match (intentional denormalization for historical accuracy)
- [02-01]: Composite primary keys on child tables for natural UPSERT conflict targets
- [02-01]: Per-row provenance (scraped_at, updated_at, source_url, parser_version) on all 5 tables
- [02-01]: Economy FK references round_history (strictest integrity); can relax via migration if needed
- [02-01]: HtmlStorage supports 4 match-page types only; results pages deferred to Phase 4
- [02-02]: MatchRepository takes sqlite3.Connection (not Database) for test decoupling
- [02-02]: UPSERT SQL as module-level constants; batch methods use loop inside with conn: (not executemany)
- [02-02]: Read methods return dict (via dict(row)); exceptions propagate to callers
- [03-01]: All HLTV pages now show Rating 3.0 (retroactive application confirmed) -- no Rating 2.0/2.1 column handling needed
- [03-01]: Forfeit matches have map name "Default" and zero mapstatsids -- parsers must detect this
- [03-01]: HLTV URL slug is cosmetic; numeric match ID determines content
- [03-01]: HTML samples in data/recon/ (gitignored); fetch scripts in scripts/ for reproducibility
- [03-02]: Big-results featured section (page 1 only) is exact duplicate of regular results -- parsers must skip it
- [03-02]: map-text encodes format (bo3/bo5), BO1 map name (nuke/ovp/mrg), and forfeit (def) in a single field
- [03-02]: Use last .results-all container on page to skip big-results; data-zonedgrouping-entry-unix on each .result-con for timestamps
- [03-06]: FusionCharts JSON in data-fusionchart-config is primary extraction source for economy data -- single JSON blob with all per-round values
- [03-06]: Buy type thresholds: Full eco <$5K, Semi-eco $5K-$10K, Semi-buy $10K-$20K, Full buy $20K+
- [03-06]: Economy data available for all eras (2023-2026), identical DOM structure, all extractable from static HTML
- [03-06]: OT economy data missing for MR12 matches -- page shows regulation rounds only (24 max)
- [03-04]: Rating 2.0 page (162345) has different column structure than 3.0 -- no st-roundSwing, eco-adjusted values are "null"; detect via th.st-rating text
- [03-04]: Map name is bare text node in match-info-box (no CSS class) -- requires NavigableString iteration
- [03-04]: Single OT (30 rounds) stays in one container; extended OT (36+ rounds) gets separate "Overtime" container
- [03-04]: 6 stats tables per page: 2 totalstats (visible) + 2 ctstats + 2 tstats (both hidden, same column layout)
- [03-04]: First .stats-table.totalstats = team-left, second = team-right
- [03-03]: Rankings are inside .lineups .box-headline .teamRanking, NOT inside .team{1,2}-gradient
- [03-03]: Two .veto-box elements per page: first is format/metadata, second is actual veto sequence
- [03-03]: Team1 = always left (.results-left); team2 = always right (.results-right) in map holders
- [03-03]: Full forfeit matches lack .won/.lost divs entirely; countdown shows "Match deleted"
- [03-03]: Half-score spans use class="ct"/"t" for side indication; overtime spans lack side classes
- [03-03]: No map pick indicator on map holders -- picks only available from veto text
- [03-05]: Performance page metrics are in FusionChart JSON (data-fusionchart-config), not HTML tables -- use json.loads() for extraction
- [03-05]: Rating 2.0 pages still exist (sample 162345, Sep 2023 tier-3 match) -- parser must detect via last bar label ("Rating 2.0" = 6 bars vs "Rating 3.0" = 7 bars)
- [03-05]: Eco-adjusted stats (eK-eD, eADR, eKAST) are NOT on performance page -- only on map stats overview page
- [03-05]: Multi-kill counts (2k-5k) and clutch stats (1v1-1v5) are NOT on performance page -- performance page has rates and ratings only
- [03-05]: Kill matrix has 3 types (All/First kills/AWP kills) all in initial HTML (hidden divs with class "hidden")
- [03-07]: Canonical extraction sources finalized: team names from Match Overview, scoreboard stats from Map Stats, rate metrics from Performance, economy from Economy page
- [03-07]: Extraction order: Results Listing (Phase 4) -> Match Overview (Phase 5) -> Map Stats (Phase 6) -> Performance + Economy (Phase 7)
- [03-07]: Rating detection: primary signal is th.st-rating text on map stats page; secondary is FusionChart last bar label on performance page
- [03-07]: Forfeit maps must be detected at Match Overview time (mapname == "Default") to avoid fetching non-existent sub-pages
- [04-01]: UPSERT ON CONFLICT does NOT update status column -- re-discovery preserves scraped/failed state
- [04-01]: Results pages stored under base_dir/results/ with offset-based naming, separate from matches/ hierarchy
- [04-01]: persist_page combines batch upsert + offset marking in single transaction for atomicity
- [04-02]: data-zonedgrouping-entry-unix attribute selector skips big-results without needing container-based logic -- cleaner than "last .results-all" approach
- [04-02]: parse_results_page is a pure function (HTML string in, list[DiscoveredMatch] out) -- no side effects, no state

### Pending Todos

None yet.

### Blockers/Concerns

- ~~[Research]: Economy data availability for historical matches uncertain~~ -- RESOLVED in 03-06: Economy data exists for all eras (2023-2026) with identical structure. OT economy data missing for MR12 matches only.
- ~~[Research]: Rating 2.0 vs 3.0 HTML differences unknown~~ -- RESOLVED across 03-04 and 03-05: Sample 162345 (Sep 2023, tier-3) retains Rating 2.0 format on both map stats (no Swing column, null eco-adjusted) and performance page (6-bar FusionChart with "Impact" and "Rating 2.0"). Detection: map stats uses th.st-rating text; performance uses last FusionChart bar label. Parsers must handle both versions.
- [01-03]: nodriver requires a real Chrome installation and runs a full browser process -- heavier than curl_cffi but necessary for Cloudflare bypass
- [02-01]: Economy->round_history FK may cause insertion issues if economy data exists without matching round history -- monitor in parsing phases

## Session Continuity

Last session: 2026-02-15
Stopped at: Completed 04-01-PLAN.md (discovery infrastructure)
Resume file: None
