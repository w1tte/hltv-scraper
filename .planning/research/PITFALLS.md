# Domain Pitfalls

**Domain:** Web scraping HLTV.org for CS2 match/player/team statistics
**Researched:** 2026-02-14
**Overall confidence:** MEDIUM-HIGH (based on analysis of multiple existing HLTV scraper projects, Cloudflare documentation, and community reports)

---

## Critical Pitfalls

Mistakes that cause complete scraper failure, IP bans, data corruption, or project rewrites.

---

### Pitfall 1: Cloudflare IP Ban Spiral

**What goes wrong:** The scraper sends requests too quickly or in detectable patterns. Cloudflare flags the IP, returns 403 Forbidden responses, and eventually places the IP on a long-term ban list. Once banned, all subsequent requests fail. Developers then switch IPs manually, get banned again, and enter a spiral of diminishing access.

**Why it happens:** HLTV uses Cloudflare Bot Management, which employs multi-layered detection: TLS/JA3/JA4 fingerprinting, JavaScript challenges, behavioral analysis, and IP reputation scoring. Even modest request rates (e.g., 1 request/second sustained) can trigger detection if the fingerprint or behavior pattern looks automated. Cloudflare's v8 ML model classifies 17 million residential proxy IPs every hour -- it is extremely aggressive.

**Consequences:** Complete loss of access from that IP. If using a shared hosting provider or VPN, the entire subnet may be flagged. Historical scraping progress is lost if there is no checkpoint/resume mechanism.

**Warning signs:**
- Intermittent 403 responses appearing after initial success
- Increasing frequency of Cloudflare challenge pages (HTTP 503 with JS challenge)
- Responses returning HTML that contains Cloudflare "checking your browser" content instead of match data
- Sudden switch from working to 100% failure rate

**Prevention:**
1. Implement aggressive rate limiting from day one: minimum 3-5 seconds between requests, with random jitter (e.g., 3-8 seconds uniform random)
2. Use residential rotating proxies, not datacenter proxies. Datacenter IPs start with low trust scores and get flagged almost immediately by Cloudflare
3. Implement exponential backoff on any non-200 response: double the delay after each failure, cap at 5 minutes
4. Track per-IP request counts and rotate proxies proactively (every 20-50 requests), not just reactively after a ban
5. Consider using a stealth browser automation tool (SeleniumBase UC Mode, Nodriver, or Patchright) rather than raw HTTP requests, as Cloudflare inspects TLS fingerprints and blocks non-browser clients like Python `requests` or `httpx` on sight

**Phase mapping:** Must be addressed in Phase 1 (core scraping infrastructure). Building the scraper without anti-detection from the start means rewriting the entire request layer later.

**Confidence:** HIGH -- documented across multiple HLTV scraper projects (gigobyte/HLTV issue #43, hltv-async-api README) and consistent with Cloudflare's published bot management documentation.

---

### Pitfall 2: TLS Fingerprint Detection (The "Hidden" Block)

**What goes wrong:** The scraper uses Python's `requests` library (or `httpx`, `aiohttp`) to make HTTP requests. Cloudflare identifies these by their TLS handshake fingerprint (JA3/JA4 hash) and blocks them silently or serves challenge pages, even with perfect headers and cookies. The developer thinks the issue is rate limiting or headers, when it is actually the TLS layer.

**Why it happens:** Every HTTP client has a unique TLS handshake signature. Python's `requests` library uses urllib3 which produces a JA3 hash that Cloudflare has in its known-bot database. No amount of header manipulation can fix a TLS-level fingerprint mismatch. This is the number one reason "I set User-Agent and it still doesn't work" posts exist.

**Consequences:** Scraper appears to work in development (maybe Cloudflare hasn't flagged your home IP yet), then fails completely in production or at scale. Developers waste days debugging headers and cookies when the problem is at the transport layer.

**Warning signs:**
- Requests work from a browser but fail from Python with identical headers
- 403 or challenge responses even with a single request (not rate-limited)
- Different behavior between local development and server deployment
- `curl` works but Python does not (curl has a different JA3 hash)

**Prevention:**
1. Use a real browser engine (Playwright, Selenium, or Nodriver) that produces authentic browser TLS fingerprints
2. If you must use HTTP libraries, use `curl_cffi` (Python) which impersonates real browser TLS fingerprints
3. Test your JA3/JA4 fingerprint against known databases before building the full scraper
4. Nodriver (successor to undetected-chromedriver) communicates with Chrome directly without WebDriver, avoiding the `navigator.webdriver=true` detection vector entirely

**Phase mapping:** Phase 1 -- must choose the right HTTP client/browser engine from the start. Switching from `requests` to Playwright later requires rewriting all request and parsing logic.

**Confidence:** HIGH -- Cloudflare's JA3/JA4 fingerprint documentation is public, and the `puppeteer-extra-stealth` project was deprecated in February 2026 specifically because Cloudflare's detection outpaced its evasions.

---

### Pitfall 3: Silent Data Loss from Partial Scrapes

**What goes wrong:** The scraper successfully fetches a match page but fails to extract all data -- missing one map's stats, skipping a player, or dropping overtime rounds. Because no validation exists, incomplete records get written to the database. Downstream ML models train on corrupted data, producing unreliable predictions. The corruption is only discovered much later (if ever).

**Why it happens:** HLTV match pages have variable structure depending on match format:
- Best-of-1 vs Best-of-3 vs Best-of-5 produce different numbers of map stat tables
- Overtime rounds produce additional data that may or may not appear in the same format
- Forfeited/walkover matches have no stats at all
- Matches with stand-in/substitute players may have different player counts or missing player profile links
- Older matches (pre-CS2 transition) may have different HTML structure entirely
- Multi-map matches return multidimensional arrays that need flattening -- if the flattening logic is wrong, data silently collapses

**Consequences:** Database contains records that look complete but are missing fields or have incorrect values. ML models trained on this data produce subtly wrong results. Fixing requires re-scraping thousands of pages, which risks more IP bans.

**Warning signs:**
- Player count per team is not exactly 5 on some records
- Map count does not match the best-of-N format
- Round counts do not add up (e.g., BO1 map with 10 rounds total)
- Stats like ADR or KAST are 0 or null when they should have values
- Identical stats for different maps in the same match (copy artifact)

**Prevention:**
1. Define a strict schema for each data type (match, map, player-map-stats) with required fields
2. Validate every scraped record against the schema BEFORE writing to database
3. Implement match format detection first: determine BO1/BO3/BO5 from the page, then validate that the correct number of map stats were extracted
4. Create explicit handling for edge cases: forfeits (skip), stand-ins (flag), overtime (extended parsing)
5. Log validation failures with the match URL so they can be investigated and re-scraped
6. Build a "completeness audit" query that checks record counts and flags suspicious patterns

**Phase mapping:** Phase 2 (data parsing and validation). The schema and validation layer should be built immediately after basic page fetching works, before any bulk scraping begins.

**Confidence:** HIGH -- multiple HLTV scraper projects (nmwalsh/HLTV-Scraper, gelbling/HLTV.org-Scraper) document multi-map array flattening bugs, and the Kaggle HLTV dataset shows evidence of incomplete records.

---

### Pitfall 4: Building Without Checkpoint/Resume Capability

**What goes wrong:** The scraper starts a bulk run of 10,000+ match pages. At match 4,237, it crashes (network error, IP ban, OOM, power loss). There is no record of which matches were already scraped successfully. The developer must either restart from the beginning (re-scraping 4,237 pages, wasting time and risking more bans) or guess where to resume (risking gaps).

**Why it happens:** Developers build the "happy path" first -- iterate over match IDs, scrape each one, write to output. Checkpointing is seen as an optimization to add later. But for a scraper that takes hours to run and is constantly at risk of being blocked, it is core infrastructure.

**Consequences:** Wasted proxy bandwidth (which costs money with residential proxies). Duplicate records if some matches get scraped twice. Gaps in data if the resume point is estimated incorrectly. Developer frustration leading to shortcuts that introduce more bugs.

**Warning signs:**
- No file or database tracking which match IDs have been scraped
- Scraper restarts always begin from match ID 1 or page 1
- No progress logging beyond console output
- Bulk runs take more than 30 minutes with no intermediate saves

**Prevention:**
1. Before scraping, generate the full list of target match IDs (from HLTV's results pages)
2. Store scraped match IDs in a persistent set (database table or file). Check membership before each scrape
3. Write data to database/file after EACH successful match, not in batch at the end
4. Log progress: "Scraped 4237/10000, 42% complete, ~3h remaining"
5. On restart, diff the target list against already-scraped IDs to produce the remaining work queue
6. The hltv-async-api library demonstrates this pattern with its `is_parsed()` method and configuration tracking

**Phase mapping:** Phase 1 -- must be built into the scraping loop from the start, not bolted on after the first failed bulk run.

**Confidence:** HIGH -- standard web scraping best practice, and multiple HLTV scraper projects (nmwalsh/HLTV-Scraper) explicitly implement match ID tracking for this reason.

---

## Moderate Pitfalls

Mistakes that cause significant delays, technical debt, or reduced data quality.

---

### Pitfall 5: Hardcoded CSS Selectors That Break on Site Updates

**What goes wrong:** The scraper uses brittle CSS selectors like `div.stats-content > table:nth-child(3) > tbody > tr:nth-child(2) > td:nth-child(4)`. HLTV updates their frontend (class name change, layout restructure, new feature added), and every selector breaks simultaneously. The scraper produces empty/wrong data or crashes.

**Why it happens:** CSS selectors are the fastest way to extract data, so developers reach for them first. But HLTV's frontend is actively maintained -- class names change, new sections are added, layouts shift. Selectors based on positional indexing (nth-child) are especially fragile because any added/removed element shifts all indices.

**Consequences:** Scraper stops working entirely after a site update, requiring manual inspection and selector updates. If updates are not detected quickly (e.g., running on a schedule), days of bad data may accumulate.

**Prevention:**
1. Prefer semantic selectors over positional ones: `.player-nick` over `td:nth-child(2)`
2. Use data attributes when available: `[data-stat-id="kills"]` is more stable than class names
3. Build a selector test suite: a set of known match pages with expected output, run as CI tests
4. Implement "canary" checks: before each bulk run, scrape 2-3 known matches and validate output against stored expected values
5. Layer selectors with fallbacks: try primary selector, if it returns empty try alternative selector, if both fail raise an alert
6. Consider using an adaptive scraping approach (e.g., Scrapling library) that can handle minor structural changes

**Phase mapping:** Phase 2 (parsing layer). Design the selector strategy before writing hundreds of selectors. Building a selector test suite is Phase 3 (hardening) work.

**Confidence:** MEDIUM -- general web scraping best practice; no specific HLTV site update breaking scrapers was documented, but HLTV is actively developed and this is a matter of when, not if.

---

### Pitfall 6: Treating All Matches as Structurally Identical

**What goes wrong:** The scraper is built against a "typical" BO3 match between two tier-1 teams. It works perfectly for that case. Then it encounters:
- A BO1 showmatch with no detailed stats page
- A BO5 grand final with 5 maps of data
- A forfeit/default win with no maps played
- A match where a player disconnected and was replaced mid-match
- An older match from 2019 with CSGO-era HTML structure
- A match with overtime rounds (16-14 becomes 19-17)

Each of these has different HTML structure, different data availability, and different edge cases.

**Why it happens:** Match page structure on HLTV is not uniform. The data presented varies by: match format (BO1/3/5), match status (completed/live/upcoming/cancelled/forfeited), era (CSGO vs CS2), tournament tier (major vs minor), and whether detailed stats were recorded.

**Consequences:** Crashes on unexpected formats. Wrong data extracted silently (e.g., treating a BO1's single map as map 1 of a BO3). Database schema that cannot accommodate format variations.

**Prevention:**
1. Before parsing any match data, detect and classify the match type: format (BO1/3/5), status (completed/forfeited/cancelled), era, stat availability
2. Build separate parsing paths for each match type, sharing common utility functions
3. Build a test suite with one example of each match type -- capture the HTML and parse offline
4. Design the database schema to handle variable map counts: use a separate `map_stats` table linked to the match, not fixed `map1_score`, `map2_score` columns
5. Treat forfeits and cancellations as first-class data types, not errors to swallow

**Phase mapping:** Phase 2 (parsing layer). Auditing HLTV match page variants should happen before writing the parser, not after it breaks.

**Confidence:** HIGH -- the nmwalsh/HLTV-Scraper project documents the multi-map array flattening issue explicitly, and the Rust HLTV library acknowledges that match pages have "many different conditions and edge cases."

---

### Pitfall 7: Using Datacenter Proxies Instead of Residential Proxies

**What goes wrong:** The developer buys cheap datacenter proxies ($5-20/month) and configures the scraper to rotate through them. Cloudflare identifies datacenter IP ranges instantly (they maintain databases of datacenter ASN blocks) and blocks them. The proxies are useless.

**Why it happens:** Datacenter proxies are 5-10x cheaper than residential proxies. Developers assume "a proxy is a proxy" and optimize for cost. But Cloudflare's IP reputation system assigns low trust scores to datacenter IPs by default, and its ML model specifically trains on datacenter traffic patterns.

**Consequences:** Money wasted on proxies that don't work. Scraper appears broken even though the code is correct. Developer blames code when the problem is infrastructure.

**Warning signs:**
- Proxies work on non-Cloudflare sites but fail on HLTV
- 403 responses on the very first request through a new proxy
- Proxy provider advertises "works on all sites" without Cloudflare-specific claims

**Prevention:**
1. Budget for residential rotating proxies from the start. Expect $50-200/month for the volume needed (thousands of pages)
2. Evaluate proxy providers specifically on their Cloudflare bypass track record
3. Test a small proxy pool against HLTV before buying in bulk
4. Consider scraping API services (ScrapingBee, Scrapfly, ScraperAPI) that handle proxy rotation and Cloudflare bypass as a managed service -- often more cost-effective than self-managed residential proxies
5. If budget is very limited, consider Nodriver/SeleniumBase UC Mode from your own residential IP with very conservative rate limiting (but this limits throughput severely)

**Phase mapping:** Phase 1 (infrastructure). Proxy strategy must be decided before any bulk scraping. Switching proxy types later is easy technically but expensive in lost time and money.

**Confidence:** HIGH -- Cloudflare documentation explicitly describes datacenter IP detection, and proxy comparison guides consistently rank residential proxies as necessary for Cloudflare-protected sites.

---

### Pitfall 8: No Deduplication Strategy for Incremental Scraping

**What goes wrong:** The scraper runs daily to pick up new matches. Without proper deduplication, the same match gets scraped and inserted multiple times. Or worse, a match that was scraped while still live (partial data) gets scraped again when complete, but the old partial record is not updated -- now the database has two conflicting records for the same match.

**Why it happens:** Deduplication seems simple ("just check the match ID") but HLTV match IDs are embedded in URLs, and the same match can appear on multiple listing pages. Additionally, a match page may be scraped during a live match (with incomplete data) and again after completion. The "same" match at different points in time has different data.

**Consequences:** Duplicate records inflate dataset size. Contradictory records for the same match confuse ML models. Aggregation queries produce wrong results (double-counting).

**Prevention:**
1. Use HLTV match ID as the unique key in the database with a UNIQUE constraint
2. Implement UPSERT logic: if a match already exists, update it (overwriting partial data with complete data) rather than inserting a duplicate
3. Track match status: mark records as "partial" when scraped during live matches, "complete" when scraped after completion
4. Run a periodic completeness sweep: re-scrape matches marked "partial" that should now be complete
5. Add a `last_scraped_at` timestamp to every record

**Phase mapping:** Phase 2-3 (data storage and incremental scraping). The unique constraint should be in place from the first database migration. UPSERT logic should be built before incremental scraping is enabled.

**Confidence:** MEDIUM -- standard data engineering practice, not HLTV-specific, but particularly important for sports data where matches transition from upcoming to live to completed.

---

## Minor Pitfalls

Mistakes that cause annoyance, minor data issues, or wasted development time.

---

### Pitfall 9: Timezone Handling for Match Dates

**What goes wrong:** HLTV displays match times in the viewer's local timezone (via JavaScript). When scraped, the raw HTML may contain UTC timestamps, JavaScript-rendered local times, or relative times ("2 hours ago"). The scraper stores these inconsistently, leading to matches appearing to happen at wrong times or on wrong dates.

**Why it happens:** Timezone handling is always harder than expected. HLTV's frontend renders times client-side, so the "time" visible in a browser differs from what is in the raw HTML. If using a headless browser, the timezone depends on the browser's locale settings, which defaults to the server's timezone.

**Prevention:**
1. Always extract and store timestamps in UTC
2. If using a headless browser, set the timezone explicitly to UTC
3. Prefer parsing Unix timestamps from the HTML source (HLTV often includes these as data attributes) over parsing rendered date strings
4. Validate: a match date should be in the past for completed matches, in the future for upcoming ones
5. The hltv-async-api library includes a `tz` configuration option specifically for this reason

**Phase mapping:** Phase 2 (data parsing). Handle timezone normalization when building the date parser.

**Confidence:** MEDIUM -- the hltv-async-api library's explicit `tz` configuration option confirms this is a real issue.

---

### Pitfall 10: Ignoring HLTV's Pagination and URL Structure

**What goes wrong:** The developer attempts to scrape all matches by incrementing match IDs sequentially (1, 2, 3, ..., N). But HLTV match IDs are not sequential -- there are large gaps, and the maximum ID does not correspond to the total number of matches. The scraper wastes thousands of requests on 404 pages.

**Why it happens:** Developers assume IDs are sequential because that is how simple auto-increment databases work. HLTV's ID scheme has gaps from deleted, cancelled, or draft matches.

**Prevention:**
1. Discover match IDs by scraping HLTV's results listing pages first (`/results` with pagination)
2. Build a match ID index before scraping individual match pages
3. Use HLTV's date-range filters to scope discovery to specific time periods for incremental runs
4. Cache the discovered match ID list to avoid re-crawling listing pages on every run

**Phase mapping:** Phase 1 (URL discovery). The URL strategy must be built before the match page scraper.

**Confidence:** HIGH -- standard pattern used by all successful HLTV scraper projects (nmwalsh, gelbling, jparedesDS all use results page discovery).

---

### Pitfall 11: Team Name and Player Name Inconsistency

**What goes wrong:** The same team or player appears under different names across matches. "Natus Vincere" vs "NAVI" vs "Na'Vi". Player nicknames change. Team org names change. The database treats these as different entities, fragmenting statistics.

**Why it happens:** HLTV uses both short and long team names in different contexts. Teams rebrand. Players change their in-game names. Some scrapers capture the display name, which varies by page section.

**Prevention:**
1. Use HLTV's team ID and player ID (from URLs) as the canonical identifier, not the display name
2. Store the display name but index/join on the numeric ID
3. Build a name normalization table for known aliases if display names must be used for output
4. Strip whitespace, normalize unicode, and lowercase for comparison purposes

**Phase mapping:** Phase 2 (data modeling). Decide on the canonical identifier strategy before building the database schema.

**Confidence:** HIGH -- the gelbling/HLTV.org-Scraper project explicitly documents team name cleanup as a necessary step, noting "team names often contained redundant event information or very odd formatting."

---

### Pitfall 12: Over-Engineering the Anti-Detection Layer

**What goes wrong:** The developer spends weeks building a sophisticated anti-detection system with rotating user agents, random mouse movements, variable viewport sizes, cookie persistence, and session management -- before verifying that a simpler approach works. Or they use an expensive scraping API service when SeleniumBase UC Mode with conservative rate limiting from a residential IP would suffice.

**Why it happens:** Fear of Cloudflare is justified, but it can lead to premature optimization. The actual level of Cloudflare protection on HLTV may be standard-tier, not enterprise-tier. A headless browser with basic stealth and slow request rates may be sufficient.

**Prevention:**
1. Start with the simplest viable approach: Nodriver or SeleniumBase UC Mode with 5-second delays
2. Test against HLTV with 10-20 requests before building more infrastructure
3. Escalate complexity only when simpler approaches demonstrably fail
4. Keep the anti-detection layer modular so the approach can be swapped without rewriting parsing logic
5. Track success rate metrics (% of requests returning valid data) to know when to escalate

**Phase mapping:** Phase 1 (infrastructure). Spend 1-2 days testing simple approaches before committing to complex ones.

**Confidence:** MEDIUM -- this is practical advice based on the principle of starting simple. Some HLTV scrapers report success with basic approaches and conservative rate limiting.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation | Severity |
|-------------|---------------|------------|----------|
| Phase 1: Core scraping engine | TLS fingerprint detection | Use real browser engine (Nodriver/SeleniumBase), never raw `requests` | Critical |
| Phase 1: Core scraping engine | No checkpoint/resume | Build match ID tracking into the scraping loop from day one | Critical |
| Phase 1: Infrastructure | Wrong proxy type | Budget for residential proxies or a scraping API service | Critical |
| Phase 1: URL discovery | Sequential ID assumption | Scrape results listing pages to discover valid match IDs first | Moderate |
| Phase 2: Data parsing | All matches treated identically | Classify match type before parsing; build per-type parsers | Critical |
| Phase 2: Data parsing | Silent data loss | Schema validation on every record before database write | Critical |
| Phase 2: Data parsing | Brittle CSS selectors | Use semantic selectors, build selector test suite | Moderate |
| Phase 2: Data parsing | Timezone errors | Extract Unix timestamps, normalize to UTC | Minor |
| Phase 2: Data modeling | Name inconsistency | Use HLTV numeric IDs as canonical identifiers | Moderate |
| Phase 3: Incremental scraping | Duplicate/conflicting records | UPSERT with match status tracking (partial vs complete) | Moderate |
| Phase 3: Hardening | Cloudflare ban spiral at scale | Rate limiting, proxy rotation, exponential backoff | Critical |
| Phase 3: Hardening | Over-engineering anti-detection | Start simple, escalate only on demonstrated failure | Minor |

---

## HLTV-Specific Data Edge Cases Checklist

Before considering the parser "complete," verify it handles each of these correctly:

- [ ] Best-of-1 match (single map stats)
- [ ] Best-of-3 match (three map stats, potentially only 2 played)
- [ ] Best-of-5 match (up to 5 map stats)
- [ ] Match with overtime (round count exceeds 30)
- [ ] Forfeited/walkover match (no stats available)
- [ ] Cancelled match (page exists but no data)
- [ ] Match with a stand-in player (different lineup than the team's roster)
- [ ] Match from the CSGO era (pre-CS2 transition, potentially different HTML)
- [ ] Match with no detailed stats (lower-tier matches may lack per-player stats)
- [ ] Match with a coach substitution or tactical pause note
- [ ] Map that was replayed (rare, but happens due to technical issues)
- [ ] Match where a player has special characters in their name (unicode)
- [ ] Match where team name contains the event name (formatting artifact)

---

## Legal and Ethical Considerations

**Note:** This section is informational, not legal advice.

- HLTV's robots.txt could not be fetched (Cloudflare returned 403 even for robots.txt), which itself is a signal that the site actively resists automated access
- HLTV's Terms of Service likely prohibit automated scraping (most sites do); violating ToS is generally a civil matter, not criminal, but can result in permanent IP/account bans
- Scraping publicly available match statistics is generally lower-risk than scraping personal data or paywalled content
- Rate-limiting your scraper to be less aggressive than a human browsing reduces both technical and ethical risk
- Consider whether HLTV offers any official data API or data licensing program before committing to scraping

**Recommendation:** Treat HLTV's data respectfully. Slow scraping, no login bypass, no personal data extraction. If HLTV offers a paid data API, evaluate it as an alternative to scraping.

---

## Sources

### HLTV Scraper Projects (direct evidence of pitfalls)
- [hltv-async-api (Python async scraper)](https://github.com/akimerslys/hltv-async-api) - Proxy support, rate limiting, 403 handling
- [gigobyte/HLTV Issue #43: Cloudflare](https://github.com/gigobyte/HLTV/issues/43) - IP bans after 2 hours of scraping
- [nmwalsh/HLTV-Scraper](https://github.com/nmwalsh/HLTV-Scraper) - Match ID tracking, multi-map data flattening
- [gelbling/HLTV.org-Scraper](https://github.com/gelbling/HLTV.org-Scraper) - Team name cleanup, 3000+ matches scraped
- [jparedesDS/hltv-scraper](https://github.com/jparedesDS/hltv-scraper) - undetected-chromedriver workarounds

### Cloudflare Detection (authoritative)
- [Cloudflare JA3/JA4 fingerprint docs](https://developers.cloudflare.com/bots/additional-configurations/ja3-ja4-fingerprint/)
- [Cloudflare Bot Management variables](https://developers.cloudflare.com/bots/reference/bot-management-variables/)
- [Cloudflare JA4 signals intelligence](https://blog.cloudflare.com/ja4-signals/)

### Anti-Detection Tools (current landscape, 2026)
- [SeleniumBase UC Mode / Nodriver as undetected-chromedriver successors](https://www.zenrows.com/blog/undetected-chromedriver-alternatives)
- [Anti-detect framework evolution (Nodriver, Patchright)](https://blog.castle.io/from-puppeteer-stealth-to-nodriver-how-anti-detect-frameworks-evolved-to-evade-bot-detection/)
- [Patchright alternatives ranking](https://roundproxies.com/blog/best-patchright-alternatives/)

### Proxy Strategy
- [Residential vs datacenter proxy comparison](https://roundproxies.com/blog/best-web-scraping-proxies/)
- [Proxy strategy for Cloudflare-protected sites](https://scrapfly.io/blog/posts/introduction-to-proxies-in-web-scraping)

### Data Quality
- [Esports data scraping accuracy concerns (Bayes Esports)](https://igamingfuture.com/bayes-esports-how-data-scraping-misleads-the-esports-industry/)
- [Incremental web scraping architecture](https://stabler.tech/blog/how-to-perform-incremental-web-scraping)
- [Data deduplication in scraped datasets](https://scrapingant.com/blog/data-deduplication-and-canonicalization-in-scraped)
