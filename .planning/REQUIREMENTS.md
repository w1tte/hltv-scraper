# Requirements: HLTV Match Scraper

**Defined:** 2026-02-14
**Core Value:** Reliably extract every available stat from HLTV match pages into a structured, queryable dataset — without getting blocked.

## v1 Requirements

### Discovery

- [ ] **DISC-01**: Scraper navigates HLTV results pages with offset-based pagination to discover all CS2-era match IDs
- [ ] **DISC-02**: Scraper filters results to only CS2-era matches (post September 2023)
- [ ] **DISC-03**: Scraper extracts match ID, team names, team IDs (from hyperlinks), scores, event name, star rating, and date from results listing

### Page Reconnaissance

- [x] **RECON-01**: Sample HTML for every target page type (results listing, match overview, map overview, map performance, map economy) is fetched and archived to disk
- [x] **RECON-02**: CSS selectors and HTML structure paths for every extractable data field are documented per page type
- [x] **RECON-03**: Structural differences across match formats (BO1 vs BO3/BO5, forfeits/walkovers, overtime) are documented with examples
- [x] **RECON-04**: Rating version differences (2.0/2.1 vs 3.0) are documented with concrete HTML examples showing changed fields
- [x] **RECON-05**: Cross-page data overlap is mapped: which fields appear on multiple page types vs. which are unique to one page type

### Match Overview

- [x] **MTCH-01**: Scraper extracts match metadata from overview page: team names, team IDs (from hyperlinks), final score, format (BO1/BO3/BO5), LAN/online, date/time
- [x] **MTCH-02**: Scraper extracts event info: event ID, event name
- [x] **MTCH-03**: Scraper extracts full map veto sequence with team attribution (pick/ban/decider)
- [x] **MTCH-04**: Scraper extracts per-map scores including CT/T half breakdowns
- [x] **MTCH-05**: Scraper extracts player rosters for each team with player IDs and player names (from hyperlinks)
- [x] **MTCH-06**: Scraper follows links to per-map stats pages for each played map

### Map Stats — Overview

- [x] **MAPS-01**: Scraper extracts per-player scoreboard from map overview: kills, deaths, assists, flash assists, HS kills, K/D diff, ADR, KAST%, first kills diff, rating
- [x] **MAPS-02**: Scraper extracts round-by-round history with outcome types (bomb, elimination, defuse, time)
- [x] **MAPS-03**: Scraper extracts CT/T side round wins per team

### Map Stats — Performance

- [x] **PERF-01**: Scraper extracts detailed player performance data from performance page: KPR, DPR, impact rating, opening kills/deaths, multi-kill rounds
- [x] **PERF-02**: Scraper handles both Rating 2.0/2.1 and Rating 3.0 fields depending on match date

### Map Stats — Economy

- [x] **ECON-01**: Scraper extracts per-round economy data: team equipment values per round
- [x] **ECON-02**: Scraper extracts round-level buy type classifications (eco, force, full buy)

### Infrastructure

- [x] **INFR-01**: Scraper uses real Chrome browser (nodriver) to bypass Cloudflare active JavaScript challenges — superior to TLS impersonation
- [x] **INFR-02**: Scraper implements randomized delays between requests (configurable range, default 3-8 seconds)
- [x] **INFR-03**: Scraper presents genuine Chrome User-Agent via nodriver (more effective than rotation for anti-detection)
- [x] **INFR-04**: Scraper handles Cloudflare challenges with exponential backoff and configurable retry limits via tenacity
- [ ] **INFR-05**: Scraper logs progress, errors, and statistics to console and file
- [ ] **INFR-06**: Scraper tracks scraping state per match (discovered → fetched → parsed → complete)
- [ ] **INFR-07**: Scraper resumes from last checkpoint after interruption without re-scraping completed matches
- [ ] **INFR-08**: Scraper supports incremental mode: detect and scrape only new matches since last run

### Storage

- [x] **STOR-01**: SQLite database with relational schema: matches, maps, player_stats, round_history, economy tables
- [x] **STOR-02**: Store raw HTML to disk before parsing, enabling parser fixes without re-fetching
- [ ] **STOR-03**: Pydantic models validate every scraped record before database insertion
- [ ] **STOR-04**: Cross-field validation: player counts, round totals matching scores, rating bounds

## v2 Requirements

### Enrichment

- **ENRH-01**: Proxy rotation for distributing requests across multiple IPs
- **ENRH-02**: Event/tournament metadata scraping (prize pool, tier, location)
- **ENRH-03**: Head-to-head history extraction from match pages
- **ENRH-04**: Demo download link collection
- **ENRH-05**: Configurable scraping scope (date range, tier, event filters)

### Export

- **EXPR-01**: Export to CSV format
- **EXPR-02**: Export to JSON format
- **EXPR-03**: Export to Parquet format

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time/live match scraping | Triggers bans fastest, not needed for historical data |
| Player profile page scraping | Career stats derivable from match data |
| Heatmap data | Low analytical value for prediction models |
| Web UI / dashboard | This is a data pipeline, not a product |
| HLTV forum/news scraping | Not match statistics, zero value for models |
| General-purpose scraping framework | Over-engineering for a single-site scraper |
| Automated scheduling | Trivial to add later via OS scheduler |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DISC-01 | Phase 4 | Complete |
| DISC-02 | Phase 4 | Complete |
| DISC-03 | Phase 4 | Complete |
| RECON-01 | Phase 3 | Complete |
| RECON-02 | Phase 3 | Complete |
| RECON-03 | Phase 3 | Complete |
| RECON-04 | Phase 3 | Complete |
| RECON-05 | Phase 3 | Complete |
| MTCH-01 | Phase 5 | Complete |
| MTCH-02 | Phase 5 | Complete |
| MTCH-03 | Phase 5 | Complete |
| MTCH-04 | Phase 5 | Complete |
| MTCH-05 | Phase 5 | Complete |
| MTCH-06 | Phase 5 | Complete |
| MAPS-01 | Phase 6 | Complete |
| MAPS-02 | Phase 6 | Complete |
| MAPS-03 | Phase 6 | Complete |
| PERF-01 | Phase 7 | Complete |
| PERF-02 | Phase 7 | Complete |
| ECON-01 | Phase 7 | Complete |
| ECON-02 | Phase 7 | Complete |
| INFR-01 | Phase 1 | Complete |
| INFR-02 | Phase 1 | Complete |
| INFR-03 | Phase 1 | Complete |
| INFR-04 | Phase 1 | Complete |
| INFR-05 | Phase 9 | Pending |
| INFR-06 | Phase 9 | Pending |
| INFR-07 | Phase 9 | Pending |
| INFR-08 | Phase 9 | Pending |
| STOR-01 | Phase 2 | Complete |
| STOR-02 | Phase 2 | Complete |
| STOR-03 | Phase 8 | Pending |
| STOR-04 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0

---
*Requirements defined: 2026-02-14*
*Last updated: 2026-02-16 -- PERF-01, PERF-02, ECON-01, ECON-02 marked Complete (Phase 7 verified)*
