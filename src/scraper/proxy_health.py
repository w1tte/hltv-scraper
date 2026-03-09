"""Proxy health scoring and smart rotation.

Tracks per-proxy success rate and latency over a rolling window,
blacklists proxies exceeding a failure threshold, and auto-unblacklists
after a cooldown period.  Used by HLTVClient to pick the best proxy
on rotation instead of blind round-robin.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProxyStats:
    """Rolling stats for a single proxy."""

    success_count: int = 0
    failure_count: int = 0
    last_failure_time: float = 0.0
    # Rolling window of recent results (True=success, False=failure)
    _recent_results: deque = field(default_factory=lambda: deque(maxlen=20))
    _recent_latencies: deque = field(default_factory=lambda: deque(maxlen=20))

    @property
    def avg_latency(self) -> float:
        if not self._recent_latencies:
            return float("inf")
        return sum(self._recent_latencies) / len(self._recent_latencies)

    @property
    def failure_rate(self) -> float:
        if not self._recent_results:
            return 0.0
        failures = sum(1 for r in self._recent_results if not r)
        return failures / len(self._recent_results)

    @property
    def total_requests(self) -> int:
        return self.success_count + self.failure_count


class ProxyHealthTracker:
    """Track proxy health metrics and provide smart proxy selection.

    Args:
        proxy_urls: List of proxy URLs to track.
        blacklist_threshold: Failure rate (0-1) over the rolling window
            that triggers blacklisting.  Default 0.6 (60%).
        blacklist_window: Number of recent requests to consider for
            failure rate calculation.  Default 20.
        cooldown_seconds: Seconds before a blacklisted proxy is
            automatically un-blacklisted.  Default 300 (5 minutes).
    """

    def __init__(
        self,
        proxy_urls: list[str],
        blacklist_threshold: float = 0.6,
        blacklist_window: int = 20,
        cooldown_seconds: float = 300.0,
    ):
        self._proxy_urls = list(proxy_urls)
        self._blacklist_threshold = blacklist_threshold
        self._blacklist_window = blacklist_window
        self._cooldown_seconds = cooldown_seconds
        self._stats: dict[str, ProxyStats] = {
            url: ProxyStats(
                _recent_results=deque(maxlen=blacklist_window),
                _recent_latencies=deque(maxlen=blacklist_window),
            )
            for url in proxy_urls
        }
        self._blacklisted: set[str] = set()

    def record_success(self, proxy_url: str, latency: float) -> None:
        """Record a successful request through this proxy."""
        stats = self._stats.get(proxy_url)
        if stats is None:
            return
        stats.success_count += 1
        stats._recent_results.append(True)
        stats._recent_latencies.append(latency)

    def record_failure(self, proxy_url: str) -> None:
        """Record a failed request through this proxy."""
        stats = self._stats.get(proxy_url)
        if stats is None:
            return
        stats.failure_count += 1
        stats.last_failure_time = time.monotonic()
        stats._recent_results.append(False)
        self._check_blacklist(proxy_url)

    def _check_blacklist(self, proxy_url: str) -> None:
        """Blacklist proxy if failure rate exceeds threshold over the window."""
        stats = self._stats[proxy_url]
        if len(stats._recent_results) >= self._blacklist_window:
            if stats.failure_rate > self._blacklist_threshold:
                if proxy_url not in self._blacklisted:
                    self._blacklisted.add(proxy_url)
                    logger.warning(
                        "Blacklisted proxy %s (%.0f%% failure rate over %d requests)",
                        proxy_url,
                        stats.failure_rate * 100,
                        len(stats._recent_results),
                    )

    def _unblacklist_expired(self) -> None:
        """Un-blacklist proxies whose cooldown period has expired."""
        now = time.monotonic()
        expired = set()
        for proxy_url in self._blacklisted:
            stats = self._stats[proxy_url]
            if now - stats.last_failure_time >= self._cooldown_seconds:
                expired.add(proxy_url)
                # Clear window to give the proxy a fresh start
                stats._recent_results.clear()
                logger.info("Un-blacklisted proxy %s (cooldown expired)", proxy_url)
        self._blacklisted -= expired

    def select_best_proxy(self, current_proxy: str | None = None) -> str | None:
        """Select the best available proxy: lowest avg latency, not blacklisted.

        Returns None if no proxies are available (shouldn't happen — falls
        back to un-blacklisting the oldest failure).
        """
        if not self._proxy_urls:
            return current_proxy

        self._unblacklist_expired()

        candidates = [
            url for url in self._proxy_urls if url not in self._blacklisted
        ]

        if not candidates:
            # All blacklisted — un-blacklist the one with the oldest failure
            logger.warning(
                "All %d proxies blacklisted — un-blacklisting oldest failure",
                len(self._blacklisted),
            )
            oldest = min(
                self._blacklisted,
                key=lambda u: self._stats[u].last_failure_time,
            )
            self._blacklisted.discard(oldest)
            self._stats[oldest]._recent_results.clear()
            candidates = [oldest]

        # Prefer lowest avg latency.  Untested proxies (no requests yet)
        # sort first so they get tried.
        def _sort_key(url: str) -> tuple:
            stats = self._stats[url]
            if stats.total_requests == 0:
                return (0, 0.0)  # untested: highest priority
            return (1, stats.avg_latency)

        candidates.sort(key=_sort_key)
        return candidates[0]

    def is_blacklisted(self, proxy_url: str) -> bool:
        """Check if a proxy is currently blacklisted."""
        return proxy_url in self._blacklisted

    def log_health_summary(self) -> None:
        """Log health stats for all tracked proxies."""
        self._unblacklist_expired()
        for url in self._proxy_urls:
            stats = self._stats[url]
            bl = " [BLACKLISTED]" if url in self._blacklisted else ""
            logger.info(
                "Proxy health: %s — %d ok, %d fail (%.0f%% fail rate), "
                "avg_latency=%.2fs%s",
                url,
                stats.success_count,
                stats.failure_count,
                stats.failure_rate * 100,
                stats.avg_latency if stats._recent_latencies else 0.0,
                bl,
            )
