# Phase 3: Page Reconnaissance - Context

**Gathered:** 2026-02-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Fetch, inspect, and document every HLTV page type the scraper will parse. Produce CSS selector maps, data field catalogs, structural variation docs, and edge case documentation. No parser code is written — this phase produces knowledge artifacts that Phases 4–7 consume.

</domain>

<decisions>
## Implementation Decisions

### Sample selection
- 5–6 sample matches per page type (results listing, match overview, map stats, performance, economy)
- Span the full CS2 era: include early CS2 (late 2023), mid-era (2024), and recent (2025–2026) to catch HTML structure changes over time
- Include tier-2/3 matches alongside top-tier events — lower-tier matches may have missing data or different structures, important to document early
- Claude picks all sample matches — select representative ones covering BO1, BO3, BO5, overtime, forfeit/walkover, different eras and events

### Documentation format
- Full detail per field: CSS selector + data type + optionality (always/sometimes present) + example value + notes on variations
- Include annotated HTML snippets showing actual page structure — makes it concrete for parsers
- Document ALL visible fields on each page, including those we're not planning to extract — mark which we extract vs skip, useful if scope expands later
- Claude decides the format (markdown tables vs JSON vs hybrid) based on what works best for downstream parser development

### Edge case scope
- Actively seek and document ALL edge case types:
  - Forfeit/walkover matches: document exactly which fields are missing or different
  - Overtime matches: dedicated analysis of how extra rounds appear, score changes, any new fields
  - BO5 matches: different veto structure, more maps
  - Showmatches / non-standard formats: exhibition matches, charity events, unusual formats
  - Rating 2.0/2.1 vs Rating 3.0: document differences, but depth of comparison is Claude's call
- **Rating version in DB**: Clearly flag which rating version each match uses so downstream consumers know unambiguously what they're working with

### Output organization
- Separate doc per page type: results listing, match overview, map stats, performance, economy
- Cross-page summary doc showing which data fields overlap between page types (helps decide canonical extraction source per field)
- Sample HTML files used during analysis but discarded after — not committed to repo. Can re-fetch if needed.

### Claude's Discretion
- Doc file location (phase directory vs dedicated folder)
- Selector map format choice (markdown tables, JSON, or hybrid)
- Rating version comparison depth
- Specific match IDs chosen as samples
- Internal doc structure within each page-type file

</decisions>

<specifics>
## Specific Ideas

- User wants comprehensive edge case coverage — "all types possible" — don't cut corners on unusual match formats
- Rating version tracking is a DB concern, not just a documentation concern: the scraper must store which rating system applies to each match's data
- Tier-2/3 match inclusion is specifically to surface data gaps early rather than discovering them during parsing phases

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-page-reconnaissance*
*Context gathered: 2026-02-15*
