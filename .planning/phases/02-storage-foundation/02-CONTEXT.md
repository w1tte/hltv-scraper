# Phase 2: Storage Foundation - Context

**Gathered:** 2026-02-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Persistent storage layer for all scraped data. SQLite database for structured records (matches, maps, player stats, round history, economy). Filesystem storage for raw HTML archival organized by match. Parsing phases (4-7) consume this layer -- this phase builds the storage API, not the parsers.

</domain>

<decisions>
## Implementation Decisions

### Database granularity
- Claude's discretion on normalization level and whether to use first-class lookup tables for teams/players/events vs inline IDs
- Versioned migration scripts for schema evolution (not drop-and-recreate) -- Phase 3 reconnaissance will likely reveal new fields
- Track scraping provenance: scraped_at, parser_version, source_url on key tables

### Raw HTML organization
- Organize by match first: `data/raw/matches/{match_id}/overview.html.gz`, `data/raw/matches/{match_id}/map-{mapstatsid}-stats.html.gz`, etc.
- Gzip compress all saved HTML files (.html.gz)
- Store inside project at `data/raw/` (gitignored)
- Keep everything forever -- no deletion or retention policy

### Access patterns
- Primary query interface: ad-hoc SQL queries (DB Browser, raw SQL) -- schema and indexes should be optimized for human SQL exploration
- Immediate writes: each parsed page writes to DB right away, no batching
- Silent UPSERT overwrite: re-scraping replaces old data, updated_at timestamp tracks freshness
- Fixed database location: `data/hltv.db`

### Offline replay
- Manual rebuild only: explicit command to re-parse from raw HTML, no automatic detection
- Claude's discretion on whether raw HTML is "source of truth" or "backup" role
- Claude's discretion on HTML save/load API design (full string return vs streaming, and whether the API is built in Phase 2 or deferred)

### Claude's Discretion
- Table normalization strategy and entity design
- First-class entity tables vs inline IDs
- Raw HTML save/load API shape (return string is fine given ~200KB page sizes)
- Whether HTML storage API is built in this phase or deferred to parsing phases
- Index strategy for common query patterns

</decisions>

<specifics>
## Specific Ideas

- Fetch-before-parse architecture: raw HTML is always saved to disk before any parsing occurs (established in roadmap)
- HLTV pages are typically 50-200KB uncompressed -- gzip brings that down to ~10-40KB
- Match IDs and mapstatsid values from HLTV URLs serve as natural primary keys
- The scraper uses nodriver (real Chrome) which returns full page HTML as strings

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 02-storage-foundation*
*Context gathered: 2026-02-14*
