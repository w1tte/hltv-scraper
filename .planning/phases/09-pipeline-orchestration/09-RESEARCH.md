# Phase 9: Pipeline Orchestration - Research

**Researched:** 2026-02-16
**Domain:** Python asyncio pipeline orchestration, CLI, logging, graceful shutdown, state machine
**Confidence:** HIGH

## Summary

Phase 9 ties all existing orchestrators (discovery, match overview, map stats, performance/economy) into a single resumable CLI pipeline. The codebase already has all the building blocks: four async orchestrators that process batches, a scrape_queue with status tracking, and UPSERT-based persistence. What needs to be built is (1) a state machine that tracks per-match completion across all phases, (2) a pipeline runner that calls orchestrators in sequence and loops until no work remains, (3) graceful shutdown handling for Ctrl+C, (4) structured logging with console and file output, (5) an incremental discovery mode, and (6) a CLI entry point.

The project already uses stdlib exclusively (dataclass config, sqlite3, logging, argparse) with no heavy framework dependencies. This phase should continue that pattern: stdlib argparse for CLI, stdlib logging for output, asyncio.Event for shutdown signaling, and simple SQLite queries for state tracking. No new libraries are needed.

**Primary recommendation:** Build the pipeline as a single `scrape` command with flags (--start-offset, --end-offset, --full, --force-rescrape). Use an asyncio.Event-based shutdown flag checked between matches. Track completion via a simple SQL query across existing tables rather than adding a new state machine table (the data presence already encodes state).

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| argparse | stdlib | CLI argument parsing | Already in stdlib, no new dependency, perfect for this use case |
| logging | stdlib | Console + file logging | Already used throughout codebase via `logging.getLogger(__name__)` |
| asyncio | stdlib | Async pipeline execution | Already used by all 4 orchestrators |
| signal | stdlib | Ctrl+C handling | Cross-platform SIGINT capture |
| sqlite3 | stdlib | State tracking queries | Already the project database layer |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| time.monotonic | stdlib | Per-match timing | Measuring wall-clock time per match for progress log lines |
| datetime | stdlib | Log file timestamps | Generating run-YYYY-MM-DD-HHMMSS.log filenames |
| pathlib | stdlib | Log directory creation | Ensuring data/logs/ exists |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| argparse | click/typer | Adds dependency for minimal gain; argparse is sufficient for ~5 flags |
| stdlib logging | structlog/loguru | More powerful but adds dependency; project already has logging throughout |
| asyncio.Event | threading.Event | asyncio.Event integrates naturally with the async pipeline |

**Installation:**
```bash
# No new dependencies needed -- all stdlib
```

## Architecture Patterns

### Recommended Project Structure
```
src/scraper/
    pipeline.py          # Pipeline runner: calls orchestrators in sequence
    cli.py               # CLI entry point: argparse + asyncio.run
    (existing files unchanged)
```

### Pattern 1: Loop-Until-Done Pipeline Runner
**What:** The pipeline runner calls each orchestrator stage in a loop, processing batches until no pending work remains for that stage, then advances to the next stage.
**When to use:** This is the core pipeline pattern.
**Example:**
```python
async def run_pipeline(client, match_repo, discovery_repo, storage, config, shutdown: asyncio.Event):
    """Execute the full scrape pipeline: discover -> overview -> map stats -> perf/economy."""

    totals = {"discovered": 0, "overviews": 0, "map_stats": 0, "perf_economy": 0, "failed": 0}

    # Stage 1: Discovery
    if not shutdown.is_set():
        discovery_stats = await run_discovery_stage(client, discovery_repo, storage, config, shutdown)
        totals["discovered"] = discovery_stats["matches_found"]

    # Stage 2: Match overviews -- loop until no pending work
    while not shutdown.is_set():
        stats = await run_match_overview(client, match_repo, discovery_repo, storage, config)
        if stats["batch_size"] == 0:
            break
        totals["overviews"] += stats["parsed"]
        totals["failed"] += stats["failed"]
        if should_halt(stats, consecutive_failures):
            break

    # Stage 3: Map stats -- loop until no pending work
    while not shutdown.is_set():
        stats = await run_map_stats(client, match_repo, storage, config)
        if stats["batch_size"] == 0:
            break
        totals["map_stats"] += stats["parsed"]
        totals["failed"] += stats["failed"]
        if should_halt(stats, consecutive_failures):
            break

    # Stage 4: Performance + Economy -- loop until no pending work
    while not shutdown.is_set():
        stats = await run_performance_economy(client, match_repo, storage, config)
        if stats["batch_size"] == 0:
            break
        totals["perf_economy"] += stats["parsed"]
        totals["failed"] += stats["failed"]
        if should_halt(stats, consecutive_failures):
            break

    return totals
```

### Pattern 2: Shutdown Flag via asyncio.Event
**What:** Use an asyncio.Event as a shutdown flag. On Ctrl+C, set the flag. The pipeline checks it between batches.
**When to use:** For graceful Ctrl+C handling.
**Why asyncio.Event:** On Windows, `loop.add_signal_handler()` is NOT supported (raises NotImplementedError). The cross-platform approach is to catch KeyboardInterrupt at the `asyncio.run()` boundary or use `signal.signal()` in the main thread.
**Example:**
```python
import asyncio
import signal

_shutdown_event = asyncio.Event()

def _handle_sigint(sig, frame):
    """Set shutdown flag on Ctrl+C. Does NOT raise -- lets current work finish."""
    _shutdown_event.set()

async def main():
    # Install signal handler (works on both Windows and Unix)
    signal.signal(signal.SIGINT, _handle_sigint)

    async with HLTVClient(config) as client:
        try:
            totals = await run_pipeline(client, ..., shutdown=_shutdown_event)
        finally:
            print_summary(totals)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Already handled by signal handler
```

### Pattern 3: Consecutive Failure Threshold
**What:** Track consecutive failures across batches. Halt the pipeline when N consecutive matches fail (likely systemic issue like IP ban or site down).
**When to use:** Error handling policy from CONTEXT.md.
**Example:**
```python
class ConsecutiveFailureTracker:
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.consecutive = 0

    def record_success(self):
        self.consecutive = 0

    def record_failure(self) -> bool:
        """Returns True if threshold exceeded."""
        self.consecutive += 1
        return self.consecutive >= self.threshold

    @property
    def should_halt(self) -> bool:
        return self.consecutive >= self.threshold
```

### Pattern 4: State Derived from Data Presence (No New Table)
**What:** Instead of adding a new `scrape_log` table with explicit state transitions, derive per-match completion state from existing data. The existing schema already encodes state implicitly:
- **discovered**: match exists in `scrape_queue`
- **overview_done**: match exists in `matches` table
- **maps_done**: all maps have `player_stats` rows
- **complete**: all maps have `kpr IS NOT NULL` in `player_stats` (Phase 7 done)

**Why this is better than a new table:**
- Existing orchestrators already use this pattern (get_pending_map_stats uses NOT EXISTS, get_pending_perf_economy uses kpr IS NULL)
- scrape_queue.status already tracks pending/scraped/failed
- No schema migration needed
- State is always consistent with actual data (no stale state bugs)
- Simpler implementation

**When a new state table would be needed:** Only if we needed to track state beyond what data presence encodes (e.g., "this match was partially scraped at map stats level"). But the existing pending queries already handle this correctly.

### Pattern 5: Incremental Discovery with Early Termination
**What:** Discovery always starts from offset 0. On each page, check how many matches are already in the DB. If an entire page of 100 matches is already present, stop pagination early (all newer matches have been seen).
**When to use:** Incremental mode (the default).
**Example:**
```python
async def run_incremental_discovery(client, repo, storage, config, shutdown):
    """Discovery with early termination when all matches on a page are known."""
    for offset in range(config.start_offset, config.end_offset + 1, 100):
        if shutdown.is_set():
            break
        # ... fetch and parse page ...
        matches = parse_results_page(html)
        new_count = repo.persist_page_incremental(matches, offset)
        if new_count == 0:
            logger.info("All %d matches on offset %d already known. Stopping.", len(matches), offset)
            break
```

### Anti-Patterns to Avoid
- **Don't use `loop.add_signal_handler()` on Windows:** It raises NotImplementedError. Use `signal.signal()` instead, which works cross-platform.
- **Don't add a new state machine table:** The existing data presence queries (get_pending_matches, get_pending_map_stats, get_pending_perf_economy) already encode state implicitly. Adding a separate state table creates a synchronization problem.
- **Don't process stages in parallel:** Stages have data dependencies (overview must complete before map stats can run). Run sequentially.
- **Don't use `asyncio.run()` inside signal handlers:** Signal handlers must be synchronous and short.
- **Don't re-scrape completed work by default:** The existing UPSERT + pending queries naturally skip completed work.
- **Don't forget to close the browser:** HLTVClient.close() must always run, even on Ctrl+C. Use try/finally or async context manager.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CLI argument parsing | Custom argv parsing | stdlib argparse | Handles types, help, defaults, errors automatically |
| Log formatting | Custom print statements | stdlib logging with Formatter | Already integrated into every module via `logging.getLogger(__name__)` |
| Log file rotation | Manual file management | logging.FileHandler per-run | One log file per run is simpler than rotation; user decision confirms this |
| Retry on failed matches | Custom retry scheduling | Existing status='failed' -> reset to 'pending' | Just UPDATE scrape_queue SET status='pending' WHERE status='failed' on next run |
| State tracking | New scrape_log table | Existing pending queries + scrape_queue.status | Data presence already encodes state correctly |
| Per-match timing | Manual datetime calculations | time.monotonic() delta | Simple, non-drifting wall-clock measurement |

**Key insight:** The existing codebase already has all the building blocks. Phase 9's job is to wire them together with a loop, add progress logging, and provide a CLI. Resist the temptation to over-engineer state tracking when the existing queries already handle it.

## Common Pitfalls

### Pitfall 1: Windows Signal Handling
**What goes wrong:** Using `loop.add_signal_handler(signal.SIGINT, ...)` crashes with NotImplementedError on Windows.
**Why it happens:** Windows does not support POSIX signals in the asyncio event loop.
**How to avoid:** Use `signal.signal(signal.SIGINT, handler)` before `asyncio.run()`. This works on both Windows and Unix. The handler should set an asyncio.Event or a module-level flag, NOT raise an exception.
**Warning signs:** NotImplementedError at runtime, or tests that pass on Linux but fail on Windows.

### Pitfall 2: KeyboardInterrupt Cancelling All Tasks in Python 3.11+
**What goes wrong:** In Python 3.11+, pressing Ctrl+C during `asyncio.run()` cancels the main task via CancelledError. If you have cleanup work in the main coroutine, it may not execute.
**Why it happens:** Python 3.11 changed the default SIGINT behavior for asyncio to cancel the main task rather than raising KeyboardInterrupt synchronously.
**How to avoid:** Install a custom `signal.signal(signal.SIGINT, handler)` that suppresses the default behavior and sets a shutdown flag instead. Wrap `asyncio.run()` in try/except KeyboardInterrupt as a fallback.
**Warning signs:** Cleanup code (print summary, save state) not running after Ctrl+C.

### Pitfall 3: Browser Process Not Closing After Shutdown
**What goes wrong:** Chrome process stays alive after Ctrl+C, consuming resources and potentially locking ports.
**Why it happens:** If KeyboardInterrupt is raised while inside `await client.fetch()`, the async context manager's `__aexit__` may not run.
**How to avoid:** Always wrap the HLTVClient usage in try/finally with explicit `await client.close()`. The signal handler should set a flag, not raise an exception, so the current operation can complete and cleanup can happen normally.
**Warning signs:** Orphaned chrome.exe processes in task manager after Ctrl+C.

### Pitfall 4: Consecutive Failure Counter Reset Between Stages
**What goes wrong:** Tracking consecutive failures only within a single stage loses cross-stage failure correlation.
**Why it happens:** Each stage is a separate while loop with its own batch stats.
**How to avoid:** Track consecutive failures across the entire pipeline, not per-stage. A fetch error that causes batch discard should count toward the threshold regardless of which stage it happens in.
**Warning signs:** Pipeline continues to next stage after repeated fetch failures in previous stage.

### Pitfall 5: Discovery and Incremental Mode Interaction
**What goes wrong:** In incremental mode, discovery might stop too early if matches were inserted by a previous partial run (offset 0-300) but the user now wants a wider range.
**Why it happens:** The "entire page already in DB" check triggers on pages that were already discovered.
**How to avoid:** The early-termination logic should only check NEW matches on each page, not matches that were already in the queue. Use `persist_page_incremental()` that returns the count of truly new inserts (not UPSERTs of existing rows). Additionally, respect --start-offset/--end-offset which override the default 0-9900 range.
**Warning signs:** Running with --end-offset=5000 but pipeline stops at offset 300 because those matches were already discovered.

### Pitfall 6: Log File Not Flushed Before Exit
**What goes wrong:** Last few log lines missing from the log file after Ctrl+C.
**Why it happens:** FileHandler uses buffered I/O by default.
**How to avoid:** Explicitly call `logging.shutdown()` in the finally block, or configure the FileHandler with flush after every write.
**Warning signs:** Log file truncated compared to console output.

## Code Examples

Verified patterns from stdlib documentation and existing codebase conventions:

### CLI Entry Point with argparse
```python
# src/scraper/cli.py
import argparse
import asyncio
import sys

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hltv-scraper",
        description="Scrape CS2 match data from HLTV.org",
    )
    parser.add_argument(
        "--start-offset", type=int, default=0,
        help="Start offset for results pagination (default: 0)",
    )
    parser.add_argument(
        "--end-offset", type=int, default=9900,
        help="End offset for results pagination (default: 9900)",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Full scrape: re-discover all matches in offset range",
    )
    parser.add_argument(
        "--force-rescrape", action="store_true",
        help="Re-process already-complete matches",
    )
    parser.add_argument(
        "--data-dir", type=str, default="data",
        help="Data directory (default: data)",
    )
    return parser

def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass  # Handled by signal handler; summary already printed

if __name__ == "__main__":
    main()
```

### Logging Setup (Console + File)
```python
# src/scraper/logging_config.py
import logging
from datetime import datetime
from pathlib import Path

def setup_logging(data_dir: str = "data", console_level: int = logging.INFO) -> Path:
    """Configure logging with console (INFO) and file (DEBUG) handlers.

    Returns:
        Path to the log file.
    """
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    log_file = log_dir / f"run-{timestamp}.log"

    # Root logger at DEBUG to capture everything
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console handler: INFO+ with concise format
    console = logging.StreamHandler()
    console.setLevel(console_level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(console)

    # File handler: DEBUG+ with full format
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    ))
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("nodriver").setLevel(logging.WARNING)
    logging.getLogger("uc").setLevel(logging.WARNING)

    return log_file
```

### Graceful Shutdown (Cross-Platform)
```python
import asyncio
import signal
import logging

logger = logging.getLogger(__name__)

class ShutdownHandler:
    """Cross-platform graceful shutdown via Ctrl+C."""

    def __init__(self):
        self._event = asyncio.Event()
        self._original_handler = None

    def install(self):
        """Install SIGINT handler. Call before asyncio.run()."""
        self._original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle)

    def _handle(self, sig, frame):
        if self._event.is_set():
            # Second Ctrl+C: force exit
            logger.warning("Force shutdown requested")
            raise SystemExit(1)
        logger.info("Shutdown requested. Finishing current match...")
        self._event.set()

    @property
    def is_set(self) -> bool:
        return self._event.is_set()

    def restore(self):
        """Restore original signal handler."""
        if self._original_handler is not None:
            signal.signal(signal.SIGINT, self._original_handler)
```

### Per-Match Progress Logging
```python
import time

class ProgressTracker:
    """Track and log per-match progress."""

    def __init__(self, total: int = 0):
        self.total = total
        self.completed = 0
        self.failed = 0
        self.skipped = 0
        self._start_time = time.monotonic()

    def log_match(self, match_id: int, status: str, elapsed: float):
        self.completed += 1
        symbol = "ok" if status == "scraped" else "FAIL"
        progress = f"[{self.completed}/{self.total}]" if self.total > 0 else f"[{self.completed}]"
        logger.info(
            "%s match %d %s (%.1fs)",
            progress, match_id, symbol, elapsed,
        )

    def summary(self) -> str:
        wall_time = time.monotonic() - self._start_time
        return (
            f"Pipeline complete: {self.completed} processed, "
            f"{self.failed} failed, {self.skipped} skipped "
            f"in {wall_time:.1f}s"
        )
```

### Incremental Discovery Early Termination
```python
def count_new_matches(conn, match_ids: list[int]) -> int:
    """Count how many match IDs are NOT already in scrape_queue."""
    placeholders = ",".join("?" for _ in match_ids)
    row = conn.execute(
        f"SELECT COUNT(*) FROM scrape_queue WHERE match_id IN ({placeholders})",
        match_ids,
    ).fetchone()
    existing = row[0]
    return len(match_ids) - existing
```

### pyproject.toml Entry Point
```toml
[project.scripts]
hltv-scraper = "scraper.cli:main"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| loop.add_signal_handler() | signal.signal() for cross-platform | Python 3.11 | Must use signal.signal() on Windows |
| asyncio.get_event_loop().run_until_complete() | asyncio.run() | Python 3.7+ | Simpler entry point, handles cleanup |
| Manual event loop shutdown | asyncio.run() handles task cancellation | Python 3.11+ | Ctrl+C auto-cancels main task |

**Important for this project:**
- The project runs on **Windows 11** (from env). `loop.add_signal_handler()` MUST NOT be used.
- Python 3.11+ is required (pyproject.toml says >=3.11), so the improved SIGINT handling is available, but we override it with signal.signal() for controlled shutdown.

## Open Questions

Things that couldn't be fully resolved:

1. **nodriver browser cleanup on forced shutdown**
   - What we know: HLTVClient has an async close() method that calls browser.stop(). The async context manager calls this in __aexit__.
   - What's unclear: If signal.signal() sets a flag and we let the current fetch complete, cleanup should work normally. But if the user double-Ctrl+C (force exit), Chrome processes may orphan.
   - Recommendation: First Ctrl+C sets flag and waits; second Ctrl+C raises SystemExit(1). Document that orphaned Chrome processes may need manual cleanup after force-exit.

2. **Exact batch size tuning for pipeline throughput**
   - What we know: Current batch sizes are 10 for all stages. Each match requires 1 overview + N map stats + 2N perf/economy fetches. With rate limiting of 3-8s per request, a batch of 10 matches with 3 maps each takes ~30-50 minutes.
   - What's unclear: Whether batch size 10 is optimal for the pipeline loop pattern vs. smaller batches with more frequent state persistence.
   - Recommendation: Keep batch size 10 (existing default). It provides a good checkpoint interval (~30 min between state saves). The pipeline loop pattern means no work is lost even with large batches since data is committed per-batch.

3. **Failed match reset semantics**
   - What we know: CONTEXT.md says "failed matches auto-retry on next run". Currently scrape_queue.status='failed' means the match overview parse/persist failed.
   - What's unclear: Should failed matches be automatically reset to 'pending' at pipeline start, or should users need --force-rescrape?
   - Recommendation: Auto-reset status='failed' to 'pending' at pipeline start (this is the default behavior described in CONTEXT.md). --force-rescrape is for re-processing status='scraped' matches.

## Sources

### Primary (HIGH confidence)
- Existing codebase analysis: All 4 orchestrators, config, db, repository, discovery_repository, storage, validation (read in full)
- Existing migrations 001-005 (read in full)
- Python 3.14 docs: asyncio event loop, signal module, logging cookbook
- Existing test patterns: test_match_overview.py (full read) -- mocked client, real DB, real parsers

### Secondary (MEDIUM confidence)
- [Python asyncio platforms documentation](https://docs.python.org/3/library/asyncio-platforms.html) - Windows limitations for add_signal_handler
- [Python signal module docs](https://docs.python.org/3/library/signal.html) - Cross-platform signal handling
- [Python logging cookbook](https://docs.python.org/3/howto/logging-cookbook.html) - Console + file handler patterns
- [Setuptools entry points](https://setuptools.pypa.io/en/latest/userguide/entry_point.html) - console_scripts configuration

### Tertiary (LOW confidence)
- [wbenny/python-graceful-shutdown](https://github.com/wbenny/python-graceful-shutdown) - Shutdown flag pattern examples
- [SuperFastPython asyncio SIGINT](https://superfastpython.com/asyncio-control-c-sigint/) - Ctrl+C handling patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All stdlib, no new dependencies, verified against existing codebase
- Architecture: HIGH - Pipeline pattern directly informed by reading all 4 existing orchestrators
- Pitfalls: HIGH - Windows signal limitation verified against Python docs; browser cleanup verified against http_client.py code
- State tracking: HIGH - Verified existing pending queries in repository.py encode state implicitly
- CLI/logging: HIGH - stdlib argparse and logging, well-documented, widely used

**Research date:** 2026-02-16
**Valid until:** Indefinite (all stdlib, no version-sensitive findings)
