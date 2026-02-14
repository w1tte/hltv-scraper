# Phase 1: HTTP Client and Anti-Detection - Context

**Gathered:** 2026-02-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a reliable HTTP transport layer that can fetch any HLTV page type without triggering Cloudflare blocks. This includes the HTTP client, rate limiting, User-Agent rotation, and error recovery with retries. Does NOT include parsing, storage, or page-specific logic.

</domain>

<decisions>
## Implementation Decisions

### Cloudflare bypass strategy
- Research and use the most efficient/fastest technique that reliably bypasses Cloudflare on all HLTV page types
- The performance page (`/stats/matches/performance/mapstatsid/{id}/{slug}`) is specifically known to be harder to reach with scrapers — the chosen technique MUST be validated against this page type
- All 5 page types must be reachable: results listing, match overview, map overview, map performance, map economy
- Prioritize speed/efficiency — don't use heavyweight approaches (full browser) if lighter ones work

### Claude's Discretion
- **Cloudflare bypass technique selection** — curl_cffi, browser automation, or hybrid. Research deeply and pick what works best for HLTV in 2026. Test against the performance page specifically.
- **Rate limiting strategy** — adaptive vs fixed, delay ranges, throttle response. Optimize for speed without triggering blocks.
- **Retry and failure policy** — retry counts, backoff curves, when to give up. Standard robust patterns.
- **Configuration surface** — what's configurable vs hardcoded. Pragmatic defaults.
- **User-Agent rotation** — list, rotation strategy, browser fingerprint consistency.

</decisions>

<specifics>
## Specific Ideas

- The map performance page is explicitly called out as harder to scrape — use this as the litmus test for whether the bypass technique is sufficient
- User wants deep research into current techniques before committing to an approach
- Speed matters — the scraper will be hitting thousands of pages, so efficiency of the HTTP layer compounds

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-http-client-and-anti-detection*
*Context gathered: 2026-02-14*
