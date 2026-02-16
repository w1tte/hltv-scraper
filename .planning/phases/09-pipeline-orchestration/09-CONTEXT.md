# Phase 9: Pipeline Orchestration - Context

**Gathered:** 2026-02-16
**Status:** Ready for planning

<domain>
## Phase Boundary

End-to-end pipeline that runs discovery through validation as a single resumable command. Tracks per-match state, supports incremental mode (scrape only new matches), resumes after interruption, and logs progress + errors to console and file.

</domain>

<decisions>
## Implementation Decisions

### CLI invocation
- Claude's discretion on single command vs subcommands — pick what fits the project
- Scope controlled via offset range: --start-offset and --end-offset flags
- No dry-run mode needed — user will test with small offset ranges (e.g. 0 to 300)
- Claude's discretion on data directory location — sensible default, optionally configurable

### Progress reporting
- Per-match log lines to console: one line per match showing match ID, status, and timing
  - e.g. `[142/500] match 2389951 ✓ scraped (4.2s)`
- Log file written on every run (timestamped, e.g. data/logs/run-2026-02-16.log)
- End-of-run summary includes counts + breakdown: matches discovered/scraped/validated/failed/skipped, list of failed match IDs, per-stage timings, error categories

### Error handling policy
- Consecutive failure threshold: halt after ~3 consecutive failures (likely systemic — IP ban, site down)
- Isolated failures allowed but pipeline stops once threshold hit
- Failed matches auto-retry on next run (go back to pending state)
- Ctrl+C triggers graceful shutdown: finish current match, save state, print summary, exit cleanly

### Incremental behavior
- Incremental mode is the default — pipeline skips already-completed matches
- Discovery re-paginates from offset 0; stops when an entire page of 100 matches is already in DB
- --full flag to force full re-scrape within offset range
- --force-rescrape flag to re-process already-complete matches (for rare corrections)

### Claude's Discretion
- Single command vs subcommands (CLI structure)
- Default data directory location
- Exact consecutive failure threshold number
- Log file naming and rotation
- Internal state machine transitions

</decisions>

<specifics>
## Specific Ideas

- "Just run it with a small offset from 0 to perhaps 300 for starters" — user expects easy test runs with limited scope
- Per-match timing in log lines helps estimate remaining time during long runs

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-pipeline-orchestration*
*Context gathered: 2026-02-16*
