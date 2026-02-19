"""Pipeline orchestration for the HLTV scraper.

Provides the ``run_pipeline`` async function that wires all four stage
orchestrators (discovery, match overview, map stats, performance/economy)
into a pipeline where stages 2-4 run concurrently via asyncio tasks.

Each downstream stage polls the DB for pending work.  When no work is
available and its upstream stage hasn't finished yet, it sleeps and retries.
When the upstream stage is done and no work remains, it terminates.

Also provides utility building blocks:

* **ShutdownHandler** -- cross-platform graceful Ctrl+C via
  ``signal.signal(SIGINT, ...)``.  First press sets a flag; second press
  force-exits.
* **ConsecutiveFailureTracker** -- halts the pipeline when *N* consecutive
  failures suggest a systemic problem (IP ban, site down).
* **ProgressTracker** -- per-match progress logging with timing and an
  end-of-run summary.
* **StageCoordinator** -- signals stage completion so downstream stages
  know when to stop polling.
"""

import asyncio
import logging
import signal
import time
from typing import Awaitable, Callable

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
        logger.info(
            "%s match %d %s (%.1fs) https://www.hltv.org/matches/%d",
            progress, match_id, symbol, elapsed, match_id,
        )

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
# Stage coordination
# ---------------------------------------------------------------------------

class StageCoordinator:
    """Coordinate stage completion for concurrent pipeline stages.

    Each stage gets an ``asyncio.Event``. When a stage finishes (success
    or failure), it marks itself done. Downstream stages poll this to
    decide whether to keep waiting for more work or terminate.
    """

    def __init__(self) -> None:
        self._done = {
            name: asyncio.Event()
            for name in ["discovery", "overview", "map_stats", "perf_economy"]
        }

    def mark_done(self, stage: str) -> None:
        self._done[stage].set()

    def is_done(self, stage: str) -> bool:
        return self._done[stage].is_set()


# ---------------------------------------------------------------------------
# Stage loop helper
# ---------------------------------------------------------------------------

async def _run_stage_loop(
    stage_name: str,
    upstream_stage: str,
    run_fn: Callable[..., Awaitable[dict]],
    run_fn_kwargs: dict,
    results_key: str,
    results: dict,
    coordinator: StageCoordinator,
    shutdown: ShutdownHandler,
    failure_tracker: ConsecutiveFailureTracker,
    progress: ProgressTracker,
    poll_interval: float,
    log_label: str,
) -> None:
    """Run a pipeline stage in a polling loop until no work remains.

    When the orchestrator returns ``batch_size == 0``:
    - If the upstream stage is not done yet, sleep and retry.
    - If the upstream stage IS done, do one final re-check for race
      condition safety, then exit.

    On exit (normal or failure), marks the stage as done in the
    coordinator so downstream stages can terminate.
    """
    logger.info("=== Stage: %s (concurrent) ===", stage_name)
    try:
        while not shutdown.is_set and not failure_tracker.should_halt:
            stats = await run_fn(**run_fn_kwargs)
            results[results_key]["parsed"] += stats["parsed"]
            results[results_key]["failed"] += stats["failed"]

            if stats["batch_size"] == 0:
                if coordinator.is_done(upstream_stage):
                    # Race condition safety: upstream just finished,
                    # re-check once in case work appeared after our query
                    recheck = await run_fn(**run_fn_kwargs)
                    results[results_key]["parsed"] += recheck["parsed"]
                    results[results_key]["failed"] += recheck["failed"]
                    if recheck["batch_size"] == 0:
                        break
                    # Got work on recheck, continue the loop
                    stats = recheck
                else:
                    await asyncio.sleep(poll_interval)
                    continue

            if stats["parsed"] > 0:
                failure_tracker.record_success()
            if stats["fetch_errors"] > 0 or (stats["failed"] > 0 and stats["parsed"] == 0):
                if failure_tracker.record_failure():
                    results["halted"] = True
                    results["halt_reason"] = (
                        f"Consecutive failures exceeded threshold ({stage_name} stage)"
                    )
                    break
            progress.log_stage(f"{log_label} batch", stats)
    finally:
        coordinator.mark_done(results_key)
        logger.info("Stage %s finished", stage_name)


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

async def run_pipeline(
    clients: dict,       # {"overview": [HLTVClient, ...], "map_stats": [...], "perf_economy": [...]}
    match_repo,          # MatchRepository
    discovery_repo,      # DiscoveryRepository
    storage,             # HtmlStorage
    config,              # ScraperConfig
    shutdown,            # ShutdownHandler
    incremental: bool = True,
    force_rescrape: bool = False,
) -> dict:
    """Run the full scraper pipeline: discovery -> overview + map stats + perf/economy.

    Stage 1 (discovery) runs sequentially. After it completes, stages 2-4
    launch as concurrent asyncio tasks, each with its own browser pool
    and failure tracker.

    Args:
        clients: Dict mapping stage names to lists of HLTVClient instances.
            Keys: ``"overview"``, ``"map_stats"``, ``"perf_economy"``.
            Discovery reuses the ``"overview"`` client list.
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
    coordinator = StageCoordinator()
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
    # Stage 1: Discovery (sequential, uses the overview client)
    # ---------------------------------------------------------------
    if not shutdown.is_set:
        logger.info("=== Stage 1: Discovery ===")
        try:
            discovery_stats = await run_discovery(
                clients["overview"], discovery_repo, storage, config,
                incremental=incremental, shutdown=shutdown,
            )
            results["discovery"] = discovery_stats
            progress.log_stage("Discovery", discovery_stats)
        except Exception as exc:
            logger.error("Discovery failed: %s", exc)
            results["halted"] = True
            results["halt_reason"] = f"Discovery failed: {exc}"
            results["summary"] = progress.summary()
            coordinator.mark_done("discovery")
            return results

    coordinator.mark_done("discovery")

    if shutdown.is_set:
        results["halted"] = True
        results["halt_reason"] = "User requested shutdown (Ctrl+C)"
        results["summary"] = progress.summary()
        return results

    # ---------------------------------------------------------------
    # Stages 2-4: Concurrent with per-stage failure tracking
    # ---------------------------------------------------------------
    poll_interval = config.stage_poll_interval
    threshold = config.consecutive_failure_threshold

    overview_tracker = ConsecutiveFailureTracker(threshold)
    map_stats_tracker = ConsecutiveFailureTracker(threshold)
    perf_economy_tracker = ConsecutiveFailureTracker(threshold)

    overview_task = asyncio.create_task(_run_stage_loop(
        stage_name="Match Overview",
        upstream_stage="discovery",
        run_fn=run_match_overview,
        run_fn_kwargs={
            "clients": clients["overview"],
            "match_repo": match_repo,
            "discovery_repo": discovery_repo,
            "storage": storage,
            "config": config,
        },
        results_key="overview",
        results=results,
        coordinator=coordinator,
        shutdown=shutdown,
        failure_tracker=overview_tracker,
        progress=progress,
        poll_interval=poll_interval,
        log_label="Match overview",
    ))

    map_stats_task = asyncio.create_task(_run_stage_loop(
        stage_name="Map Stats",
        upstream_stage="overview",
        run_fn=run_map_stats,
        run_fn_kwargs={
            "clients": clients["map_stats"],
            "match_repo": match_repo,
            "storage": storage,
            "config": config,
        },
        results_key="map_stats",
        results=results,
        coordinator=coordinator,
        shutdown=shutdown,
        failure_tracker=map_stats_tracker,
        progress=progress,
        poll_interval=poll_interval,
        log_label="Map stats",
    ))

    perf_economy_task = asyncio.create_task(_run_stage_loop(
        stage_name="Perf/Economy",
        upstream_stage="map_stats",
        run_fn=run_performance_economy,
        run_fn_kwargs={
            "clients": clients["perf_economy"],
            "match_repo": match_repo,
            "storage": storage,
            "config": config,
        },
        results_key="perf_economy",
        results=results,
        coordinator=coordinator,
        shutdown=shutdown,
        failure_tracker=perf_economy_tracker,
        progress=progress,
        poll_interval=poll_interval,
        log_label="Perf/economy",
    ))

    await asyncio.gather(overview_task, map_stats_task, perf_economy_task)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    results["summary"] = progress.summary()
    if shutdown.is_set:
        results["halted"] = True
        results["halt_reason"] = "User requested shutdown (Ctrl+C)"
    return results
