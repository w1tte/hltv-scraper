# Roadmap: HLTV Match Scraper

## Overview

This roadmap delivers a complete HLTV match data scraper in 9 phases, following the natural dependency chain: first the ability to make HTTP requests without getting blocked, then a place to store data, then a reconnaissance phase to understand page structures and available data fields before writing any parsers, then progressively building out page-type parsers (discovery, match overview, map stats, performance, economy), then validation, and finally orchestration that ties everything into a resumable pipeline. The reconnaissance phase ensures every parser is built against real HTML structure rather than assumptions.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: HTTP Client and Anti-Detection** - Reliable, ban-resistant HTTP transport for HLTV
- [ ] **Phase 2: Storage Foundation** - Database schema and raw HTML archival system
- [ ] **Phase 3: Page Reconnaissance** - Fetch, inspect, and document every HLTV page type to map available data before building parsers
- [ ] **Phase 4: Match Discovery** - Paginate HLTV results pages to collect all CS2-era match IDs
- [ ] **Phase 5: Match Overview Extraction** - Parse match detail pages for teams, scores, vetoes, rosters
- [ ] **Phase 6: Map Stats Extraction** - Parse per-map overview pages for scoreboards and round history
- [ ] **Phase 7: Performance and Economy Extraction** - Parse performance and economy sub-pages per map
- [ ] **Phase 8: Data Validation** - Pydantic schema enforcement and cross-field integrity checks
- [ ] **Phase 9: Pipeline Orchestration** - End-to-end pipeline with state tracking, resume, incremental mode, and logging

## Phase Details

### Phase 1: HTTP Client and Anti-Detection
**Goal**: The scraper can make HTTP requests to any HLTV page and receive valid HTML responses without triggering Cloudflare blocks
**Depends on**: Nothing (first phase)
**Requirements**: INFR-01, INFR-02, INFR-03, INFR-04
**Success Criteria** (what must be TRUE):
  1. Scraper can fetch an HLTV match page and receive a 200 response with valid HTML (not a Cloudflare challenge page)
  2. Scraper waits a randomized delay (configurable range) between consecutive requests
  3. Scraper uses a different User-Agent string across successive requests
  4. Scraper recovers from 403/429/503 errors by backing off exponentially and retrying, without crashing
  5. Fetching 20+ pages in sequence does not trigger an IP ban or Cloudflare challenge escalation
**Plans**: 3 plans

Plans:
- [ ] 01-01-PLAN.md -- Project scaffolding, config, exceptions, rate limiter, and UA rotator
- [ ] 01-02-PLAN.md -- Cloudflare detection, retry logic, and HLTVClient assembly
- [ ] 01-03-PLAN.md -- Integration test against live HLTV (all 5 page types, 20-page sequence)

### Phase 2: Storage Foundation
**Goal**: All scraped data has a persistent home -- relational database for structured data, filesystem for raw HTML
**Depends on**: Phase 1
**Requirements**: STOR-01, STOR-02
**Success Criteria** (what must be TRUE):
  1. SQLite database exists with normalized tables for matches, maps, player_stats, round_history, and economy
  2. Raw HTML responses are saved to disk organized by page type and ID before any parsing occurs
  3. Database schema supports UPSERT semantics so re-processing a match does not create duplicates
  4. Raw HTML files can be read back and parsed offline without any network requests
**Plans**: TBD

Plans:
- [ ] 02-01: SQLite database schema design and creation (all tables, indexes, constraints)
- [ ] 02-02: Raw HTML storage layer (directory structure, save/load by page type and ID)
- [ ] 02-03: Database access layer (CRUD operations, UPSERT logic)

### Phase 3: Page Reconnaissance
**Goal**: Every HLTV page type the scraper will parse is fetched, inspected, and documented -- CSS selectors, data fields, structural variations, and edge cases are all mapped out before any parser code is written
**Depends on**: Phase 1, Phase 2
**Requirements**: RECON-01, RECON-02, RECON-03, RECON-04, RECON-05
**Success Criteria** (what must be TRUE):
  1. Sample HTML is saved to disk for every page type the scraper targets: results listing, match overview, map overview (stats), map performance, and map economy
  2. A selector map document exists for each page type listing the CSS selectors / HTML structure paths for every data field the scraper will extract
  3. Structural differences between match formats are documented: BO1 vs BO3/BO5 (number of map tabs, veto length), forfeit/walkover matches (missing stats), overtime matches (extra rounds)
  4. The difference between Rating 2.0/2.1 pages and Rating 3.0 pages is documented with concrete HTML examples showing which fields change
  5. Each page type's selector map identifies which data fields overlap with other pages vs. which are unique to that page type only
**Plans**: TBD

Plans:
- [ ] 03-01: Fetch and archive sample pages (results listing, BO1 match, BO3 match, forfeit/walkover)
- [ ] 03-02: Results listing page analysis (pagination structure, match entry selectors, available metadata)
- [ ] 03-03: Match overview page analysis (metadata, teams, scores, vetoes, rosters, map links)
- [ ] 03-04: Map overview (stats) page analysis (scoreboard, round history, side stats)
- [ ] 03-05: Map performance page analysis (detailed player metrics, Rating 2.0 vs 3.0 field differences)
- [ ] 03-06: Map economy page analysis (per-round equipment values, buy type classifications)
- [ ] 03-07: Edge case and cross-page synthesis (BO1 vs BO3 differences, overtime, forfeits, data overlap map)

### Phase 4: Match Discovery
**Goal**: The scraper can systematically find every CS2-era match on HLTV by paginating the results listing
**Depends on**: Phase 1, Phase 2, Phase 3
**Requirements**: DISC-01, DISC-02, DISC-03
**Success Criteria** (what must be TRUE):
  1. Scraper paginates through HLTV /results pages using offset-based navigation and discovers match URLs
  2. Scraper only collects matches from the CS2 era (post September 2023), stopping pagination at the boundary
  3. Each discovered match has its match ID, teams, score, event name, star rating, and date extracted from the listing page
  4. Discovered matches are persisted to the database so they survive process restarts
**Plans**: TBD

Plans:
- [ ] 04-01: Results page HTML analysis and selector map for listing entries
- [ ] 04-02: Pagination logic with CS2-era date boundary detection
- [ ] 04-03: Discovery data extraction and database persistence

### Phase 5: Match Overview Extraction
**Goal**: Every discovered match has its full overview data extracted -- teams, scores, format, event, vetoes, rosters, and links to per-map stats pages
**Depends on**: Phase 2, Phase 4
**Requirements**: MTCH-01, MTCH-02, MTCH-03, MTCH-04, MTCH-05, MTCH-06
**Success Criteria** (what must be TRUE):
  1. Scraper extracts match metadata from the overview page: both team names/IDs, final series score, match format (BO1/BO3/BO5), LAN/online flag, and date/time
  2. Scraper extracts the event ID and event name for every match
  3. Scraper extracts the full map veto sequence with correct team attribution (which team picked, banned, or was assigned decider)
  4. Scraper extracts per-map scores including CT-side and T-side half breakdowns
  5. Scraper extracts the player roster for each team with player IDs
  6. Scraper identifies and stores URLs to the per-map stats pages (mapstatsid links) for each played map
**Plans**: TBD

Plans:
- [ ] 05-01: Match overview page HTML analysis and selector map
- [ ] 05-02: Match metadata parser (teams, scores, format, date, LAN/online)
- [ ] 05-03: Event info, veto sequence, and per-map score parser
- [ ] 05-04: Player roster extraction and mapstatsid link collection
- [ ] 05-05: Match overview integration (fetch, store raw HTML, parse, persist to DB)

### Phase 6: Map Stats Extraction
**Goal**: Every played map has its per-player scoreboard and round-by-round history extracted from the map overview page
**Depends on**: Phase 2, Phase 5
**Requirements**: MAPS-01, MAPS-02, MAPS-03
**Success Criteria** (what must be TRUE):
  1. Scraper extracts the full per-player scoreboard from each map: kills, deaths, assists, flash assists, HS kills, K/D diff, ADR, KAST%, first kills diff, and rating
  2. Scraper extracts the round-by-round history with outcome types (bomb plant, elimination, defuse, time runout) for every round
  3. Scraper extracts CT-side and T-side round win counts per team for each map
  4. All extracted map stats are persisted to the database linked to the correct match and map
**Plans**: TBD

Plans:
- [ ] 06-01: Map overview page HTML analysis and selector map
- [ ] 06-02: Per-player scoreboard parser
- [ ] 06-03: Round history and side-stats parser
- [ ] 06-04: Map stats integration (fetch, store raw HTML, parse, persist to DB)

### Phase 7: Performance and Economy Extraction
**Goal**: Every played map has its detailed performance metrics and round-by-round economy data extracted from the two remaining sub-pages
**Depends on**: Phase 2, Phase 5
**Requirements**: PERF-01, PERF-02, ECON-01, ECON-02
**Success Criteria** (what must be TRUE):
  1. Scraper extracts detailed player performance data from the performance page: KPR, DPR, impact rating, opening kills/deaths, and multi-kill round counts
  2. Scraper correctly handles both Rating 2.0/2.1 fields (pre-August 2025 matches) and Rating 3.0 fields (post-August 2025 matches) without data loss
  3. Scraper extracts per-round economy data including team equipment values for each round
  4. Scraper extracts round-level buy type classifications (eco, force buy, full buy) for both teams
  5. All performance and economy data is persisted to the database linked to the correct match, map, and players
**Plans**: TBD

Plans:
- [ ] 07-01: Performance page HTML analysis and selector map
- [ ] 07-02: Performance data parser (KPR, DPR, impact, openers, multi-kills)
- [ ] 07-03: Rating version detection and dual-format handling (2.0/2.1 vs 3.0)
- [ ] 07-04: Economy page HTML analysis and selector map
- [ ] 07-05: Economy data parser (equipment values, buy types per round)
- [ ] 07-06: Performance and economy integration (fetch, store, parse, persist)

### Phase 8: Data Validation
**Goal**: Every scraped record is validated against a strict schema before database insertion, catching data quality issues immediately rather than discovering them during analysis
**Depends on**: Phase 5, Phase 6, Phase 7
**Requirements**: STOR-03, STOR-04
**Success Criteria** (what must be TRUE):
  1. Every scraped record passes through a Pydantic model that enforces field types, required fields, and value constraints before database insertion
  2. Cross-field validation catches inconsistencies: player count per team equals 5, round totals match the final score, rating values fall within expected bounds
  3. Validation failures are logged with enough detail to identify the problematic match/map and the specific field that failed
  4. Invalid records do not silently enter the database -- they are rejected and flagged for investigation
**Plans**: TBD

Plans:
- [ ] 08-01: Pydantic models for all data entities (match, map, player_stats, round, economy)
- [ ] 08-02: Cross-field validation rules (player counts, round totals, rating bounds)
- [ ] 08-03: Validation integration into parsing pipeline with error reporting
- [ ] 08-04: Validation against sample of real scraped data (edge cases: forfeits, overtime, walkovers)

### Phase 9: Pipeline Orchestration
**Goal**: The scraper runs as a complete, resumable pipeline that can bulk-scrape historical data and incrementally pick up new matches, with full visibility into progress and state
**Depends on**: Phase 4, Phase 5, Phase 6, Phase 7, Phase 8
**Requirements**: INFR-05, INFR-06, INFR-07, INFR-08
**Success Criteria** (what must be TRUE):
  1. Scraper tracks per-match state through a progression (discovered, fetched, parsed, complete) so partial work is never lost
  2. After interruption (crash, Ctrl+C, network loss), the scraper resumes from its last checkpoint without re-scraping completed matches
  3. Incremental mode detects and scrapes only matches added since the last successful run
  4. Scraper logs progress, errors, and run statistics to both console and a log file with enough detail to diagnose issues
  5. Running a bulk scrape end-to-end (discovery through validation) produces a complete, validated dataset with no manual intervention
**Plans**: TBD

Plans:
- [ ] 09-01: Scrape state machine (per-match state tracking in scrape_log table)
- [ ] 09-02: Checkpoint and resume logic (survive interruptions, skip completed work)
- [ ] 09-03: Incremental mode (detect new matches since last run)
- [ ] 09-04: Logging framework (structured console + file logging, progress stats)
- [ ] 09-05: End-to-end pipeline integration and CLI entry point
- [ ] 09-06: Full pipeline test (bulk scrape a date range, verify complete dataset)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9
(Phases 6 and 7 can run in parallel after Phase 5 completes)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. HTTP Client and Anti-Detection | 0/3 | Planning complete | - |
| 2. Storage Foundation | 0/3 | Not started | - |
| 3. Page Reconnaissance | 0/7 | Not started | - |
| 4. Match Discovery | 0/3 | Not started | - |
| 5. Match Overview Extraction | 0/5 | Not started | - |
| 6. Map Stats Extraction | 0/4 | Not started | - |
| 7. Performance and Economy Extraction | 0/6 | Not started | - |
| 8. Data Validation | 0/4 | Not started | - |
| 9. Pipeline Orchestration | 0/6 | Not started | - |

---
*Roadmap created: 2026-02-14*
*Last updated: 2026-02-14 -- Phase 1 planned: 3 plans in 3 waves*
