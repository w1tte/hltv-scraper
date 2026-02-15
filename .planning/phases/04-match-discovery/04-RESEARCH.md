# Phase 4: Match Discovery - Research

**Researched:** 2026-02-15
**Domain:** HLTV results page pagination, HTML parsing, SQLite queue persistence
**Confidence:** HIGH

## Summary

Phase 4 builds a discovery pipeline that paginates 100 HLTV results pages (offsets 0-9900), parses each page to extract match entries, and persists them to a `scrape_queue` SQLite table. The existing codebase provides all the building blocks: `HLTVClient.fetch()` for page retrieval, `HtmlStorage` for raw HTML archival, `Database` with migration-based schema management, and the `MatchRepository` pattern for data access.

The results listing page structure is thoroughly documented by the Phase 3 selector map (`results-listing.md`) and verified against 3 HTML samples. Each page returns exactly 100 match entries with consistent CSS selectors. The only structural variation is page 1, which includes 8 duplicate "big-results" entries that lack timestamps -- these are filtered out by selecting only elements with the `data-zonedgrouping-entry-unix` attribute.

One critical finding: **DISC-03 requires team IDs, but team IDs are NOT available on the results listing page.** The listing contains only team names, not links to `/team/{id}/...`. Team IDs must be deferred to Phase 5 (match overview parsing). The CONTEXT.md Decision 3 already accounts for this -- the queue stores only `match_id, url, offset, discovered_at, is_forfeit, status`, not team names/scores/events.

**Primary recommendation:** Build a `ResultsPageParser` that uses BeautifulSoup to extract match entries from a single HTML page, a `DiscoveryRepository` for the `scrape_queue` table, extend `HtmlStorage` with a `results_listing` page type, and create a `DiscoveryRunner` that orchestrates the 100-page pagination loop with resume support.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| beautifulsoup4 | 4.14.3 | HTML parsing/selector queries | Already installed. Used in Phase 3 recon. Reliable CSS selector support via `.select()` / `.select_one()` |
| sqlite3 | stdlib | Queue persistence | Already used by `Database` and `MatchRepository`. No external dependency needed. |
| nodriver | >=0.38 | Page fetching via real Chrome | Already used by `HLTVClient`. Solves Cloudflare challenges. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| gzip | stdlib | HTML compression for storage | Already used by `HtmlStorage`. Results pages are ~6MB raw. |
| re | stdlib | Match ID extraction from URLs | Regex `/matches/(\d+)/` on href attributes |
| datetime | stdlib | Timestamp conversion | Unix ms timestamps to ISO 8601 dates |
| logging | stdlib | Progress/error reporting | Follow existing pattern from `http_client.py` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| BeautifulSoup | lxml.html directly | lxml is installed but BS4 is more readable for CSS selectors. BS4+lxml parser gives speed of lxml with BS4 API. |
| SQLite scrape_queue | JSON file | SQLite already in use, supports UPSERT, crash-safe with WAL mode |

**Installation:**
```bash
pip install beautifulsoup4 lxml
```
Both already installed. Add `beautifulsoup4>=4.12` and `lxml>=5.0` to `pyproject.toml` `[project.dependencies]`.

## Architecture Patterns

### Recommended Project Structure
```
src/scraper/
    config.py              # Add results_url, max_offset constants
    http_client.py         # No changes needed
    storage.py             # Add "results_listing" page type
    db.py                  # No changes needed
    repository.py          # Add DiscoveryRepository class (or extend)
    discovery.py           # NEW: ResultsPageParser + DiscoveryRunner
    exceptions.py          # No changes needed
migrations/
    001_initial_schema.sql # Existing (schema version 1)
    002_scrape_queue.sql   # NEW: scrape_queue + discovery_progress tables
tests/
    test_discovery.py      # NEW: parser + repository + runner tests
```

### Pattern 1: ResultsPageParser (Pure Function, No Side Effects)
**What:** A class/function that takes raw HTML string, returns a list of parsed match entries as dicts.
**When to use:** Every results page HTML needs parsing -- both during live scraping and during offline re-parsing of archived HTML.
**Example:**
```python
# Source: Phase 3 selector map (results-listing.md)
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from bs4 import BeautifulSoup

@dataclass
class DiscoveredMatch:
    match_id: int
    url: str
    is_forfeit: bool
    timestamp_ms: int  # Unix ms from data-zonedgrouping-entry-unix

def parse_results_page(html: str) -> list[DiscoveredMatch]:
    """Parse a results listing page, return discovered matches.

    Uses data-zonedgrouping-entry-unix attribute to select only
    regular entries (automatically skips big-results on page 1).
    """
    soup = BeautifulSoup(html, "lxml")
    entries = soup.select(".result-con[data-zonedgrouping-entry-unix]")

    matches = []
    for entry in entries:
        link = entry.select_one("a.a-reset")
        href = link["href"]
        match_id_match = re.search(r"/matches/(\d+)/", href)
        match_id = int(match_id_match.group(1))

        map_text = entry.select_one(".map-text").text.strip()
        is_forfeit = map_text == "def"

        timestamp_ms = int(entry["data-zonedgrouping-entry-unix"])

        matches.append(DiscoveredMatch(
            match_id=match_id,
            url=href,
            is_forfeit=is_forfeit,
            timestamp_ms=timestamp_ms,
        ))

    return matches
```

### Pattern 2: DiscoveryRepository (UPSERT Queue Rows)
**What:** Repository class following the existing `MatchRepository` pattern -- receives a `sqlite3.Connection`, provides UPSERT methods for the `scrape_queue` table.
**When to use:** Persisting discovered matches and tracking progress.
**Example:**
```python
# Follows existing repository.py pattern
import sqlite3

UPSERT_QUEUE = """
    INSERT INTO scrape_queue (match_id, url, offset, discovered_at, is_forfeit, status)
    VALUES (:match_id, :url, :offset, :discovered_at, :is_forfeit, 'pending')
    ON CONFLICT(match_id) DO UPDATE SET
        url           = excluded.url,
        offset        = excluded.offset,
        discovered_at = excluded.discovered_at,
        is_forfeit    = excluded.is_forfeit
"""
# Note: status is NOT updated on re-discovery -- already-scraped matches keep their status

class DiscoveryRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_discovered(self, data: dict) -> None:
        with self.conn:
            self.conn.execute(UPSERT_QUEUE, data)

    def upsert_batch(self, batch: list[dict]) -> None:
        """Atomically upsert a page of discovered matches."""
        with self.conn:
            for row in batch:
                self.conn.execute(UPSERT_QUEUE, row)

    def mark_offset_complete(self, offset: int) -> None:
        """Record that an offset page has been successfully processed."""
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO discovery_progress (offset, completed_at) "
                "VALUES (?, datetime('now'))",
                (offset,),
            )

    def get_completed_offsets(self) -> set[int]:
        """Return all offsets that have been successfully processed."""
        rows = self.conn.execute(
            "SELECT offset FROM discovery_progress"
        ).fetchall()
        return {r[0] for r in rows}

    def count_pending(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM scrape_queue WHERE status = 'pending'"
        ).fetchone()[0]

    def count_total(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM scrape_queue"
        ).fetchone()[0]
```

### Pattern 3: DiscoveryRunner (Orchestration Loop)
**What:** Async function that drives the pagination loop: fetch page, parse, persist batch, save HTML, mark offset complete.
**When to use:** The main entry point for running discovery.
**Example:**
```python
async def run_discovery(
    client: HLTVClient,
    repo: DiscoveryRepository,
    html_storage: HtmlStorage,
    config: ScraperConfig,
) -> dict:
    """Paginate results pages and populate scrape_queue.

    Resumes from last completed offset on restart.
    """
    completed = repo.get_completed_offsets()
    stats = {"pages_fetched": 0, "matches_found": 0, "pages_skipped": 0}

    for offset in range(0, config.max_offset + 1, 100):
        if offset in completed:
            stats["pages_skipped"] += 1
            continue

        url = f"{config.base_url}/results?offset={offset}"
        html = await client.fetch(url)

        # Archive raw HTML
        html_storage.save_results_page(html, offset=offset)

        # Parse and persist
        matches = parse_results_page(html)
        batch = [
            {
                "match_id": m.match_id,
                "url": m.url,
                "offset": offset,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "is_forfeit": m.is_forfeit,
            }
            for m in matches
        ]
        repo.upsert_batch(batch)
        repo.mark_offset_complete(offset)

        stats["pages_fetched"] += 1
        stats["matches_found"] += len(matches)
        logger.info(
            "Offset %d: %d matches (total: %d)",
            offset, len(matches), stats["matches_found"],
        )

    return stats
```

### Anti-Patterns to Avoid
- **Filtering on team names or scores during discovery:** Decision 2 says collect everything. No filtering.
- **Storing team names/scores/event in scrape_queue:** Decision 3 explicitly says NOT to store these. They come from Phase 5.
- **Using `.results-all` indexing to skip big-results:** Fragile. Use `[data-zonedgrouping-entry-unix]` attribute selector instead -- it naturally excludes big-results entries on page 1 and works identically on all pages.
- **Date-based CS2 boundary detection:** Decision 1 says fixed offset limit (0-9900), no date logic.
- **Inserting into the `matches` table:** Decision 3 says use `scrape_queue` table, not `matches`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML parsing | Regex on raw HTML | BeautifulSoup with lxml parser | HTML is messy, class ordering varies, whitespace differs |
| Crash recovery | Custom state file | SQLite `discovery_progress` table + WAL mode | Atomic commits, survives power loss, queryable |
| Retry on fetch failure | Custom retry loop | Existing `HLTVClient.fetch()` has tenacity retry | Already handles Cloudflare challenges with exponential backoff |
| Rate limiting | Sleep between pages | Existing `RateLimiter` in `HLTVClient` | Already implements jittered delays with adaptive backoff |
| gzip compression | Manual file I/O | Extend existing `HtmlStorage` class | Consistent storage layer, same patterns |
| Database migrations | Manual CREATE TABLE | Add `002_scrape_queue.sql` migration file | Existing `Database.apply_migrations()` handles versioning |

**Key insight:** Phase 4 primarily wires together existing components (client, storage, database) with new parsing logic. The only genuinely new code is the HTML parser and the pagination orchestrator.

## Common Pitfalls

### Pitfall 1: Double-Counting Big-Results Entries on Page 1
**What goes wrong:** Page 1 contains 108 `.result-con` elements (8 big-results + 100 regular). Selecting all `.result-con` causes 8 duplicate match IDs.
**Why it happens:** The big-results section duplicates entries from the regular listing.
**How to avoid:** Select `.result-con[data-zonedgrouping-entry-unix]` instead of plain `.result-con`. Big-results entries lack this attribute, so they are automatically excluded. This works on ALL pages (100 entries on every page, including page 1).
**Warning signs:** Getting 108 matches from page 1 instead of 100.

### Pitfall 2: UPSERT Clobbering Scraped Status on Re-Run
**What goes wrong:** Re-running discovery resets `status` from 'scraped' back to 'pending' for already-processed matches.
**Why it happens:** The UPSERT updates all fields including status.
**How to avoid:** The ON CONFLICT DO UPDATE clause must NOT update `status`. Only update `url`, `offset`, `discovered_at`, `is_forfeit`.
**Warning signs:** After re-running discovery, `count_pending()` returns the total count instead of only new matches.

### Pitfall 3: Results Page HTML Too Short (Cloudflare Interstitial)
**What goes wrong:** `HLTVClient.fetch()` returns challenge page HTML instead of results page. Parser finds 0 entries.
**Why it happens:** Cloudflare sometimes serves an interstitial even after the title check passes.
**How to avoid:** After parsing, validate that the page returned a reasonable number of entries (expect exactly 100, except possibly the very last page). If 0 entries are found, raise an error and retry.
**Warning signs:** Pages with 0 entries or pages significantly shorter than expected (~6MB for a results page).

### Pitfall 4: Not Committing Per-Page (Large Transaction)
**What goes wrong:** Wrapping all 100 pages in a single transaction. If the process crashes on page 50, all work is lost.
**Why it happens:** Premature optimization or forgetting to commit after each page.
**How to avoid:** Commit after each page: batch-upsert the 100 matches AND mark the offset complete in a single transaction. Use `discovery_progress` table for resume.
**Warning signs:** `discovery_progress` table is empty even after processing pages.

### Pitfall 5: HtmlStorage Path Collision with Match-Based Storage
**What goes wrong:** Results listing pages don't have match IDs. Using the existing `HtmlStorage.save(match_id=...)` API doesn't make sense.
**Why it happens:** `HtmlStorage` was designed for per-match pages, not listing pages.
**How to avoid:** Add a separate method like `save_results_page(html, offset)` that stores to `data/raw/results/offset-{offset}.html.gz` instead of the `matches/{id}/` hierarchy. Or add a new page type with offset-based naming.
**Warning signs:** Trying to call `storage.save(html, match_id=???, page_type="results_listing")`.

### Pitfall 6: Timestamp Precision Loss
**What goes wrong:** Storing timestamps as seconds instead of milliseconds, or as floats that lose precision.
**Why it happens:** The `data-zonedgrouping-entry-unix` attribute is in milliseconds (13 digits).
**How to avoid:** Store as integer milliseconds in the queue, or convert to ISO 8601 string with `datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()`.
**Warning signs:** Dates are off by a factor of 1000, or fractional seconds are truncated.

## Code Examples

### Parsing a Single Results Page (Complete)
```python
# Source: Phase 3 selector map + verified against 3 HTML samples
import re
from dataclasses import dataclass
from bs4 import BeautifulSoup

@dataclass
class DiscoveredMatch:
    match_id: int
    url: str           # Relative URL: /matches/2389953/furia-vs-b8-...
    is_forfeit: bool   # True when map-text == "def"
    timestamp_ms: int  # Unix milliseconds

def parse_results_page(html: str) -> list[DiscoveredMatch]:
    soup = BeautifulSoup(html, "lxml")

    # Select only entries with timestamp attribute.
    # This automatically skips big-results on page 1 (they lack this attr).
    entries = soup.select(".result-con[data-zonedgrouping-entry-unix]")

    results = []
    for entry in entries:
        # Match URL and ID
        link = entry.select_one("a.a-reset")
        href = link["href"]  # e.g., /matches/2389953/furia-vs-b8-...
        m = re.search(r"/matches/(\d+)/", href)
        if not m:
            continue  # Skip malformed entries
        match_id = int(m.group(1))

        # Forfeit flag
        map_text = entry.select_one(".map-text").text.strip()
        is_forfeit = (map_text == "def")

        # Timestamp
        timestamp_ms = int(entry["data-zonedgrouping-entry-unix"])

        results.append(DiscoveredMatch(
            match_id=match_id,
            url=href,
            is_forfeit=is_forfeit,
            timestamp_ms=timestamp_ms,
        ))

    return results
```

### Migration SQL for scrape_queue
```sql
-- migrations/002_scrape_queue.sql
-- Phase 4: Match Discovery - scrape queue and progress tracking

CREATE TABLE IF NOT EXISTS scrape_queue (
    match_id      INTEGER PRIMARY KEY,
    url           TEXT NOT NULL,          -- Relative match URL
    offset        INTEGER NOT NULL,       -- Which results page (0, 100, 200, ...)
    discovered_at TEXT NOT NULL,          -- ISO 8601 timestamp
    is_forfeit    INTEGER NOT NULL DEFAULT 0,  -- 1 if map-text was "def"
    status        TEXT NOT NULL DEFAULT 'pending'  -- pending | scraped | failed
);

CREATE TABLE IF NOT EXISTS discovery_progress (
    offset       INTEGER PRIMARY KEY,    -- Results page offset (0, 100, 200, ...)
    completed_at TEXT NOT NULL           -- When this page was fully processed
);

CREATE INDEX IF NOT EXISTS idx_scrape_queue_status ON scrape_queue(status);
CREATE INDEX IF NOT EXISTS idx_scrape_queue_offset ON scrape_queue(offset);
```

### HtmlStorage Extension for Results Pages
```python
# Add to storage.py -- results pages use offset-based paths, not match-based
class HtmlStorage:
    # ... existing code ...

    def save_results_page(self, html: str, offset: int) -> Path:
        """Save a results listing page HTML to disk."""
        file_path = self.base_dir / "results" / f"offset-{offset}.html.gz"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(gzip.compress(html.encode("utf-8")))
        return file_path

    def load_results_page(self, offset: int) -> str:
        """Load a results listing page HTML from disk."""
        file_path = self.base_dir / "results" / f"offset-{offset}.html.gz"
        if not file_path.exists():
            raise FileNotFoundError(f"No saved results page for offset {offset}")
        return gzip.decompress(file_path.read_bytes()).decode("utf-8")

    def results_page_exists(self, offset: int) -> bool:
        """Check whether a results listing page has been saved."""
        return (self.base_dir / "results" / f"offset-{offset}.html.gz").exists()
```

### Config Extension
```python
# Add to ScraperConfig dataclass
    # Discovery pagination
    max_offset: int = 9900           # Last offset to paginate to (inclusive)
    results_per_page: int = 100      # Entries per results page (HLTV constant)
```

### Resume Logic
```python
# In the discovery runner
completed = repo.get_completed_offsets()

for offset in range(0, config.max_offset + 1, 100):
    if offset in completed:
        logger.debug("Skipping offset %d (already complete)", offset)
        continue

    # ... fetch, parse, persist ...
    repo.mark_offset_complete(offset)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Headless Chrome (`headless=True`) | Off-screen Chrome (`headless=False` + position hack) | Phase 1 discovery | Cloudflare detects headless mode; off-screen window bypasses detection |
| `curl_cffi` for requests | `nodriver` with real Chrome | Phase 1 discovery | HLTV's Turnstile challenges require full JS execution |
| Manual CREATE TABLE | Migration files (`NNN_desc.sql`) | Phase 2 implementation | `Database.apply_migrations()` tracks schema version via `PRAGMA user_version` |

**Deprecated/outdated:**
- Nothing deprecated within this project's stack. All dependencies are current.

## Critical Requirement Discrepancy

**DISC-03 states:** "Scraper extracts match ID, team names, **team IDs (from hyperlinks)**, scores, event name, star rating, and date from results listing"

**Reality (verified against 3 HTML samples with HIGH confidence):** The results listing page does NOT contain team hyperlinks. There are no `/team/{id}/...` links anywhere in a `.result-con` entry. Team IDs are only available on the match overview page (Phase 5).

**Available on results listing:**
- match_id (from match URL href)
- team names (from `.team1 .team` and `.team2 .team` text)
- scores (from `.result-score span` elements)
- event name (from `.event-name` text)
- star rating (count of `.stars i` elements)
- date/timestamp (from `data-zonedgrouping-entry-unix` attribute)
- format/map (from `.map-text`)
- forfeit flag (from `.map-text` == "def")

**NOT available on results listing:**
- team IDs (no team links)
- event ID (no event link with ID)
- LAN/online indicator
- Player information

**Recommendation:** Decision 3 in CONTEXT.md already handles this correctly -- the `scrape_queue` table stores only `match_id, url, offset, discovered_at, is_forfeit, status`. Team IDs, scores, event details etc. will be extracted in Phase 5 from the match overview page and stored in the `matches` table. DISC-03's mention of "team IDs from hyperlinks" on the results listing is factually impossible and should be noted as a requirement to fulfill across Phases 4+5, not Phase 4 alone.

## Open Questions

1. **Should beautifulsoup4 and lxml be added to pyproject.toml dependencies?**
   - What we know: Both are installed system-wide but not listed in project dependencies
   - What's unclear: Whether they were intentionally omitted (dev-only) or overlooked
   - Recommendation: Add them to `[project.dependencies]` since parsing is core functionality

2. **Transaction boundary for per-page persistence**
   - What we know: Each page produces ~100 UPSERT rows + 1 progress row. These should be atomic.
   - What's unclear: Whether `with self.conn:` (auto-commit) wrapping the batch is sufficient, or whether explicit `BEGIN`/`COMMIT` is needed for the combined batch+progress operation
   - Recommendation: Use a single `with self.conn:` block that does both the batch upserts AND the progress insert -- SQLite's `with conn:` provides automatic transaction management

3. **Entry count validation threshold**
   - What we know: Every observed page has exactly 100 entries. The last page of all HLTV results might have fewer.
   - What's unclear: Whether offset 9900 (our fixed limit) will always have exactly 100 entries, or could have fewer
   - Recommendation: Warn (don't fail) if entry count != 100. Log the count for debugging. Only fail on 0 entries (likely Cloudflare issue).

## Sources

### Primary (HIGH confidence)
- Phase 3 selector map: `.planning/phases/03-page-reconnaissance/recon/results-listing.md` - Complete CSS selector reference verified against 3 HTML samples
- HTML samples: `data/recon/results-offset-0.html.gz`, `results-offset-100.html.gz`, `results-offset-5000.html.gz` - Verified all selectors programmatically
- Existing codebase: `src/scraper/http_client.py`, `storage.py`, `db.py`, `repository.py`, `config.py` - Read in full
- Migration: `migrations/001_initial_schema.sql` - Verified schema version tracking pattern

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions (6 locked decisions from `/gsd:discuss-phase`) - Constrains architecture

### Tertiary (LOW confidence)
- None. All findings verified against source code and HTML samples.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already installed and used in prior phases
- Architecture: HIGH - Follows established patterns from existing codebase (repository, storage, migrations)
- Pitfalls: HIGH - Verified against real HTML samples; big-results duplication and team ID absence confirmed programmatically
- Selectors: HIGH - Verified against 3 HTML samples with BeautifulSoup

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (HLTV page structure changes infrequently; selector map was built 2026-02-15)
