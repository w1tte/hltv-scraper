# Project Research Summary

**Project:** HLTV.org CS2 Match Data Scraper
**Domain:** Web scraping / esports data collection
**Researched:** 2026-02-14
**Confidence:** MEDIUM-HIGH

## Executive Summary

This project is a single-site web scraper targeting HLTV.org to collect CS2 match statistics (teams, scores, map vetoes, per-map player stats including Rating 3.0) and store them in a local SQLite database for downstream analysis and ML model training. Experts build this type of scraper as a **five-layer pipeline**: URL discovery, page fetching with anti-detection, raw HTML storage, HTML parsing with externalized selectors, and structured data persistence. The critical architectural decision is to **store raw HTML before parsing** -- this decouples fetching (which is rate-limited and ban-prone) from parsing (which breaks when HLTV changes their frontend), letting you fix parsers and re-process stored HTML without touching HLTV's servers.

The recommended approach uses **curl_cffi** as the primary HTTP transport (it impersonates real browser TLS fingerprints, bypassing Cloudflare's passive detection) with **SeleniumBase UC Mode** as a fallback for pages that trigger active Cloudflare Turnstile challenges. HTML is parsed with **selectolax** for speed (20-30x faster than BeautifulSoup, material for 50K+ pages) and validated through **Pydantic** models before storage in **SQLite** via **Peewee** ORM. The two-tier HTTP strategy means most pages are fetched in ~50ms (curl_cffi) rather than ~2-5s (browser), dramatically reducing total scrape time while keeping a browser fallback ready.

The primary risks are: (1) **Cloudflare IP bans** from insufficient rate limiting or detectable TLS fingerprints -- mitigated by using curl_cffi's browser impersonation, 3-8 second random delays, and exponential backoff; (2) **silent data loss** from variable match page structures (BO1/BO3/BO5, forfeits, overtime, missing stats) -- mitigated by Pydantic schema validation on every record before database insertion; and (3) **lost scraping progress** from crashes during multi-day bulk runs -- mitigated by a checkpoint/resume system built into the database from day one. All three must be addressed in the first development phase, not bolted on later.

## Key Findings

### Recommended Stack

The stack follows a "lightest viable tool" principle: use fast HTTP with TLS impersonation by default, escalate to real browser only when challenged, and parse with the fastest library available. All libraries target **Python 3.12** (minimum 3.10, constrained by curl_cffi and tenacity).

**Core technologies:**
- **curl_cffi 0.14** (primary HTTP) -- impersonates real browser TLS/JA3 fingerprints at the network level; passes Cloudflare passive detection without launching a browser
- **SeleniumBase 4.46 UC Mode** (fallback browser) -- launches real undetectable Chrome for Cloudflare Turnstile challenges; more actively maintained than nodriver or Camoufox
- **selectolax 0.4.6** (primary parser) -- 20-30x faster than BeautifulSoup for CSS selector queries; built on C-level Lexbor engine; essential for bulk parsing of 50K+ pages
- **BeautifulSoup4 + lxml** (secondary parser) -- for the 5% of cases needing DOM traversal (.parent, .find_next_sibling)
- **Pydantic 2.12** (validation) -- runtime validation and type coercion at the boundary between raw HTML and structured data; catches data quality issues immediately
- **SQLite + Peewee 3.19** (storage) -- zero-config single-file database; Peewee adds lightweight ORM with migration support; trivial to swap for raw sqlite3 if project stays small
- **tenacity 9.1** (retry) -- declarative exponential backoff with jitter for transient 403/429/timeout errors

**Do NOT use:** Scrapy (overkill for single-site, Cloudflare bypass is painful), cloudscraper (outdated, can't keep up with Cloudflare 2025-2026), vanilla requests/httpx (TLS fingerprint detected and blocked instantly), vanilla Playwright (detected without stealth plugins which are deprecated).

### Expected Features

**Must have (table stakes) -- MVP scope:**
- **TS-1: Match discovery and pagination** -- navigate /results pages, collect match IDs across all pages with date/event filtering
- **TS-2: Match page parsing** -- extract teams, scores, vetoes, event, format, date from /matches/{id}/{slug}
- **TS-3: Per-map player stats** -- extract full scoreboard per map (kills, deaths, ADR, KAST, rating) from /stats/matches/mapstatsid/{id}/{slug}
- **TS-4: Anti-detection / rate limiting** -- randomized delays, TLS fingerprint impersonation, escalating backoff
- **TS-5: Data persistence** -- SQLite with relational schema (matches -> maps -> player_stats)
- **TS-6: Error handling and retry** -- graceful handling of 403/429/503/timeouts, automatic retries
- **TS-7: Incremental/resume capability** -- track scraping state per match, resume after interruption
- **TS-8: Map veto extraction** -- pick/ban sequence with team attribution (same page as TS-2, low marginal cost)
- **TS-9: Logging and progress** -- structured logging, progress bars (tqdm), ETA for bulk runs

**Should have (differentiators) -- post-MVP:**
- **D-1: Round-by-round history** -- enables round-level analysis (comeback patterns, eco success rates)
- **D-3: Head-to-head history** -- strong predictor for matchup analysis, easy extraction from match page
- **D-6: Data validation/integrity checks** -- cross-field validation (player count = 5, rounds add up, rating in bounds)
- **D-7: Entity resolution** -- canonical team/player ID mapping across name changes
- **D-8: Configurable scraping scope** -- filter by date, event, team, tier via CLI parameters
- **D-10: Export to CSV/JSON/Parquet** -- multiple output formats for different analysis tools
- **D-11: Rating 3.0 fields** -- new sub-ratings (Round Swing, Multi-kill rating, eco-adjusted stats)

**Defer (v2+):**
- **D-2: Economy/equipment data** -- uncertain availability for historical matches (needs empirical check)
- **D-4: Event/tournament metadata** -- separate page type, independent scraping target
- **D-5: Proxy rotation** -- not needed until single-IP rate limiting becomes a bottleneck
- **D-9: Demo download links** -- trivial to add but tangential to core stats mission

**Anti-features (do NOT build):**
- Real-time / live match scraping (fastest way to get permanently banned)
- Player profile page scraping (massive scope expansion; career stats derivable from match data)
- Web UI / dashboard (scope creep; export to existing analysis tools instead)
- General-purpose scraping framework (over-engineering for a single-site scraper)

### Architecture Approach

The architecture is a five-layer pipeline with strict separation between fetching and parsing. Raw HTML is stored to disk (keyed by match ID and page type) before any parsing occurs, so fetcher bugs and parser bugs are fixed independently. A `scrape_log` table in SQLite serves as both the checkpoint/resume system and the work queue. CSS selectors are externalized into per-page-type selector maps so that HLTV HTML changes require updating a single config file, not hunting through parsing logic.

**Major components:**
1. **URL Discovery (Coordinator)** -- paginates /results pages, builds work queue of match IDs, consults checkpoint state to skip already-scraped matches
2. **Page Fetcher (Anti-Detection Layer)** -- wraps curl_cffi (tier 1) and SeleniumBase UC Mode (tier 2) behind a simple `fetch(url) -> html` interface; owns rate limiting, delay randomization, and exponential backoff
3. **Raw HTML Store** -- saves complete HTML responses to `data/raw/{page_type}/{id}.html`; enables offline re-parsing and parser development without network requests
4. **HTML Parser (Selector Abstraction)** -- extracts structured data from stored HTML using externalized selector maps; separate parser functions per page type (results listing, match detail, map stats)
5. **Structured Database (SQLite)** -- normalized schema (matches, maps, player_stats, scrape_log) with UNIQUE constraints and UPSERT semantics for idempotent re-processing
6. **Checkpoint/Resume Manager** -- thin query layer over scrape_log table; tracks per-match state machine (DISCOVERED -> HTML_FETCHED -> PARSED -> COMPLETE or FAILED)

### Critical Pitfalls

1. **TLS fingerprint detection** -- Python's default TLS stack (requests, httpx, aiohttp) is instantly blocked by Cloudflare. Use curl_cffi for TLS impersonation from day one. Switching HTTP libraries later means rewriting the entire request layer. *Phase 1 concern.*
2. **Cloudflare IP ban spiral** -- Aggressive request rates (< 2s intervals) trigger escalating bans. Implement 3-8s random delays, exponential backoff on non-200 responses, and circuit breaker pattern (pause after N consecutive failures). *Phase 1 concern.*
3. **Silent data loss from variable page structures** -- BO1/BO3/BO5, forfeits, overtime, stand-ins, and pre-CS2 matches all have different HTML structures. Validate every record against Pydantic schema before database write. Detect match format first, then apply format-specific parsing. *Phase 2 concern.*
4. **No checkpoint/resume** -- Bulk scraping 50K+ matches takes days at safe rates. Any interruption without checkpoint tracking wastes days of work. Build scrape_log state tracking into the database schema from the first migration. *Phase 1 concern.*
5. **Hardcoded CSS selectors** -- HLTV is actively maintained; class names and layouts change. Externalize all selectors into per-page-type selector maps. Build a selector test suite with known HTML fixtures. *Phase 2 concern.*

## Implications for Roadmap

Based on combined research, the project naturally divides into 5 phases following the dependency chain: foundation infrastructure first, then data accumulation, then parsing, then orchestration, then hardening.

### Phase 1: Foundation and Fetching Infrastructure
**Rationale:** Everything depends on the ability to make requests to HLTV without getting banned, and on having a database schema to track progress. The anti-detection layer and checkpoint system must exist before any data collection begins. Every pitfall study confirms that retrofitting these is painful.
**Delivers:** Working HTTP client that can fetch HLTV pages reliably; SQLite schema with scrape_log; raw HTML storage directory structure; rate limiter with adaptive backoff; URL discovery that paginates /results pages and populates the work queue.
**Addresses:** TS-4 (anti-detection), TS-5 (storage schema), TS-6 (error handling/retry), TS-9 (logging), TS-1 (match discovery)
**Avoids:** Pitfall 1 (IP ban spiral), Pitfall 2 (TLS fingerprint detection), Pitfall 4 (no checkpoint/resume), Pitfall 10 (sequential ID assumption)

### Phase 2: HTML Parsing and Data Extraction
**Rationale:** With raw HTML accumulating from Phase 1, parsing becomes a purely offline activity. Selectors can be developed and tested against stored HTML without making any network requests. This phase is the most iterative -- inspect HTML, write selectors, test, adjust.
**Delivers:** Complete parser for all three HLTV page types (results listing, match detail, map stats); Pydantic validation models; externalized selector maps; match format classification (BO1/BO3/BO5, forfeits, overtime).
**Addresses:** TS-2 (match page parsing), TS-3 (per-map player stats), TS-8 (map vetoes), D-6 (data validation)
**Avoids:** Pitfall 3 (silent data loss), Pitfall 5 (hardcoded selectors), Pitfall 6 (treating all matches identically), Pitfall 9 (timezone handling), Pitfall 11 (name inconsistency)

### Phase 3: Orchestration and Incremental Updates
**Rationale:** With fetching and parsing both working, this phase ties them together into a CLI tool that can run end-to-end bulk scrapes and incremental daily updates. Resume capability and deduplication logic are built here.
**Delivers:** CLI interface for full-sweep and incremental modes; incremental update mode ("scrape matches newer than last run"); retry queue for failed matches; entity resolution for team/player IDs.
**Addresses:** TS-7 (incremental/resume), D-7 (entity resolution), D-8 (configurable scope)
**Avoids:** Pitfall 8 (no deduplication strategy)

### Phase 4: Data Enrichment and Export
**Rationale:** Core data pipeline is complete. This phase adds deeper data extraction (round history, head-to-head, Rating 3.0 sub-fields) and export formats for downstream consumers.
**Delivers:** Round-by-round history extraction; head-to-head data; Rating 3.0 sub-ratings; CSV/JSON/Parquet export; event metadata scraping.
**Addresses:** D-1 (round history), D-3 (head-to-head), D-10 (export formats), D-11 (Rating 3.0), D-4 (event metadata)
**Avoids:** Scope creep by keeping enrichment separate from core pipeline.

### Phase 5: Hardening and Scale
**Rationale:** Only build heavy anti-detection and proxy infrastructure if Phase 1-4 demonstrate the need. Start simple, escalate on evidence.
**Delivers:** SeleniumBase UC Mode integration as automated fallback; proxy rotation support; monitoring/alerting for scraping health; selector test suite as CI checks.
**Addresses:** D-5 (proxy rotation), D-2 (economy data -- investigate availability)
**Avoids:** Pitfall 7 (datacenter proxies), Pitfall 12 (over-engineering anti-detection)

### Phase Ordering Rationale

- **Phase 1 before Phase 2:** You cannot develop parsers without HTML to parse. Phase 1 accumulates raw HTML that Phase 2 processes offline. This also means parser bugs never cause re-fetching.
- **Phase 2 before Phase 3:** Orchestration depends on both fetching and parsing working correctly. Building the CLI before the parser means testing with incomplete data.
- **Phases 4-5 are independent of each other:** Enrichment and hardening can proceed in parallel or in either order based on need. They are separated from core functionality to prevent scope creep.
- **Anti-detection in Phase 1, not Phase 5:** Research unanimously shows that building the scraper with requests/httpx first and "adding anti-detection later" is a project-rewriting mistake. The TLS fingerprint layer must be chosen from the start.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Needs empirical testing of curl_cffi against HLTV's current Cloudflare configuration. Community reports suggest standard-tier protection, but exact rate limits and challenge triggers are unknown. Budget 1-2 days for discovery testing with 10-20 requests.
- **Phase 2:** Needs hands-on HTML inspection of actual HLTV match pages to build accurate selector maps. Existing scraper projects provide starting points but selectors may be outdated. Test against BO1, BO3, BO5, forfeit, and overtime match pages.
- **Phase 4:** Rating 3.0 HTML structure needs verification -- launched August 2025, so older matches have Rating 2.0/2.1 format. Economy data availability for historical matches is MEDIUM confidence and needs empirical check.

Phases with standard patterns (skip research-phase):
- **Phase 3:** CLI orchestration, incremental updates, and UPSERT deduplication are well-documented patterns with no HLTV-specific complexity.
- **Phase 5:** Proxy rotation and browser fallback are standard scraping infrastructure. SeleniumBase UC Mode documentation is thorough.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All library versions verified via PyPI (Feb 2026 releases). curl_cffi and SeleniumBase are actively maintained. TLS impersonation approach validated by multiple community sources. |
| Features | MEDIUM-HIGH | Data inventory cross-referenced against gigobyte/HLTV Node.js API, multiple Python scrapers, and HLTV's Rating 3.0 announcement. Economy data availability for historical matches is uncertain. |
| Architecture | MEDIUM-HIGH | Five-layer pipeline pattern validated by 4+ existing HLTV scraper projects. Raw-HTML-first pattern is unanimous recommendation. Scale estimates (50K-100K matches, 2-10 day bulk scrape) are reasonable but need validation. |
| Pitfalls | HIGH | Critical pitfalls (TLS detection, IP bans, silent data loss, no checkpoint) are documented across multiple independent HLTV scraper projects and confirmed by Cloudflare's own documentation. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **HLTV Cloudflare configuration level:** Is it standard or enterprise tier? Determines whether curl_cffi alone suffices or SeleniumBase fallback is immediately needed. Resolve with 10-20 test requests in Phase 1.
- **Match detail page data completeness:** Does the match page at /matches/{id} contain full per-map player stats inline, or must separate /stats/matches/mapstatsid/{id} pages always be fetched? This determines whether total requests per match is 1 or 1-3. Resolve by inspecting actual HTML in Phase 2.
- **Rating 3.0 page structure:** How does the scoreboard HTML differ for matches before vs after August 2025? Need dual-format parsing or can old format be ignored? Resolve during Phase 2 selector development.
- **Economy data for historical matches:** HLTV shows economy data during live matches, but it is unclear whether this data persists on completed match pages. MEDIUM confidence. Resolve with empirical check during Phase 4.
- **Peewee vs raw sqlite3:** MEDIUM confidence recommendation. If project stays under ~10 models, raw sqlite3 with handwritten SQL is a valid alternative. Evaluate during Phase 1 schema design.

## Sources

### Primary (HIGH confidence)
- [curl_cffi 0.14.0 on PyPI](https://pypi.org/project/curl-cffi/) -- TLS impersonation capabilities, version compatibility
- [SeleniumBase 4.46.5 on PyPI](https://pypi.org/project/seleniumbase/) -- UC Mode documentation, Cloudflare bypass
- [selectolax 0.4.6 on PyPI](https://pypi.org/project/selectolax/) -- Parser benchmarks, CSS selector support
- [Pydantic 2.12.5 on PyPI](https://pypi.org/project/pydantic/) -- Validation capabilities
- [gigobyte/HLTV Node.js API](https://github.com/gigobyte/HLTV) -- Authoritative HLTV page structure and data field reference
- [HLTV Rating 3.0 Announcement](https://www.hltv.org/news/42485/introducing-rating-30) -- New scoreboard fields and metrics
- [Cloudflare JA3/JA4 fingerprint docs](https://developers.cloudflare.com/bots/additional-configurations/ja3-ja4-fingerprint/) -- TLS detection mechanisms

### Secondary (MEDIUM confidence)
- [hltv-async-api](https://github.com/akimerslys/hltv-async-api) -- Python async scraper patterns, retry/proxy configuration, 403 handling
- [nmwalsh/HLTV-Scraper](https://github.com/nmwalsh/HLTV-Scraper) -- Incremental scraping, multi-map data flattening issues
- [jparedesDS/hltv-scraper](https://github.com/jparedesDS/hltv-scraper) -- Selenium + undetected-chromedriver approach, player stat extraction
- [gelbling/HLTV.org-Scraper](https://github.com/gelbling/HLTV.org-Scraper) -- Scrapy approach, team name cleanup, 3000+ match dataset
- [ZenRows: Bypass Cloudflare 2026](https://www.zenrows.com/blog/bypass-cloudflare) -- Detection methods and bypass strategies

### Tertiary (LOW confidence, needs validation)
- HLTV rate limit thresholds (~20-30 req/min reported) -- based on community anecdotes, not measured empirically
- Total CS2 match count (50K-100K estimated) -- extrapolated from ~100 matches/day across all tiers
- Camoufox as future fallback option -- currently beta (v146.0.1-beta.25), maintenance disrupted, revisit in 6 months

---
*Research completed: 2026-02-14*
*Ready for roadmap: yes*
