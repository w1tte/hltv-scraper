# Phase 4: Match Discovery — Context

**Created:** 2026-02-15
**Phase goal:** Paginate HLTV results pages to collect match URLs into a scrape queue

---

## Decision 1: Discovery Scope (Fixed Offset Limit)

**Decision:** Scrape offsets 0 through 9900 (100 pages × 100 matches = 10,000 matches).

**Rationale:** No date-based CS2 boundary. MR12 vs MR15 (CS:GO vs CS2) distinction is not visible on the results listing page. Over-collect now; classification deferred to later phases when round data is available.

**Implications:**
- Pagination loop: `offset = 0, 100, 200, ... 9900`
- No need to parse match dates for boundary detection
- No need for a configurable cutoff date
- Fixed 100-page limit — simple loop with offset tracking

## Decision 2: Match Inclusion (Collect Everything)

**Decision:** Every match on every page is collected. No filtering by star rating, format, or type.

- **Forfeits** (map-text = "def"): Persist with a forfeit flag. Later phases skip them.
- **BO1s**: Treated identically to BO3/BO5 — no special handling.
- **0-star matches**: Included — no minimum tier filter.
- **Duplicates on re-run**: UPSERT (overwrite existing row with fresh data).

**Implications:**
- Parser extracts every `.result-con` entry without conditionals
- Forfeit flag must be derivable from listing data (map-text = "def")
- UPSERT requires match_id as conflict target

## Decision 3: Storage — Queue-Based Architecture

**Decision:** Discovered matches go into a **scrape queue** (not the existing `matches` table). The queue tracks scraping progress.

**Queue row fields:**
- `match_id` (integer, primary key)
- `url` (match page URL)
- `offset` (which results page it was found on)
- `discovered_at` (timestamp of discovery)
- `is_forfeit` (boolean flag from map-text = "def")
- Status tracking (pending → scraped) — implementation left to Claude

**Flow:**
1. Discovery (Phase 4): Insert rows with status=pending
2. Scraping (Phase 5+): Process pending rows, update status to scraped
3. Re-runs: UPSERT on match_id — overwrites existing rows

**NOT stored during discovery:** team names, scores, event, stars, format. These come from Phase 5 match overview parsing into the `matches` table.

## Decision 4: Raw HTML Archival

**Decision:** Save raw HTML for all 100 results listing pages.

**Storage pattern:** Follow existing `data/recon/` convention (or similar). One file per offset page.

**Rationale:** Enables offline re-parsing if selectors change or if additional listing-level data is needed later.

## Decision 5: Resume Support (Offset Tracking)

**Decision:** Track the last successfully processed offset so the scraper can resume mid-run.

**Mechanism:** Persist last completed offset. On restart, skip offsets already processed.

**Rationale:** 100 pages with rate limiting could take 10-20+ minutes. Crash recovery avoids re-fetching completed pages.

## Decision 6: Re-run Strategy

**Decision:** Always paginate from offset 0 (newest first) on every run.

**Rationale:** Catches new matches added since last run. Simple — no need for incremental logic in Phase 4. Phase 9 may add smarter incremental mode later.

---

## Deferred Items

- **MR12/MR15 classification:** Deferred to Phase 5/6 when round data is visible on match detail and map stats pages
- **Incremental discovery mode:** Deferred to Phase 9 (Pipeline Orchestration)
- **Star-based prioritization:** Not needed — all matches treated equally

---

## Key Constraints (from Phase 3 Recon)

These are locked findings from the results listing selector map:

- 100 entries per page, offset increments of 100
- Page 1 has a `big-results` section — **skip it**, use last `.results-all` container
- Match URL: `a.a-reset[href]` → parse match_id with regex `/matches/(\d+)/`
- Forfeit detection: `.map-text` text = "def"
- Pagination next: `.pagination-next` — has class `inactive` on last page
- Timestamps: `data-zonedgrouping-entry-unix` attribute (milliseconds)
