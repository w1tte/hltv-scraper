---
phase: 09-pipeline-orchestration
plan: 03
subsystem: pipeline-runner
tags: [pipeline, cli, argparse, asyncio, orchestration, console-script]

dependency_graph:
  requires:
    - "09-01 (ShutdownHandler, ConsecutiveFailureTracker, ProgressTracker)"
    - "09-02 (incremental discovery, reset_failed_matches, config fields)"
    - "04-03 (run_discovery orchestrator)"
    - "05-03 (run_match_overview orchestrator)"
    - "06-03 (run_map_stats orchestrator)"
    - "07-04 (run_performance_economy orchestrator)"
  provides:
    - "run_pipeline async function wiring all 4 stages"
    - "CLI entry point with argparse (hltv-scraper command)"
    - "console_scripts registration in pyproject.toml"
  affects:
    - "09-04 (integration testing of the full pipeline)"

tech_stack:
  added: []
  patterns:
    - "Sequential loop-until-done stage orchestration with shutdown checking"
    - "argparse CLI with --start-offset, --end-offset, --full, --force-rescrape, --data-dir"
    - "try/finally for guaranteed summary output on Ctrl+C"
    - "Untyped parameters on pipeline function to avoid circular imports"

key_files:
  created:
    - src/scraper/cli.py
  modified:
    - src/scraper/pipeline.py
    - pyproject.toml

decisions:
  - id: "09-03-01"
    decision: "run_pipeline uses untyped parameters (same as existing orchestrators)"
    reason: "Avoids circular imports -- pipeline.py imports from discovery.py, match_overview.py, etc."
  - id: "09-03-02"
    decision: "CLI maps --end-offset to config.max_offset"
    reason: "Consistent with 09-02 decision to NOT rename max_offset field"
  - id: "09-03-03"
    decision: "End-of-run summary printed in try/finally block"
    reason: "Guarantees summary output even on Ctrl+C or exception"

metrics:
  duration: "~5 min"
  completed: "2026-02-16"
  tasks: "3/3"
---

# Phase 9 Plan 03: Pipeline Runner and CLI Summary

**Sequential loop-until-done pipeline runner wiring all 4 stage orchestrators, with argparse CLI entry point and hltv-scraper console script registration.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-02-16T05:32:57Z
- **Completed:** 2026-02-16T06:03:44Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- `run_pipeline` async function orchestrates discovery -> overview -> map stats -> perf/economy with loop-until-done
- CLI entry point accepts 5 flags and sets up all components (logging, DB, repos, client)
- End-of-run summary always prints, even on Ctrl+C (try/finally guarantee)
- hltv-scraper console script registered and installable via pip

## Task Commits

Each task was committed atomically:

1. **Task 1: Pipeline runner function** - `e49f445` (feat)
2. **Task 2: CLI entry point** - `812c3d1` (feat)
3. **Task 3: pyproject.toml entry point** - `e1fa365` (chore)

## Files Created/Modified
- `src/scraper/pipeline.py` - Added `run_pipeline` async function (157 new lines) to existing utility classes file
- `src/scraper/cli.py` - New file: argparse CLI with `build_parser()`, `async_main()`, `main()`, and summary formatting
- `pyproject.toml` - Added `[project.scripts]` section mapping `hltv-scraper` to `scraper.cli:main`

## Decisions Made

1. **run_pipeline uses untyped parameters** -- Same pattern as all 4 existing orchestrators. Avoids circular imports since pipeline.py imports from discovery.py, match_overview.py, map_stats.py, and performance_economy.py.

2. **CLI maps --end-offset to config.max_offset** -- Consistent with 09-02 decision. Users see `--end-offset` (intuitive), code uses `config.max_offset` (backward compatible).

3. **End-of-run summary in try/finally** -- Summary printing is guaranteed even on Ctrl+C or unhandled exceptions. Browser cleanup is handled by HLTVClient's async context manager.

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

Plan 04 (integration testing) can proceed. The full pipeline is now runnable via:
- `hltv-scraper` (after `pip install -e .`)
- `python -m scraper.cli`

All 4 stage orchestrators are wired in sequence with shutdown checking, consecutive failure tracking, and progress reporting.

---
*Phase: 09-pipeline-orchestration*
*Completed: 2026-02-16*
