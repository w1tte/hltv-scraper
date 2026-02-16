"""Pipeline utility classes for the HLTV scraper.

Provides three building blocks used by the pipeline runner (added in a
later plan):

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
