# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-14)

**Core value:** Reliably extract every available stat from HLTV match pages into a structured, queryable dataset -- without getting blocked.
**Current focus:** Phase 3 in progress. Plan 03-02 (results listing analysis) complete. Next: 03-03 (match overview analysis)

## Current Position

Phase: 3 of 9 (Page Reconnaissance) -- IN PROGRESS
Plan: 2 of 7 in current phase (03-02 complete)
Status: In progress
Last activity: 2026-02-15 -- Completed 03-02-PLAN.md (results listing selector map)

Progress: [██████░░░░] 58%

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: ~11 min
- Total execution time: ~1.2 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-http-client | 3/3 | ~45 min | ~15 min |
| 02-storage-foundation | 2/2 | ~6 min | ~3 min |
| 03-page-reconnaissance | 2/7 | ~24 min | ~12 min |

**Recent Trend:**
- Last 5 plans: 01-03 (45 min -- included major deviation), 02-01 (4 min), 02-02 (2 min), 03-01 (17 min -- live fetching with pauses), 03-02 (7 min)
- 03-02 was fast: pure offline analysis against saved HTML samples

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
- [02-02]: MatchRepository takes sqlite3.Connection (not Database) for test decoupling
- [02-02]: UPSERT SQL as module-level constants; batch methods use loop inside with conn: (not executemany)
- [02-02]: Read methods return dict (via dict(row)); exceptions propagate to callers
- [03-01]: All HLTV pages now show Rating 3.0 (retroactive application confirmed) -- no Rating 2.0/2.1 column handling needed
- [03-01]: Forfeit matches have map name "Default" and zero mapstatsids -- parsers must detect this
- [03-01]: HLTV URL slug is cosmetic; numeric match ID determines content
- [03-01]: HTML samples in data/recon/ (gitignored); fetch scripts in scripts/ for reproducibility
- [03-02]: Big-results featured section (page 1 only) is exact duplicate of regular results -- parsers must skip it
- [03-02]: map-text encodes format (bo3/bo5), BO1 map name (nuke/ovp/mrg), and forfeit (def) in a single field
- [03-02]: Use last .results-all container on page to skip big-results; data-zonedgrouping-entry-unix on each .result-con for timestamps

### Pending Todos

None yet.

### Blockers/Concerns

- [Research]: Economy data availability for historical matches uncertain -- verify in Phase 3 reconnaissance (economy pages exist for 2023 matches per 03-01)
- ~~[Research]: Rating 2.0 vs 3.0 HTML differences unknown~~ -- RESOLVED in 03-01: all pages use Rating 3.0 after retroactive application
- [01-03]: nodriver requires a real Chrome installation and runs a full browser process -- heavier than curl_cffi but necessary for Cloudflare bypass
- [02-01]: Economy->round_history FK may cause insertion issues if economy data exists without matching round history -- monitor in parsing phases

## Session Continuity

Last session: 2026-02-15
Stopped at: Completed 03-02-PLAN.md (results listing selector map)
Resume file: None
