"""Adaptive rate limiter with jitter for HLTV request pacing.

Uses randomized delays with adaptive backoff to avoid detection by
Cloudflare's behavioral analysis. The limiter tracks elapsed time
between requests so processing time counts toward the delay.

Fully async -- uses asyncio.sleep and asyncio.Lock so concurrent
fetches are properly serialized without blocking the event loop.
"""

import asyncio
import logging
import random
import time

from scraper.config import ScraperConfig

logger = logging.getLogger(__name__)


class RateLimiter:
    """Manages delays between HTTP requests with jitter and adaptive backoff.

    The delay between requests is randomized within [current_delay, current_delay * 1.5]
    to avoid fixed-interval detection. On errors or Cloudflare challenges, call backoff()
    to increase the delay. On successes, call recover() to gradually decrease it.

    Time already spent processing since the last request is subtracted from the
    wait, so if processing took 4 seconds and the delay is 5 seconds, only 1
    second of actual sleep occurs.

    Uses an asyncio.Lock so multiple concurrent fetchers are properly
    serialized through the rate limiter.
    """

    def __init__(self, config: ScraperConfig | None = None):
        if config is None:
            config = ScraperConfig()

        self._min_delay = config.min_delay
        self._max_delay = config.max_delay
        self._backoff_factor = config.backoff_factor
        self._recovery_factor = config.recovery_factor
        self._max_backoff = config.max_backoff
        self._current_delay = config.min_delay
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

        # Accelerated recovery after consecutive successes
        self._fast_recovery = config.fast_recovery
        self._fast_recovery_threshold = config.fast_recovery_threshold
        self._consecutive_successes: int = 0

    @property
    def current_delay(self) -> float:
        """Current base delay value in seconds."""
        return self._current_delay

    async def wait(self) -> float:
        """Sleep for a jittered delay, accounting for elapsed processing time.

        Uses asyncio.Lock to serialize concurrent callers so requests are
        properly spaced even with multiple browser tabs.

        Returns:
            The jittered delay value (before elapsed-time adjustment).
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time

            # Jitter: uniform random in [current_delay, current_delay * 1.5]
            jittered_delay = random.uniform(
                self._current_delay, self._current_delay * 1.5
            )

            # Subtract time already elapsed since last request
            remaining = max(0.0, jittered_delay - elapsed)

            if remaining > 0:
                await asyncio.sleep(remaining)

            self._last_request_time = time.monotonic()
            return jittered_delay

    def backoff(self) -> None:
        """Increase delay after a failed request or Cloudflare challenge."""
        self._consecutive_successes = 0
        self._current_delay = min(
            self._current_delay * self._backoff_factor,
            self._max_backoff,
        )
        logger.warning(
            "Rate limiter backoff: delay now %.1fs", self._current_delay
        )

    def recover(self) -> None:
        """Gradually decrease delay after a successful request.

        When fast_recovery is enabled and consecutive successes exceed the
        threshold, uses recovery_factor^2 for more aggressive recovery.
        """
        self._consecutive_successes += 1
        if (
            self._fast_recovery
            and self._consecutive_successes >= self._fast_recovery_threshold
        ):
            factor = self._recovery_factor ** 2
        else:
            factor = self._recovery_factor
        self._current_delay = max(
            self._current_delay * factor,
            self._min_delay,
        )

    def reset(self) -> None:
        """Reset delay to minimum (e.g., after a long pause or IP change)."""
        self._current_delay = self._min_delay
