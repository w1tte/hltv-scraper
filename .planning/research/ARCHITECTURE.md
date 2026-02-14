# Architecture Patterns

**Domain:** HLTV.org CS2 Match Data Scraper
**Researched:** 2026-02-14
**Overall Confidence:** MEDIUM-HIGH

## Executive Summary

The scraper should be built as a **five-layer pipeline** with clear boundaries: URL discovery, page fetching (with anti-detection), HTML parsing, data transformation, and persistent storage. The critical architectural insight is that **fetching and parsing must be completely decoupled** -- HLTV's anti-scraping measures mean the fetching layer will change frequently (new Cloudflare bypasses, proxy rotation strategies), while the parsing layer will change when HLTV redesigns their HTML. These changes happen independently and for different reasons, so coupling them is the most common architectural mistake in HLTV scrapers.

The second critical insight is that **raw HTML should be stored before parsing**. This decouples scraping speed from parsing correctness -- you can fix a parser bug and re-process stored HTML without re-fetching (and risking bans). Every major HLTV scraper project on GitHub that did NOT do this eventually regretted it when selectors broke and data was lost.

---

## Recommended Architecture

```
+------------------+     +------------------+     +------------------+
|  URL DISCOVERY   |---->|   PAGE FETCHER   |---->|  RAW HTML STORE  |
|  (Coordinator)   |     | (Anti-Detection) |     |   (File/Blob)    |
+------------------+     +------------------+     +--------+---------+
        ^                                                  |
        |                                                  v
+------------------+     +------------------+     +------------------+
| CHECKPOINT/STATE |<----|  STRUCTURED DB   |<----|   HTML PARSER    |
|   (Resume Log)   |     | (SQLite/Parquet) |     | (Selector Layer) |
+------------------+     +------------------+     +------------------+
```

### Data Flow (Numbered Steps)

1. **URL Discovery** reads `/results?offset=N` pages to collect match IDs
2. **Checkpoint** is consulted: "Have I already fetched match ID 2361342?" -- skip if yes
3. **Page Fetcher** retrieves the match detail page through the anti-detection layer
4. **Raw HTML Store** saves the complete HTML response to disk (keyed by match ID + page type)
5. **HTML Parser** extracts structured data from stored HTML using the selector abstraction layer
6. **Structured DB** receives cleaned, validated records (matches, maps, player stats)
7. **Checkpoint** is updated: match ID marked as fully processed

### Why This Order Matters

The pipeline is designed so that the **most failure-prone step (fetching) happens before any data transformation**. If the fetcher gets blocked or crashes, you lose nothing -- already-fetched HTML is safely stored. If the parser has a bug, you fix it and re-parse from stored HTML without touching HLTV's servers.

---

## Component Boundaries

### Component 1: URL Discovery (Coordinator)

**Responsibility:** Discover all match IDs that need scraping.

**Input:** Configuration (date range, offset start, match tiers).
**Output:** Ordered queue of match IDs to fetch.

**How it works:**
- Paginates through `https://www.hltv.org/results?offset=N` (100 matches per page)
- Can filter by date range: `?startDate=2023-09-01&endDate=2026-02-14`
- Extracts match IDs and basic metadata (teams, date, event name) from listing
- Compares against checkpoint store to skip already-collected matches
- Produces a work queue of "match IDs to fetch"

**Key design decisions:**
- Listing pages are lightweight (no player stats), so they can be scraped more aggressively
- Store discovered match IDs even before fetching detail pages (the discovery itself is valuable)
- Support both "full sweep" (all offsets) and "incremental" (stop when hitting known matches) modes

**Communicates with:** Checkpoint Store (read), Page Fetcher (write to queue)

---

### Component 2: Page Fetcher (Anti-Detection Layer)

**Responsibility:** Retrieve HTML from HLTV without getting blocked.

**Input:** URL to fetch.
**Output:** Raw HTML string + HTTP metadata (status, headers, timestamp).

**How it works:**
- Wraps the actual HTTP mechanism (browser automation or HTTP client)
- Implements rate limiting, delay randomization, proxy rotation
- Handles retries with exponential backoff
- Detects block signals (403, CAPTCHA pages, empty responses)
- Escalates fetching strategy when blocks are detected

**Anti-detection strategy (layered):**

| Layer | Tool | When Used |
|-------|------|-----------|
| 1. Stealth HTTP | `curl_cffi` or `httpx` with browser TLS fingerprint | Default -- fastest, lowest resource |
| 2. Headless browser | `nodriver` (async, undetected Chrome) | When Layer 1 gets blocked |
| 3. Stealth browser | Camoufox (Firefox with C++ fingerprint spoofing) | When Layer 2 gets blocked |
| 4. Manual/API | Proxy API service (ScrapingBee, ScrapFly) | Last resort, has cost |

**Key design decisions:**
- Start with the lightest approach and escalate only when needed
- The fetcher exposes a simple interface: `fetch(url) -> html` -- callers do not know which strategy is in use
- Rate limiting is built into this layer, not the caller: 3-8 second random delays between requests to HLTV
- Proxy rotation: residential proxies preferred (higher trust score with Cloudflare)
- Circuit breaker pattern: if N consecutive requests fail, pause for M minutes before retrying

**Communicates with:** URL Discovery (receives URLs), Raw HTML Store (writes HTML)

---

### Component 3: Raw HTML Store

**Responsibility:** Persist fetched HTML pages to disk for offline parsing.

**Input:** HTML string, match ID, page type, fetch timestamp.
**Output:** File path to stored HTML.

**Storage structure:**
```
data/
  raw/
    results/                    # Listing pages
      offset_0000.html
      offset_0100.html
    matches/                    # Match detail pages
      2361342.html
      2361343.html
    mapstats/                   # Per-map stat pages (if separate fetch needed)
      2361342_map1.html
      2361342_map2.html
```

**Key design decisions:**
- Plain HTML files, not a database -- easy to inspect, debug, and version
- File naming by match ID makes deduplication trivial
- Optional: gzip compression for storage efficiency (HTML compresses ~90%)
- This store enables "parse-only" mode: re-run parser without any network requests
- Retention policy: keep raw HTML at least until parsed data is validated

**Communicates with:** Page Fetcher (receives HTML), HTML Parser (provides HTML on demand)

---

### Component 4: HTML Parser (Selector Abstraction Layer)

**Responsibility:** Extract structured data from raw HTML using CSS selectors.

**Input:** Raw HTML string, page type identifier.
**Output:** Structured Python dictionaries / dataclass instances.

**Critical design: Selector abstraction for maintainability**

HLTV will change their HTML. It has happened before and will happen again. The parser MUST isolate selectors from logic.

```python
# BAD: Selectors mixed into logic
def parse_match(html):
    soup = BeautifulSoup(html)
    team1 = soup.select_one('div.team1-gradient .teamName').text  # Breaks when class changes
    score1 = soup.select_one('div.team1-gradient .score').text

# GOOD: Selector map separated from extraction logic
MATCH_SELECTORS = {
    "team1_name": "div.team1-gradient .teamName",
    "team1_score": "div.team1-gradient .score-won, div.team1-gradient .score-lost",
    "team2_name": "div.team2-gradient .teamName",
    "team2_score": "div.team2-gradient .score-won, div.team2-gradient .score-lost",
    "date": "div.date",
    "event": "div.event a",
    "map_tabs": "div.mapholder",
}

def parse_match(html, selectors=MATCH_SELECTORS):
    soup = BeautifulSoup(html, 'lxml')
    return {
        key: extract(soup, sel)
        for key, sel in selectors.items()
    }
```

When HLTV changes HTML, you update the selector map. The extraction logic stays stable. You can even version selector maps to handle pages fetched before/after a redesign.

**Page types and their data:**

| Page Type | URL Pattern | Data Extracted |
|-----------|-------------|----------------|
| Results listing | `/results?offset=N` | Match IDs, team names, scores, dates, event names |
| Match detail | `/matches/{id}/{slug}` | Teams, final score, map vetoes, map scores, event info |
| Map stats | `/stats/matches/mapstatsid/{id}/{slug}` | Per-map player stats (kills, deaths, ADR, KAST, rating, etc.) |

**Key design decisions:**
- Use `BeautifulSoup` with `lxml` parser (fastest pure-Python HTML parser)
- Selector maps are data, not code -- store in YAML/JSON/Python dict for easy updates
- Each page type has its own parser function and selector map
- Validation layer: parsed data is checked for completeness before storage (e.g., "match must have 2 teams, 1-5 maps")
- Log warnings when selectors return None -- early detection of HTML changes

**Communicates with:** Raw HTML Store (reads HTML), Structured DB (writes parsed data)

---

### Component 5: Structured Database (SQLite)

**Responsibility:** Store parsed, validated match data in queryable format.

**Recommended: SQLite** -- because this is a single-user pipeline on a local machine, not a web service. SQLite requires no server, produces a single portable file, and handles the read-heavy analytical queries this data feeds into. The dataset (all CS2 matches since Sept 2023) is estimated at ~50K-100K matches -- well within SQLite's comfortable range.

**Schema (normalized):**

```sql
-- Core entities
CREATE TABLE matches (
    match_id      INTEGER PRIMARY KEY,  -- HLTV match ID
    date          TEXT NOT NULL,         -- ISO 8601
    event_id      INTEGER,
    event_name    TEXT,
    team1_id      INTEGER NOT NULL,
    team1_name    TEXT NOT NULL,
    team2_id      INTEGER NOT NULL,
    team2_name    TEXT NOT NULL,
    team1_score   INTEGER,              -- Maps won
    team2_score   INTEGER,
    best_of       INTEGER,              -- BO1/BO3/BO5
    url           TEXT,
    scraped_at    TEXT NOT NULL,         -- When we fetched this
    parsed_at     TEXT                   -- When we parsed this
);

-- One row per map played in a match
CREATE TABLE maps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id      INTEGER NOT NULL REFERENCES matches(match_id),
    map_number    INTEGER NOT NULL,     -- 1, 2, 3...
    map_name      TEXT NOT NULL,        -- "Mirage", "Inferno", etc.
    team1_rounds  INTEGER,
    team2_rounds  INTEGER,
    team1_ct_rounds  INTEGER,
    team1_t_rounds   INTEGER,
    team2_ct_rounds  INTEGER,
    team2_t_rounds   INTEGER,
    mapstats_id   INTEGER,              -- HLTV's mapstatsid for detailed stats
    UNIQUE(match_id, map_number)
);

-- One row per player per map
CREATE TABLE player_stats (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id      INTEGER NOT NULL REFERENCES matches(match_id),
    map_number    INTEGER NOT NULL,
    player_id     INTEGER NOT NULL,
    player_name   TEXT NOT NULL,
    team_id       INTEGER NOT NULL,
    kills         INTEGER,
    deaths        INTEGER,
    assists       INTEGER,
    adr           REAL,                 -- Average damage per round
    kast          REAL,                 -- KAST percentage
    rating        REAL,                 -- HLTV Rating 2.1
    headshots     INTEGER,
    first_kills   INTEGER,
    first_deaths  INTEGER,
    UNIQUE(match_id, map_number, player_id)
);

-- Scraping state tracking
CREATE TABLE scrape_log (
    match_id      INTEGER PRIMARY KEY,
    discovered_at TEXT NOT NULL,
    html_fetched  INTEGER DEFAULT 0,    -- Boolean
    fetched_at    TEXT,
    parsed        INTEGER DEFAULT 0,    -- Boolean
    parsed_at     TEXT,
    error         TEXT                   -- Last error message if any
);
```

**Key design decisions:**
- `scrape_log` table IS the checkpoint system -- resume capability is built into the data layer
- UNIQUE constraints prevent duplicate data on re-parse
- Use `INSERT OR REPLACE` (upsert) semantics for idempotent re-processing
- Timestamps on everything for debugging and auditing
- Export to Parquet/CSV for ML pipeline consumption (SQLite is the working store, not the delivery format)

**Communicates with:** HTML Parser (receives structured data), Checkpoint/Resume (scrape_log), ML Pipeline (via export)

---

### Component 6: Checkpoint / Resume Manager

**Responsibility:** Track what has been scraped, enable resume after interruption.

**Implementation:** This is NOT a separate service -- it is the `scrape_log` table in SQLite plus a thin query layer.

**State machine per match:**

```
DISCOVERED --> HTML_FETCHED --> PARSED --> COMPLETE
     |              |             |
     v              v             v
   FAILED       FAILED        FAILED
```

**Resume logic:**
```python
def get_pending_fetches():
    """Matches discovered but not yet fetched."""
    return db.query("SELECT match_id FROM scrape_log WHERE html_fetched = 0 AND error IS NULL")

def get_pending_parses():
    """Matches fetched but not yet parsed."""
    return db.query("SELECT match_id FROM scrape_log WHERE html_fetched = 1 AND parsed = 0 AND error IS NULL")

def get_failed():
    """Matches that failed at any stage."""
    return db.query("SELECT match_id, error FROM scrape_log WHERE error IS NOT NULL")
```

**Key design decisions:**
- Failed matches are NOT automatically retried in the same run -- they go into a "retry" queue for the next run
- Error messages are stored for debugging (was it a 403? a parse error? a timeout?)
- The coordinator checks this state before adding to the work queue
- Supports "force re-scrape" of specific match IDs for correction

---

## HLTV-Specific Page Navigation

Understanding how data flows across HLTV's pages is critical for the scraper's crawl strategy.

### Page Hierarchy

```
/results?offset=0           (100 matches per page, paginate by +100)
  |
  +--> /matches/{id}/{slug}   (match detail: teams, maps, vetoes, overview stats)
         |
         +--> /stats/matches/mapstatsid/{id}/{slug}   (per-map detailed player stats)
```

### Crawl Strategy

**Phase 1 -- Discovery (lightweight):**
Paginate `/results?offset=N` pages. Each page lists ~100 matches with basic info (teams, score, date, event). This gives us the match ID inventory. These pages are simpler and load faster.

**Phase 2 -- Detail Fetch (heavy):**
For each match ID, fetch `/matches/{id}/{slug}`. This page contains:
- Match overview (teams, final score, format)
- Map veto sequence
- Per-map scores (CT/T side rounds)
- Player stats overview (may contain enough data without needing mapstats pages)

**Phase 3 -- Deep Stats (optional, if match detail page lacks granularity):**
For each map played, fetch `/stats/matches/mapstatsid/{id}/{slug}` for granular per-map player statistics. This is only needed if the match detail page doesn't expose all desired stats.

**Important:** The match detail page (`/matches/{id}`) often contains player stat tables for each map inline. Inspect the actual HTML to determine if Phase 3 is needed -- it may be unnecessary, which would cut total requests significantly.

---

## Patterns to Follow

### Pattern 1: Fetch-Store-Parse Pipeline

**What:** Never parse HTML in the same step that fetches it. Always store raw HTML first, then parse from storage.

**Why:** When HLTV changes their HTML structure (and they will), you can update parsers and re-process stored HTML without re-fetching. When your parser has a bug, you fix it and re-run against stored HTML. You also decouple fetching speed from parsing speed.

**Build order implication:** Build the fetcher and raw storage first. Build the parser second. This lets you start accumulating data immediately, even before the parser is perfect.

### Pattern 2: Selector Maps

**What:** Externalize CSS selectors from parsing logic. Store them as data (dict/config), not hardcoded in function bodies.

**Why:** HLTV HTML changes require selector updates. If selectors are scattered through code, every change is a bug hunt. If they are centralized in a selector map, every change is a config update.

**Example:**
```python
# selectors.py -- the ONLY file that changes when HLTV updates HTML
RESULTS_PAGE = {
    "match_links": "div.result-con a.a-reset",
    "match_team1": "div.team1 .team",
    "match_team2": "div.team2 .team",
    "match_score": "span.score-won, span.score-lost",
    "match_date": "div.standard-headline",
}

MATCH_PAGE = {
    "team1_name": "div.team1-gradient .teamName",
    "team2_name": "div.team2-gradient .teamName",
    # ...
}
```

### Pattern 3: Rate Limiting as First-Class Concern

**What:** Rate limiting is not an afterthought -- it is a core architectural component with its own state and configuration.

**Why:** HLTV will ban you. The rate limiter must be:
- Configurable (delays between requests)
- Adaptive (slow down when seeing soft blocks, speed up when stable)
- Persistent (remember rate state across restarts)

**Implementation:**
```python
class RateLimiter:
    def __init__(self, min_delay=3.0, max_delay=8.0, backoff_factor=2.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.current_delay = min_delay
        self.backoff_factor = backoff_factor

    async def wait(self):
        jitter = random.uniform(-0.5, 1.5)
        await asyncio.sleep(self.current_delay + jitter)

    def backoff(self):
        """Call when a soft block is detected."""
        self.current_delay = min(self.current_delay * self.backoff_factor, self.max_delay * 3)

    def recover(self):
        """Call after successful request."""
        self.current_delay = max(self.current_delay * 0.95, self.min_delay)
```

### Pattern 4: Idempotent Operations

**What:** Every operation (fetch, parse, store) must be safe to repeat without creating duplicates or corruption.

**Why:** Crashes, network failures, and restarts are inevitable in a long-running bulk scrape. If re-running the same match ID produces the same result and does not create duplicate rows, the system is robust.

**Implementation:** UNIQUE constraints in SQLite + `INSERT OR REPLACE` semantics. The `scrape_log` table provides at-most-once semantics for fetching.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Parsing During Fetch

**What:** Parsing HTML in the same function/step that fetches it, without storing raw HTML.

**Why bad:** When the parser breaks (and it will), you must re-fetch from HLTV to fix it -- risking bans and wasting time. When you discover you missed a data field, you must re-scrape everything.

**Instead:** Always store raw HTML to disk before parsing. Parse from stored files.

### Anti-Pattern 2: Hardcoded Selectors

**What:** CSS selectors embedded directly in parsing logic throughout the codebase.

**Why bad:** When HLTV changes HTML, you must find and update selectors scattered across multiple functions. Easy to miss one, creating silent data loss.

**Instead:** Centralize selectors in a single file/dict per page type. Parsing functions reference the selector map, not raw selector strings.

### Anti-Pattern 3: No Resume Capability

**What:** A scraper that must start from scratch if interrupted.

**Why bad:** A bulk scrape of ~50K+ matches will take days at safe request rates (~3-8 seconds per request). Interruptions are guaranteed. Without resume capability, you waste days of work.

**Instead:** Track per-match state in `scrape_log`. On restart, query for unfinished work.

### Anti-Pattern 4: Aggressive Request Rates

**What:** Minimizing delays to "go fast" -- requests every 0.5-1 second.

**Why bad:** HLTV + Cloudflare will ban you. An IP ban can last hours to days. One hour of aggressive scraping can cost you days of blocked access. Multiple scrapers report bans at rates faster than ~2 second intervals.

**Instead:** 3-8 second random delays between requests. A full bulk scrape at this rate takes ~2-4 days for 50K matches. That is fine. Patience over speed.

### Anti-Pattern 5: Single Fetch Strategy

**What:** Committing to one fetching approach (e.g., only Selenium, or only requests).

**Why bad:** HLTV's anti-scraping measures change. What works today may not work next month. If your architecture is tightly coupled to one fetching library, changing it means rewriting significant code.

**Instead:** The Page Fetcher is an abstraction. Behind the interface, swap between `curl_cffi`, `nodriver`, Camoufox, or proxy APIs without changing any other component.

---

## Suggested Build Order

Based on component dependencies, build in this order:

### Phase 1: Foundation (must build first)

1. **SQLite schema + scrape_log** -- Everything depends on the data model
2. **Raw HTML storage** -- Directory structure and file naming conventions
3. **Rate limiter** -- Needed before any requests to HLTV

**Rationale:** These are the lowest-risk, highest-dependency components. Get them right first.

### Phase 2: Fetching Pipeline

4. **Page Fetcher (Layer 1: HTTP)** -- Start with `curl_cffi` or similar stealth HTTP client
5. **URL Discovery** -- Paginate `/results` pages, populate scrape_log
6. **Match Detail Fetcher** -- Fetch individual match pages, store raw HTML

**Rationale:** You need to start accumulating HTML before you can build parsers. Even if parsing is incomplete, having raw HTML stored means no wasted effort.

### Phase 3: Parsing Pipeline

7. **Selector maps** -- Define selectors for each page type (requires inspecting actual HLTV HTML)
8. **Results page parser** -- Parse listing pages for match IDs
9. **Match detail parser** -- Parse match pages for teams, scores, maps
10. **Player stats parser** -- Parse per-map player statistics

**Rationale:** Parsing is the most iterative component -- you will inspect HTML, write selectors, test, adjust. Having raw HTML stored (from Phase 2) makes this a purely offline activity.

### Phase 4: Orchestration

11. **Coordinator / CLI** -- Tie all components together with command-line interface
12. **Incremental update mode** -- "Scrape only matches newer than last run"
13. **Retry failed matches** -- Re-process matches that errored
14. **Data export** -- CSV/Parquet export for ML pipelines

**Rationale:** Orchestration is the last layer because it depends on all other components being functional.

### Phase 5: Hardening (if needed)

15. **Fetcher Layer 2: nodriver** -- Browser automation fallback
16. **Fetcher Layer 3: Camoufox** -- Heavy-duty Cloudflare bypass
17. **Proxy rotation** -- Residential proxy pool integration
18. **Monitoring/alerting** -- Detect when scraping breaks

**Rationale:** Only build these if Layer 1 fetching proves insufficient. Do not over-engineer anti-detection upfront -- test the simplest approach first.

---

## Scale Estimates

| Metric | Estimate | Confidence |
|--------|----------|------------|
| Total CS2 matches (Sept 2023 - Feb 2026) | 50,000 - 100,000 | MEDIUM (based on HLTV's ~100 matches/day across all tiers) |
| Requests per match | 1-3 (match page + optional map stats pages) | HIGH |
| Total requests for bulk scrape | 50,000 - 300,000 | MEDIUM |
| Time per request (with rate limiting) | 3-8 seconds | HIGH (intentional) |
| Total bulk scrape time | 2-10 days (continuous) | MEDIUM |
| Raw HTML storage | 5-20 GB (uncompressed), 0.5-2 GB (gzipped) | MEDIUM |
| SQLite database size | 50-200 MB | MEDIUM |
| Incremental daily update | 50-150 new matches, ~10-30 minutes | MEDIUM |

---

## Technology Choices (Architecture-Relevant)

| Component | Recommendation | Why |
|-----------|---------------|-----|
| HTTP client | `curl_cffi` | TLS fingerprint mimicking, fastest stealth HTTP option |
| Browser fallback | `nodriver` | Async, undetected Chrome, actively maintained successor to undetected-chromedriver |
| Heavy fallback | Camoufox | Firefox C++ fingerprint spoofing, beats most anti-bot when needed |
| HTML parser | `BeautifulSoup` + `lxml` | Fastest Python HTML parser, excellent CSS selector support |
| Database | SQLite | Zero-config, single-file, handles this scale perfectly |
| Async runtime | `asyncio` | Native Python, needed for nodriver and aiohttp integration |
| Data export | `pandas` | DataFrame operations for CSV/Parquet export to ML pipelines |

---

## Sources

**HLTV Scraper Projects (architecture patterns observed):**
- [nmwalsh/HLTV-Scraper](https://github.com/nmwalsh/HLTV-Scraper) -- Multi-threaded, CSV storage, incremental ID tracking
- [akimerslys/hltv-async-api](https://github.com/akimerslys/hltv-async-api) -- Async architecture, adaptive delays, proxy rotation
- [jparedesDS/hltv-scraper](https://github.com/jparedesDS/hltv-scraper) -- Selenium + undetected-chromedriver, player stats extraction
- [gelbling/HLTV.org-Scraper](https://github.com/gelbling/HLTV.org-Scraper) -- Scrapy-based, spider architecture
- [gigobyte/HLTV](https://github.com/gigobyte/HLTV) -- Node.js API, comprehensive URL pattern documentation

**Anti-Detection Research:**
- [ZenRows: Bypass Cloudflare 2026](https://www.zenrows.com/blog/bypass-cloudflare) -- Cloudflare detection methods and bypass strategies
- [BrightData: Web Scraping with Camoufox](https://brightdata.com/blog/web-data/web-scraping-with-camoufox) -- Camoufox capabilities and limitations
- [nodriver on GitHub](https://github.com/ultrafunkamsterdam/nodriver) -- Undetected Chrome automation
- [ScrapingBee: Bypass Cloudflare at Scale](https://www.scrapingbee.com/blog/how-to-bypass-cloudflare-antibot-protection-at-scale/) -- Production-scale anti-detection

**Architecture Patterns:**
- [Browserless: Patterns and Anti-Patterns in Web Scraping](https://www.browserless.io/blog/patterns-and-anti-patterns-in-web-scraping) -- Selector abstraction, maintainability
- [The Web Scraping Club: Adapting to Website Changes](https://substack.thewebscraping.club/p/5-approaches-make-scrapers-more-reliable) -- Adaptive selector patterns
- [GroupBWT: Web Scraping Infrastructure](https://groupbwt.com/blog/infrastructure-of-web-scraping/) -- Pipeline architecture patterns
- [ScrapingBee: Advanced Web Scraping](https://www.scrapingbee.com/blog/advanced-web-scraping/) -- Checkpoint/resume patterns

**Data Storage:**
- [SQLite: Appropriate Uses](https://www.sqlite.org/whentouse.html) -- When SQLite is the right choice
- [DataCamp: SQLite vs PostgreSQL](https://www.datacamp.com/blog/sqlite-vs-postgresql-detailed-comparison) -- Comparison for analytical workloads
