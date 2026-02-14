# Feature Landscape

**Domain:** Web scraper for HLTV.org CS2 match statistics
**Researched:** 2026-02-14
**Overall confidence:** MEDIUM-HIGH

---

## HLTV Match Page Data Inventory

Before mapping features, here is what data is actually available on HLTV match pages. This is based on cross-referencing the unofficial HLTV Node.js API (gigobyte/HLTV), multiple Python scraper projects, and HLTV's own Rating 3.0 announcement.

### Match-Level Data (from match page `/matches/{id}/{slug}`)

| Field | Description | Confidence |
|-------|-------------|------------|
| Match ID | Unique numeric identifier | HIGH |
| Stats ID | Separate ID linking to stats page | HIGH |
| Date/time | Match start timestamp | HIGH |
| Status | Upcoming / Live / Finished | HIGH |
| Format | Best-of-1 / Best-of-3 / Best-of-5, LAN/Online | HIGH |
| Significance | Match tier/importance indicator | MEDIUM |
| Team 1 / Team 2 | Team IDs, names, logos | HIGH |
| Winner team | Which team won | HIGH |
| Map vetoes | Full pick/ban sequence with team attribution | HIGH |
| Map results | Per-map scores (total rounds, CT/T half scores) | HIGH |
| Player rosters | Players for each team with IDs | HIGH |
| Event | Tournament/event ID, name, logo | HIGH |
| Head-to-head history | Past match results between these teams | HIGH |
| Betting odds | Provider odds (multiple bookmakers) | HIGH |
| Player of the match | Highlighted player | HIGH |
| Highlighted players | Notable performers per team | MEDIUM |
| Demos | Download links for match demos | HIGH |
| Highlights | Video highlight clips | MEDIUM |
| Streams | Live stream links | MEDIUM |

### Per-Map Statistics (from stats page `/stats/matches/mapstatsid/{id}/{slug}`)

| Field | Description | Confidence |
|-------|-------------|------------|
| Map name | Which map was played | HIGH |
| Total rounds | Rounds per team, half breakdown | HIGH |
| Round history | Round-by-round outcomes (win type: bomb, elimination, defuse, time) | HIGH |

#### Per-Player Stats (per map)

| Field | Description | Confidence |
|-------|-------------|------------|
| Kills | Total kills | HIGH |
| Deaths | Total deaths | HIGH |
| Assists | Total assists | HIGH |
| Flash assists | Kills enabled by player's flashbangs | HIGH |
| Headshot kills | Kills via headshot | HIGH |
| Kill/Death difference | K - D | HIGH |
| K/D ratio | Kills / Deaths | HIGH |
| ADR | Average damage per round | HIGH |
| KAST% | Rounds with Kill, Assist, Survived, or Traded | HIGH |
| First kills difference | Opening kills minus opening deaths | HIGH |
| Kills per round | KPR | HIGH |
| Deaths per round | DPR | HIGH |
| Impact rating | Legacy impact metric | HIGH |
| Rating 2.0 / 2.1 | HLTV performance rating (legacy) | HIGH |
| Rating 3.0 | Current HLTV performance rating (since Aug 2025) | HIGH |
| Round Swing | Impact on round win probability per kill (Rating 3.0) | MEDIUM |
| Multi-kill rating | Rating for multi-kill rounds (Rating 3.0) | MEDIUM |
| Eco-adjusted stats | Stats adjusted for economy advantage/disadvantage | MEDIUM |
| Openers | Opening kills count (shown on scoreboard) | MEDIUM |
| Multis | Multi-kill round count (shown on scoreboard) | MEDIUM |
| Clutches | Clutch round wins (shown on scoreboard) | MEDIUM |

#### Performance Overview (per map, per team)

| Field | Description | Confidence |
|-------|-------------|------------|
| CT/T round wins | Rounds won on each side | HIGH |
| First kills | Which team got opening kill per round | MEDIUM |
| Equipment value | Economy data per round | MEDIUM |

### Aggregate Match Statistics (from stats page `/stats/matches/{id}/{slug}`)

All the per-player stats above aggregated across all maps in the match, plus:

| Field | Description | Confidence |
|-------|-------------|------------|
| Map stats IDs | Links to individual map stat pages | HIGH |
| Maps won per team | Series score | HIGH |

### Results Listing Page (`/results`)

| Field | Description | Confidence |
|-------|-------------|------------|
| Match ID | For linking to detail page | HIGH |
| Teams and scores | Team names + final score | HIGH |
| Event name | Tournament context | HIGH |
| Match format | BO1/BO3/BO5 | HIGH |
| Star rating | Match significance (0-5 stars) | HIGH |
| Date | When the match was played | HIGH |

---

## Table Stakes

Features users expect from any production-quality HLTV scraper. Missing any of these and the scraper is functionally useless or unreliable for its stated purpose.

### TS-1: Match Results Discovery and Pagination

| Attribute | Detail |
|-----------|--------|
| **What** | Navigate HLTV results pages, extract match IDs across all pages |
| **Why expected** | Cannot scrape match data without first finding matches |
| **Complexity** | Medium |
| **Notes** | HLTV results page uses offset-based pagination. Must handle filters for date ranges and event types. Star rating filter useful for tier separation. |

### TS-2: Individual Match Page Parsing

| Attribute | Detail |
|-----------|--------|
| **What** | Extract all structured data from a single match page: teams, scores, vetoes, event, format, date |
| **Why expected** | Core purpose of the scraper |
| **Complexity** | Medium |
| **Notes** | Match page has two main URL patterns: `/matches/{id}/{slug}` for match overview and `/stats/matches/{statsId}/{slug}` for detailed stats. Both must be scraped. |

### TS-3: Per-Map Player Statistics Extraction

| Attribute | Detail |
|-----------|--------|
| **What** | Extract full player scoreboard per map: kills, deaths, assists, ADR, KAST, rating, flash assists, HS kills, first kills diff |
| **Why expected** | Per-map stats are the most granular and valuable data for analysis models |
| **Complexity** | Medium |
| **Notes** | Stats page at `/stats/matches/mapstatsid/{id}/{slug}`. Each map in a BO3 is a separate stats page. Must follow links from match page to each map's stats page. |

### TS-4: Anti-Detection / Rate Limiting

| Attribute | Detail |
|-----------|--------|
| **What** | Randomized delays, proper User-Agent rotation, request throttling to avoid IP bans |
| **Why expected** | HLTV uses Cloudflare protection. Without this, scraper will be blocked within minutes |
| **Complexity** | Medium-High |
| **Notes** | HLTV is known to ban IPs aggressively. The unofficial Node.js API explicitly warns about this. Random delays between 2-10 seconds are the baseline. Must handle 403 responses with exponential backoff. |

### TS-5: Data Persistence / Storage

| Attribute | Detail |
|-----------|--------|
| **What** | Store scraped data in structured format (database or structured files) with proper schema |
| **Why expected** | Raw HTML is useless; data must be queryable for analysis |
| **Complexity** | Medium |
| **Notes** | SQLite is the pragmatic choice for a single-user scraper. CSV export as secondary output. Must handle relational data: matches have maps, maps have player stats. |

### TS-6: Error Handling and Retry Logic

| Attribute | Detail |
|-----------|--------|
| **What** | Graceful handling of HTTP errors (403, 429, 503, timeouts), automatic retries with backoff, partial failure recovery |
| **Why expected** | Bulk scraping thousands of matches will inevitably encounter errors. Crashing on the first error makes the scraper unusable. |
| **Complexity** | Medium |
| **Notes** | The hltv-async-api project uses up to 10 retries with progressive delays (1-10s). 403 specifically indicates Cloudflare blocking. 429 indicates rate limiting. Different strategies needed for each. |

### TS-7: Incremental/Resume Capability

| Attribute | Detail |
|-----------|--------|
| **What** | Track which matches have been scraped, skip already-scraped matches, resume after interruption |
| **Why expected** | Scraping all CS2 era matches (thousands) takes hours/days. Must be able to stop and resume without re-scraping everything. |
| **Complexity** | Medium |
| **Notes** | nmwalsh/HLTV-Scraper implements this by comparing new match IDs against existing CSV data. A scraping state table in the database is cleaner. |

### TS-8: Map Veto Data Extraction

| Attribute | Detail |
|-----------|--------|
| **What** | Extract the full pick/ban sequence: which team removed/picked which map, in what order |
| **Why expected** | Veto data is critical for prediction models (reveals team map preferences and strategies) |
| **Complexity** | Low |
| **Notes** | Available directly on the match page. The gigobyte/HLTV API confirms `vetoes` as an array in the match schema. |

### TS-9: Logging and Progress Reporting

| Attribute | Detail |
|-----------|--------|
| **What** | Structured logging of scraping progress, errors, and statistics (matches scraped, failed, remaining) |
| **Why expected** | Long-running bulk scrapes need visibility into progress and failure patterns |
| **Complexity** | Low |
| **Notes** | Simple but essential. Log to file + console. Include timestamps, match IDs, HTTP status codes. |

---

## Differentiators

Features that add significant value but are not strictly required for basic functionality. These separate a good scraper from a great one.

### D-1: Round-by-Round History Extraction

| Attribute | Detail |
|-----------|--------|
| **What** | Extract the round history timeline showing outcome of each round (bomb planted, CT elimination, time ran out, etc.) |
| **Value proposition** | Enables round-level analysis: comeback patterns, eco round success rates, side switches |
| **Complexity** | Medium |
| **Notes** | Available on map stats pages. The gigobyte/HLTV API confirms `roundHistory` as a `RoundOutcome[]` array. Extremely valuable for prediction models. |

### D-2: Economy/Equipment Value Data

| Attribute | Detail |
|-----------|--------|
| **What** | Extract per-round economy data showing team equipment values |
| **Value proposition** | Economy management is a key factor in CS2 match outcomes. Essential for sophisticated prediction models. |
| **Complexity** | Medium-High |
| **Notes** | HLTV shows economy data during live matches and Rating 3.0 uses seven economy categories for eco-adjustment. Historical economy data availability on completed match pages needs verification during implementation. MEDIUM confidence this is fully available for historical matches. |

### D-3: Head-to-Head History Extraction

| Attribute | Detail |
|-----------|--------|
| **What** | Extract historical matchup results between two teams shown on match pages |
| **Value proposition** | Head-to-head records are a strong predictor in matchup analysis |
| **Complexity** | Low |
| **Notes** | Confirmed available in match page data (`headToHead` array in gigobyte/HLTV schema). Easy to extract since it is on the same page as match data. |

### D-4: Event/Tournament Metadata

| Attribute | Detail |
|-----------|--------|
| **What** | Scrape event pages for tournament context: prize pool, tier, location, format, participating teams |
| **Value proposition** | Match importance varies enormously by event. A Major final vs an online qualifier carry different weight for models. |
| **Complexity** | Medium |
| **Notes** | Requires scraping a separate page type (`/events/{id}/{slug}`). Event ID is already linked from match data. |

### D-5: Proxy Rotation Support

| Attribute | Detail |
|-----------|--------|
| **What** | Support rotating through multiple proxy IPs to distribute requests and avoid bans |
| **Value proposition** | Enables faster scraping and resilience against IP-based blocking |
| **Complexity** | Medium |
| **Notes** | The hltv-async-api supports proxy lists with automatic failed proxy removal. For bulk scraping of thousands of matches, this becomes near-essential. Could be considered table stakes if scraping volume is very high. |

### D-6: Data Validation and Integrity Checks

| Attribute | Detail |
|-----------|--------|
| **What** | Validate extracted data against expected schemas: correct number of players (5 per team), round counts matching score, non-null required fields |
| **Value proposition** | Prevents garbage data from reaching analysis models. HLTV pages sometimes have missing data for forfeited matches, admin decisions, or very old matches. |
| **Complexity** | Medium |
| **Notes** | Cross-field validation: kills per team should roughly equal deaths of opposing team. Total rounds should match sum of half scores. Rating should be within reasonable bounds (0.0-3.0). |

### D-7: Team and Player Entity Resolution

| Attribute | Detail |
|-----------|--------|
| **What** | Maintain a canonical mapping of team and player IDs, handling name changes, roster moves, and org rebrands |
| **Value proposition** | HLTV uses stable numeric IDs for teams and players, but display names change frequently. Entity resolution ensures consistent tracking across the dataset. |
| **Complexity** | Low-Medium |
| **Notes** | HLTV assigns stable numeric IDs which makes this simpler than many entity resolution problems. The scraper should store both the ID and the display name at time of match. |

### D-8: Configurable Scraping Scope

| Attribute | Detail |
|-----------|--------|
| **What** | Filter scraping by: date range, event, team, match tier (star rating), match format |
| **Value proposition** | Enables targeted scraping instead of all-or-nothing. Useful for updating specific event data or focusing on top-tier matches. |
| **Complexity** | Low-Medium |
| **Notes** | HLTV results page supports URL parameters for filtering. Exposing these as scraper configuration is straightforward. |

### D-9: Demo Download Links Collection

| Attribute | Detail |
|-----------|--------|
| **What** | Extract and catalog GOTV demo download URLs from match pages |
| **Value proposition** | Demos contain the richest possible data (every player position, every shot, economy per round). Enables future deep analysis. |
| **Complexity** | Low |
| **Notes** | Demo links are on the match page (confirmed in gigobyte/HLTV schema). Downloading the actual demo files is a separate concern from collecting the URLs. |

### D-10: Export to Multiple Formats

| Attribute | Detail |
|-----------|--------|
| **What** | Export data to CSV, JSON, and potentially Parquet for direct use in data science workflows |
| **Value proposition** | Different consumers need different formats. CSV for quick inspection, JSON for APIs, Parquet for large-scale analysis in pandas/polars. |
| **Complexity** | Low |
| **Notes** | Most existing scrapers only output CSV. JSON and Parquet are trivial to add if the internal data model is clean. |

### D-11: Rating 3.0 Field Extraction

| Attribute | Detail |
|-----------|--------|
| **What** | Extract the new Rating 3.0 sub-ratings: Round Swing, Multi-kill rating, eco-adjusted figures, T/CT split ratings |
| **Value proposition** | Rating 3.0 (launched August 2025) is the most current player evaluation metric. Models using outdated Rating 2.0 are at a disadvantage. |
| **Complexity** | Medium |
| **Notes** | Rating 3.0 adds new scoreboard fields (openers, multis, clutches) and separate performance panels. HTML structure likely differs from pre-August-2025 pages. Need to handle both old and new page formats. |

---

## Anti-Features

Features to deliberately NOT build. These are common mistakes in scraper projects that waste effort or create problems.

### AF-1: Real-Time / Live Match Scraping

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Scraping live match data in real-time via page polling | HLTV has a scorebot WebSocket for live data, but scraping live pages hammers their servers, triggers anti-bot immediately, and the data quality is poor mid-match. Live scraping is the fastest way to get permanently banned. | Focus exclusively on completed match results. If live data is needed in the future, investigate the HLTV scorebot WebSocket API as a separate project. |

### AF-2: User Authentication / Login Scraping

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Logging into HLTV accounts to access premium or user-specific data | Violates terms of service more aggressively. Adds session management complexity. No match stats require authentication. | All match statistics are publicly accessible. No login needed. |

### AF-3: Scraping Player Profile Pages at Scale

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Scraping every player's full career stats page (separate from match data) | Massive scope expansion. Player career stats are aggregations of match data you are already collecting. Doubles or triples the number of pages to scrape. | Extract player stats from match pages where they appear naturally. Career aggregations can be computed from your own match dataset. |

### AF-4: Full Browser Rendering for Every Page

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Using Selenium/Playwright with full browser for every single page request | 10-100x slower than HTTP requests. Massive memory footprint. For thousands of matches, this is impractical. | Use plain HTTP requests with proper headers as the primary method. Only fall back to browser automation if Cloudflare challenge pages cannot be bypassed with simpler methods (e.g., cloudscraper, curl_cffi). Use a headless browser sparingly to solve initial challenges then reuse cookies. |

### AF-5: Building a Web UI / Dashboard

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Building a web interface to browse scraped data | Scope creep. The scraper's job is to collect and store data. Visualization is a separate project. | Export clean data to formats that existing tools (pandas, Jupyter, Tableau, custom analysis scripts) can consume directly. |

### AF-6: Scraping Forum Posts, News, or Comments

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Scraping HLTV news articles, forum threads, or match comments | Not match statistics data. Different page structures. Massive volume of unstructured text. Zero value for match prediction models. | Stay focused on structured match statistics only. |

### AF-7: Building a General-Purpose Scraping Framework

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Abstracting the scraper into a configurable framework that could scrape any site | Over-engineering. HLTV has a specific page structure. A general framework adds complexity without value for a single-site scraper. | Build purpose-specific parsers for HLTV's known page types. Keep the code simple and direct. |

### AF-8: Automated Scheduling / Cron Integration (Initially)

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Building scheduler integration before the core scraper works | Premature optimization. Get the scraper working reliably first. Scheduling is trivial to add later (OS cron, Windows Task Scheduler). | Build the scraper as a CLI tool that can be run manually or via external scheduler. Incremental mode (TS-7) is the prerequisite. |

---

## Feature Dependencies

```
TS-1: Match Discovery -----> TS-2: Match Page Parsing -----> TS-3: Per-Map Stats
        |                           |                              |
        |                           |---> TS-8: Map Veto           |
        |                           |---> D-3: Head-to-Head        |
        |                           |---> D-9: Demo Links          |
        |                                                          |
        |                                                     D-1: Round History
        |                                                     D-2: Economy Data
        |                                                     D-11: Rating 3.0
        |
   TS-7: Resume/Incremental (needs TS-5: Storage)
        |
   TS-5: Storage <---- TS-6: Error Handling
        |
   D-6: Data Validation
   D-7: Entity Resolution
   D-10: Export Formats

TS-4: Anti-Detection (independent, applies to all HTTP requests)
TS-9: Logging (independent, applies to everything)

D-4: Event Metadata (independent scraping target, needs TS-4, TS-5)
D-5: Proxy Rotation (enhances TS-4, independent implementation)
D-8: Configurable Scope (modifies TS-1, independent implementation)
```

### Dependency Summary

| Feature | Depends On | Blocks |
|---------|-----------|--------|
| TS-1: Match Discovery | Nothing | TS-2, TS-7 |
| TS-2: Match Page Parsing | TS-1 | TS-3, TS-8, D-3, D-9 |
| TS-3: Per-Map Stats | TS-2 | D-1, D-2, D-11 |
| TS-4: Anti-Detection | Nothing | Nothing (cross-cutting) |
| TS-5: Storage | Nothing | TS-7, D-6, D-7, D-10 |
| TS-6: Error Handling | Nothing | Nothing (cross-cutting) |
| TS-7: Resume/Incremental | TS-1, TS-5 | Nothing |
| TS-8: Map Veto | TS-2 | Nothing |
| TS-9: Logging | Nothing | Nothing (cross-cutting) |
| D-1: Round History | TS-3 | Nothing |
| D-2: Economy Data | TS-3 | Nothing |
| D-3: Head-to-Head | TS-2 | Nothing |
| D-4: Event Metadata | TS-4, TS-5 | Nothing |
| D-5: Proxy Rotation | TS-4 | Nothing |
| D-6: Data Validation | TS-5 | Nothing |
| D-7: Entity Resolution | TS-5 | Nothing |
| D-8: Configurable Scope | TS-1 | Nothing |
| D-9: Demo Links | TS-2 | Nothing |
| D-10: Export Formats | TS-5 | Nothing |
| D-11: Rating 3.0 | TS-3 | Nothing |

---

## MVP Recommendation

For MVP, prioritize building a scraper that can reliably extract complete match data for any given match, with enough infrastructure to run bulk scrapes without crashing or getting banned.

### MVP Must-Haves (in build order)

1. **TS-4: Anti-Detection** -- Without this, nothing else works. Build the HTTP layer with proper headers, randomized delays, and backoff first.
2. **TS-9: Logging** -- Essential for debugging during development.
3. **TS-5: Storage** -- Schema design and database setup. SQLite with proper relational model.
4. **TS-6: Error Handling** -- Retry logic and graceful failure handling.
5. **TS-1: Match Discovery** -- Paginate through results pages, collect match IDs.
6. **TS-2: Match Page Parsing** -- Extract match metadata, teams, scores, vetoes.
7. **TS-8: Map Veto** -- Extract alongside match page (same page, low additional cost).
8. **TS-3: Per-Map Stats** -- Follow links to map stats pages, extract full player scoreboards.
9. **TS-7: Resume/Incremental** -- Track scraping state so bulk runs can be interrupted and resumed.

### Defer to Post-MVP

- **D-1: Round History** -- Valuable but requires additional parsing of map stats pages. Add once core stats extraction is solid.
- **D-2: Economy Data** -- Medium confidence on availability for historical matches. Investigate during implementation.
- **D-3: Head-to-Head** -- Easy to add, but not blocking for initial data collection.
- **D-4: Event Metadata** -- Separate scraping target, can be added independently.
- **D-5: Proxy Rotation** -- Not needed until scraping volume demands it. Start with single-IP with conservative delays.
- **D-6: Data Validation** -- Important but can be run as a post-processing step initially.
- **D-7: Entity Resolution** -- HLTV's stable IDs make this low urgency.
- **D-8: Configurable Scope** -- Hardcode initial scope, parameterize later.
- **D-9: Demo Links** -- Easy add-on once match page parsing works.
- **D-10: Export Formats** -- SQLite is sufficient initially. CSV/JSON export is trivial to add.
- **D-11: Rating 3.0** -- Depends on when match pages started showing 3.0 data. Older matches will have 2.0/2.1 only.

---

## Sources

### Verified (HIGH confidence)
- [gigobyte/HLTV - Unofficial Node.js API](https://github.com/gigobyte/HLTV) -- Authoritative reference for HLTV match page data structure. Source code confirms exact fields returned by getMatch, getMatchStats, getMatchMapStats.
- [HLTV Rating 3.0 Announcement](https://www.hltv.org/news/42485/introducing-rating-30) -- Official HLTV source for Rating 3.0 fields and scoreboard changes.
- [akimerslys/hltv-async-api](https://github.com/akimerslys/hltv-async-api) -- Python async scraper with retry logic and proxy support, confirms anti-detection patterns.
- [nmwalsh/HLTV-Scraper](https://github.com/nmwalsh/HLTV-Scraper) -- Python scraper with incremental scraping and multi-threaded architecture.

### Cross-Referenced (MEDIUM confidence)
- [jparedesDS/hltv-scraper](https://github.com/jparedesDS/hltv-scraper) -- CS2 scraper using Selenium + undetected-chromedriver, confirms player stat field list.
- [gelbling/HLTV.org-Scraper](https://github.com/gelbling/HLTV.org-Scraper) -- Scrapy-based scraper, confirms data volume (3000+ matches, 750K+ data points).
- [OttScrape - Extract Individual Match Stats](https://www.ottscrape.com/extract-individual-match-stats-from-hltv.php) -- Third-party extraction guide confirming available match page fields.
- [HLTV Kaggle Dataset](https://www.kaggle.com/datasets/dimitryzub/hltv-csgo-match-stats) -- Example of scraped HLTV data in structured format.

### Community Sources (LOW confidence, for context only)
- [ZenRows - Bypass Cloudflare](https://www.zenrows.com/blog/bypass-cloudflare) -- Anti-bot bypass techniques.
- [Scrape.do - Rate Limit Bypass](https://scrape.do/blog/web-scraping-rate-limit/) -- Rate limiting strategies.
- [ScraperAPI - Best Practices](https://www.scraperapi.com/web-scraping/best-practices/) -- General scraping best practices.
- [Rating 3.0 Adjustments](https://www.hltv.org/news/43047/rating-30-adjustments-go-live) -- Official HLTV source for Rating 3.0 updates.
