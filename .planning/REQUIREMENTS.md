# Requirements: HLTV Match Scraper

**Defined:** 2026-02-14
**Core Value:** Reliably extract every available stat from HLTV match pages into a structured, queryable dataset — without getting blocked.

## v1 Requirements

### Discovery

- [ ] **DISC-01**: Scraper navigates HLTV results pages with offset-based pagination to discover all CS2-era match IDs
- [ ] **DISC-02**: Scraper filters results to only CS2-era matches (post September 2023)
- [ ] **DISC-03**: Scraper extracts match ID, teams, scores, event name, star rating, and date from results listing

### Match Overview

- [ ] **MTCH-01**: Scraper extracts match metadata from overview page: teams, final score, format (BO1/BO3/BO5), LAN/online, date/time
- [ ] **MTCH-02**: Scraper extracts event info: event ID, event name
- [ ] **MTCH-03**: Scraper extracts full map veto sequence with team attribution (pick/ban/decider)
- [ ] **MTCH-04**: Scraper extracts per-map scores including CT/T half breakdowns
- [ ] **MTCH-05**: Scraper extracts player rosters for each team with player IDs
- [ ] **MTCH-06**: Scraper follows links to per-map stats pages for each played map

### Map Stats — Overview

- [ ] **MAPS-01**: Scraper extracts per-player scoreboard from map overview: kills, deaths, assists, flash assists, HS kills, K/D diff, ADR, KAST%, first kills diff, rating
- [ ] **MAPS-02**: Scraper extracts round-by-round history with outcome types (bomb, elimination, defuse, time)
- [ ] **MAPS-03**: Scraper extracts CT/T side round wins per team

### Map Stats — Performance

- [ ] **PERF-01**: Scraper extracts detailed player performance data from performance page: KPR, DPR, impact rating, opening kills/deaths, multi-kill rounds
- [ ] **PERF-02**: Scraper handles both Rating 2.0/2.1 and Rating 3.0 fields depending on match date

### Map Stats — Economy

- [ ] **ECON-01**: Scraper extracts per-round economy data: team equipment values per round
- [ ] **ECON-02**: Scraper extracts round-level buy type classifications (eco, force, full buy)

### Infrastructure

- [ ] **INFR-01**: Scraper uses TLS-fingerprint-safe HTTP client (curl_cffi or equivalent) to bypass Cloudflare passive detection
- [ ] **INFR-02**: Scraper implements randomized delays between requests (configurable range, e.g. 3-8 seconds)
- [ ] **INFR-03**: Scraper rotates User-Agent strings across requests
- [ ] **INFR-04**: Scraper handles HTTP errors (403, 429, 503, timeouts) with exponential backoff and configurable retry limits
- [ ] **INFR-05**: Scraper logs progress, errors, and statistics to console and file
- [ ] **INFR-06**: Scraper tracks scraping state per match (discovered → fetched → parsed → complete)
- [ ] **INFR-07**: Scraper resumes from last checkpoint after interruption without re-scraping completed matches
- [ ] **INFR-08**: Scraper supports incremental mode: detect and scrape only new matches since last run

### Storage

- [ ] **STOR-01**: SQLite database with relational schema: matches, maps, player_stats, round_history, economy tables
- [ ] **STOR-02**: Store raw HTML to disk before parsing, enabling parser fixes without re-fetching
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
| DISC-01 | — | Pending |
| DISC-02 | — | Pending |
| DISC-03 | — | Pending |
| MTCH-01 | — | Pending |
| MTCH-02 | — | Pending |
| MTCH-03 | — | Pending |
| MTCH-04 | — | Pending |
| MTCH-05 | — | Pending |
| MTCH-06 | — | Pending |
| MAPS-01 | — | Pending |
| MAPS-02 | — | Pending |
| MAPS-03 | — | Pending |
| PERF-01 | — | Pending |
| PERF-02 | — | Pending |
| ECON-01 | — | Pending |
| ECON-02 | — | Pending |
| INFR-01 | — | Pending |
| INFR-02 | — | Pending |
| INFR-03 | — | Pending |
| INFR-04 | — | Pending |
| INFR-05 | — | Pending |
| INFR-06 | — | Pending |
| INFR-07 | — | Pending |
| INFR-08 | — | Pending |
| STOR-01 | — | Pending |
| STOR-02 | — | Pending |
| STOR-03 | — | Pending |
| STOR-04 | — | Pending |

**Coverage:**
- v1 requirements: 28 total
- Mapped to phases: 0
- Unmapped: 28 ⚠️

---
*Requirements defined: 2026-02-14*
*Last updated: 2026-02-14 after initial definition*
