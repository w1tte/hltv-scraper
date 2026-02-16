"""Pipeline orchestration for the HLTV scraper.

Provides the ``run_pipeline`` async function that wires all four stage
orchestrators (discovery, match overview, map stats, performance/economy)
into a sequential loop-until-done pipeline with shutdown checking and
consecutive failure tracking.

Also provides three utility building blocks:

* **ShutdownHandler** -- cross-platform graceful Ctrl+C via
  ``signal.signal(SIGINT, ...)``.  First press sets a flag; second press
  force-exits.
* **ConsecutiveFailureTracker** -- halts the pipeline when *N* consecutive
  failures suggest a systemic problem (IP ban, site down).
* **ProgressTracker** -- per-match progress logging with timing and an
  end-of-run summary.
"""

import asyncio
import logging
import signal
import time

from scraper.discovery import run_discovery
from scraper.match_overview import run_match_overview
from scraper.map_stats import run_map_stats
from scraper.performance_economy import run_performance_economy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

class ShutdownHandler:
    """Cross-platform graceful shutdown via Ctrl+C.

    Uses ``signal.signal(SIGINT, ...)`` which works on both Windows and
    Unix (unlike ``loop.add_signal_handler`` which raises
    ``NotImplementedError`` on Windows).

    First Ctrl+C sets a flag so the current operation can finish cleanly.
    Second Ctrl+C raises ``SystemExit(1)`` for an immediate exit.
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._original_handler = None

    def install(self) -> None:
        """Save the current SIGINT handler and install our own."""
        self._original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handle)

    def _handle(self, sig, frame) -> None:  # noqa: ANN001
        if self._event.is_set():
            logger.warning("Force shutdown")
            raise SystemExit(1)
        logger.info("Shutdown requested. Finishing current work...")
        self._event.set()

    @property
    def is_set(self) -> bool:
        """Whether a shutdown has been requested."""
        return self._event.is_set()

    def restore(self) -> None:
        """Restore the original SIGINT handler if one was saved."""
        if self._original_handler is not None:
            signal.signal(signal.SIGINT, self._original_handler)


# ---------------------------------------------------------------------------
# Consecutive failure tracking
# ---------------------------------------------------------------------------

class ConsecutiveFailureTracker:
    """Track consecutive failures and halt when a threshold is reached.

    A run of *threshold* consecutive failures strongly suggests a systemic
    issue (Cloudflare ban, site outage) rather than isolated bad data.  The
    pipeline should stop instead of burning through requests.

    Any single success resets the counter.
    """

    def __init__(self, threshold: int = 3) -> None:
        self.threshold = threshold
        self.consecutive: int = 0

    def record_success(self) -> None:
        """Reset the consecutive failure counter."""
        self.consecutive = 0

    def record_failure(self) -> bool:
        """Increment the counter. Return ``True`` if threshold is reached."""
        self.consecutive += 1
        return self.consecutive >= self.threshold

    @property
    def should_halt(self) -> bool:
        """Whether the failure threshold has been reached or exceeded."""
        return self.consecutive >= self.threshold


# ---------------------------------------------------------------------------
# Progress tracking
# ---------------------------------------------------------------------------

class ProgressTracker:
    """Track and log per-match progress with timing.

    Maintains running counts of completed / failed / skipped matches and
    provides both machine-readable (``summary()``) and human-readable
    (``format_summary()``) end-of-run reports.
    """

    def __init__(self, total: int = 0) -> None:
        self.total = total
        self.completed: int = 0
        self.failed: int = 0
        self.skipped: int = 0
        self._start_time: float = time.monotonic()

    def log_match(self, match_id: int, status: str, elapsed: float) -> None:
        """Log a single match result.

        Args:
            match_id: HLTV numeric match ID.
            status: ``"scraped"`` for success, anything else for failure.
            elapsed: Seconds spent on this match.
        """
        self.completed += 1
        symbol = "ok" if status == "scraped" else "FAIL"
        if self.total > 0:
            progress = f"[{self.completed}/{self.total}]"
        else:
            progress = f"[{self.completed}]"
        logger.info("%s match %d %s (%.1fs)", progress, match_id, symbol, elapsed)

    def log_stage(self, stage: str, stats: dict) -> None:
        """Log a summary line for a completed pipeline stage.

        Args:
            stage: Human-readable stage name (e.g. ``"Discovery"``).
            stats: Arbitrary key/value pairs to display.
        """
        parts = [f"{k}: {v}" for k, v in stats.items()]
        logger.info("%s: %s", stage, ", ".join(parts))

    def summary(self) -> dict:
        """Return a machine-readable summary dict.

        Keys: ``completed``, ``failed``, ``skipped``, ``wall_time``.
        """
        return {
            "completed": self.completed,
            "failed": self.failed,
            "skipped": self.skipped,
            "wall_time": time.monotonic() - self._start_time,
        }

    def format_summary(self) -> str:
        """Return a human-readable multiline summary string."""
        wall = time.monotonic() - self._start_time
        minutes, seconds = divmod(wall, 60)
        lines = [
            "--- Pipeline Summary ---",
            f"  Completed : {self.completed}",
            f"  Failed    : {self.failed}",
            f"  Skipped   : {self.skipped}",
            f"  Wall time : {int(minutes)}m {seconds:.1f}s",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

async def run_pipeline(
    client,              # HLTVClient
    match_repo,          # MatchRepository
    discovery_repo,      # DiscoveryRepository
    storage,             # HtmlStorage
    config,              # ScraperConfig
    shutdown,            # ShutdownHandler
    incremental: bool = True,
    force_rescrape: bool = False,
) -> dict:
    """Run the full scraper pipeline: discovery -> overview -> map stats -> perf/economy.

    Each stage runs in a loop until no pending work remains (or shutdown
    is requested, or consecutive failures exceed the threshold).

    Uses untyped parameters (same pattern as the individual orchestrators)
    to avoid circular imports.

    Args:
        client: HLTVClient instance (must be started).
        match_repo: MatchRepository instance.
        discovery_repo: DiscoveryRepository instance.
        storage: HtmlStorage instance.
        config: ScraperConfig instance.
        shutdown: ShutdownHandler instance.
        incremental: If True (default), discovery stops when all matches
            on a page are already known.
        force_rescrape: If True, resets all scraped matches to pending
            before running.

    Returns:
        Dict with per-stage results, halt status, and summary.
    """
    failure_tracker = ConsecutiveFailureTracker(config.consecutive_failure_threshold)
    progress = ProgressTracker(total=0)

    results = {
        "discovery": {},
        "overview": {"parsed": 0, "failed": 0},
        "map_stats": {"parsed": 0, "failed": 0},
        "perf_economy": {"parsed": 0, "failed": 0},
        "halted": False,
        "halt_reason": None,
    }

    # Auto-reset failed matches so they get another chance
    if not force_rescrape:
        reset_count = discovery_repo.reset_failed_matches()
        if reset_count > 0:
            logger.info("Reset %d failed matches to pending", reset_count)

    # ---------------------------------------------------------------
    # Stage 1: Discovery
    # ---------------------------------------------------------------
    if not shutdown.is_set:
        logger.info("=== Stage 1: Discovery ===")
        try:
            discovery_stats = await run_discovery(
                client, discovery_repo, storage, config,
                incremental=incremental, shutdown=shutdown,
            )
            results["discovery"] = discovery_stats
            progress.log_stage("Discovery", discovery_stats)
            failure_tracker.record_success()
        except Exception as exc:
            logger.error("Discovery failed: %s", exc)
            if failure_tracker.record_failure():
                results["halted"] = True
                results["halt_reason"] = f"Discovery failed: {exc}"
                results["summary"] = progress.summary()
                return results

    # ---------------------------------------------------------------
    # Stage 2: Match Overview -- loop until no pending work
    # ---------------------------------------------------------------
    if not shutdown.is_set:
        logger.info("=== Stage 2: Match Overview ===")
    while not shutdown.is_set and not failure_tracker.should_halt:
        stats = await run_match_overview(
            client, match_repo, discovery_repo, storage, config,
        )
        results["overview"]["parsed"] += stats["parsed"]
        results["overview"]["failed"] += stats["failed"]
        if stats["batch_size"] == 0:
            break
        if stats["parsed"] > 0:
            failure_tracker.record_success()
        if stats["fetch_errors"] > 0 or (stats["failed"] > 0 and stats["parsed"] == 0):
            if failure_tracker.record_failure():
                results["halted"] = True
                results["halt_reason"] = "Consecutive failures exceeded threshold (overview stage)"
                break
        progress.log_stage("Match overview batch", stats)

    # ---------------------------------------------------------------
    # Stage 3: Map Stats -- loop until no pending work
    # ---------------------------------------------------------------
    if not shutdown.is_set and not failure_tracker.should_halt:
        logger.info("=== Stage 3: Map Stats ===")
    while not shutdown.is_set and not failure_tracker.should_halt:
        stats = await run_map_stats(client, match_repo, storage, config)
        results["map_stats"]["parsed"] += stats["parsed"]
        results["map_stats"]["failed"] += stats["failed"]
        if stats["batch_size"] == 0:
            break
        if stats["parsed"] > 0:
            failure_tracker.record_success()
        if stats["fetch_errors"] > 0 or (stats["failed"] > 0 and stats["parsed"] == 0):
            if failure_tracker.record_failure():
                results["halted"] = True
                results["halt_reason"] = "Consecutive failures exceeded threshold (map stats stage)"
                break
        progress.log_stage("Map stats batch", stats)

    # ---------------------------------------------------------------
    # Stage 4: Performance + Economy -- loop until no pending work
    # ---------------------------------------------------------------
    if not shutdown.is_set and not failure_tracker.should_halt:
        logger.info("=== Stage 4: Performance + Economy ===")
    while not shutdown.is_set and not failure_tracker.should_halt:
        stats = await run_performance_economy(client, match_repo, storage, config)
        results["perf_economy"]["parsed"] += stats["parsed"]
        results["perf_economy"]["failed"] += stats["failed"]
        if stats["batch_size"] == 0:
            break
        if stats["parsed"] > 0:
            failure_tracker.record_success()
        if stats["fetch_errors"] > 0 or (stats["failed"] > 0 and stats["parsed"] == 0):
            if failure_tracker.record_failure():
                results["halted"] = True
                results["halt_reason"] = "Consecutive failures exceeded threshold (perf/economy stage)"
                break
        progress.log_stage("Perf/economy batch", stats)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    results["summary"] = progress.summary()
    if shutdown.is_set:
        results["halted"] = True
        results["halt_reason"] = "User requested shutdown (Ctrl+C)"
    return results
