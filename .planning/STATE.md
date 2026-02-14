# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-14)

**Core value:** Reliably extract every available stat from HLTV match pages into a structured, queryable dataset -- without getting blocked.
**Current focus:** Phase 2 in progress. Completing Storage Foundation plans.

## Current Position

Phase: 2 of 9 (Storage Foundation) -- IN PROGRESS
Plan: 1 of 2 in current phase (02-01 complete)
Status: In progress
Last activity: 2026-02-15 -- Completed 02-01-PLAN.md (database schema, HTML storage, tests)

Progress: [████░░░░░░] 15%

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: ~13 min (02-01 was fast at 4 min, bringing average down)
- Total execution time: ~0.82 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-http-client | 3/3 | ~45 min | ~15 min |
| 02-storage-foundation | 1/2 | ~4 min | ~4 min |

**Recent Trend:**
- Last 4 plans: 01-01 (3 min), 01-02 (2 min), 01-03 (45 min -- included major deviation), 02-01 (4 min)
- 02-01 was fast: zero external dependencies (all stdlib), no integration surprises

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 9-phase pipeline architecture following fetch-before-parse pattern (raw HTML stored to disk before parsing)
- [Roadmap]: Phase 3 (Page Reconnaissance) inserted to understand HTML structure and edge cases before writing parsers
- [01-01]: Used stdlib dataclass for ScraperConfig (not pydantic) -- lightweight, no extra dependency
- [01-01]: All exceptions carry url and status_code as keyword-only attributes
- [01-01]: RateLimiter uses time.monotonic() for elapsed accounting
- [01-02]: tenacity @retry decorator inline on fetch() method; _patch_retry() overrides stop with config.max_retries
- **[01-03 DEVIATION]: curl_cffi replaced with nodriver** -- HLTV performance pages serve active Cloudflare JavaScript challenges (Turnstile) that no HTTP-only client can solve. nodriver (real Chrome, off-screen window) solves all 5 page types. user_agents.py deleted (real Chrome UA is superior to rotation).
- [01-03]: Off-screen Chrome: headless=False + --window-position=-32000,-32000 --window-size=1,1 (headless modes detected by Cloudflare)
- [01-03]: Minimum content threshold: 10,000 chars (detects incomplete page loads and Cloudflare interstitials)
- [01-03]: Extraction retry: if HTML < 10K chars, wait page_load_wait and re-extract before failing
- [02-01]: No separate entity lookup tables -- inline team/player IDs with names-at-time-of-match (intentional denormalization for historical accuracy)
- [02-01]: Composite primary keys on child tables for natural UPSERT conflict targets
- [02-01]: Per-row provenance (scraped_at, updated_at, source_url, parser_version) on all 5 tables
- [02-01]: Economy FK references round_history (strictest integrity); can relax via migration if needed
- [02-01]: HtmlStorage supports 4 match-page types only; results pages deferred to Phase 4

### Pending Todos

None yet.

### Blockers/Concerns

- [Research]: Economy data availability for historical matches uncertain -- verify in Phase 3 reconnaissance
- [Research]: Rating 2.0 vs 3.0 HTML differences unknown -- document in Phase 3 reconnaissance
- [01-03]: nodriver requires a real Chrome installation and runs a full browser process -- heavier than curl_cffi but necessary for Cloudflare bypass
- [02-01]: Economy→round_history FK may cause insertion issues if economy data exists without matching round history -- monitor in parsing phases

## Session Continuity

Last session: 2026-02-15
Stopped at: Completed 02-01-PLAN.md
Resume file: None
