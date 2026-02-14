"""HLTV HTTP client with curl_cffi impersonation and anti-detection.

Wraps a curl_cffi Session with Cloudflare challenge detection, adaptive
rate limiting, User-Agent rotation, and tenacity retry logic. Every
subsequent phase uses HLTVClient.fetch() as the sole HTTP transport.
"""

import logging
from typing import Any

from curl_cffi.requests import Session

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from scraper.config import ScraperConfig
from scraper.exceptions import (
    CloudflareChallenge,
    HLTVFetchError,
    PageNotFound,
    RateLimited,
)
from scraper.rate_limiter import RateLimiter
from scraper.user_agents import UserAgentRotator

logger = logging.getLogger(__name__)

# Cloudflare HTML signatures found in challenge/block pages
_CF_HTML_SIGNATURES = (
    "cf-chl-widget",
    "challenge-platform",
    "_cf_chl_opt",
    "Checking your browser",
    "Just a moment...",
)


def _check_response(response: Any) -> None:
    """Inspect a curl_cffi response and raise the appropriate exception.

    Detection order matters -- check in this exact sequence:
    1. cf-mitigated header (most reliable Cloudflare signal)
    2. HTTP 429 (rate limited)
    3. HTTP 403/503 with HTML body (Cloudflare challenge pages)
    4. HTTP 404 (page not found -- not retriable)
    5. Any other HTTP >= 400 (generic fetch error)

    Args:
        response: A curl_cffi response object.

    Raises:
        CloudflareChallenge: Cloudflare served a challenge or block page.
        RateLimited: Server returned HTTP 429.
        PageNotFound: Server returned HTTP 404.
        HLTVFetchError: Any other HTTP error >= 400.
    """
    url = str(response.url)
    status = response.status_code
    headers = response.headers

    # 1. cf-mitigated header -- most reliable Cloudflare detection
    if headers.get("cf-mitigated", "").lower() == "challenge":
        raise CloudflareChallenge(
            f"Cloudflare challenge detected (cf-mitigated header) for {url}",
            url=url,
            status_code=status,
        )

    # 2. HTTP 429 -- rate limited
    if status == 429:
        retry_after = headers.get("Retry-After", "unknown")
        raise RateLimited(
            f"Rate limited (429) for {url}, Retry-After: {retry_after}",
            url=url,
            status_code=429,
        )

    # 3. HTTP 403 or 503 -- check for Cloudflare HTML signatures
    if status in (403, 503):
        content_type = headers.get("content-type", "")
        if "text/html" in content_type:
            body_snippet = response.text[:2000]
            for signature in _CF_HTML_SIGNATURES:
                if signature in body_snippet:
                    raise CloudflareChallenge(
                        f"Cloudflare challenge detected (HTML signature: {signature!r}) for {url}",
                        url=url,
                        status_code=status,
                    )
        # 403/503 without HTML signatures -- err on the side of caution
        raise CloudflareChallenge(
            f"Cloudflare challenge suspected ({status}) for {url}",
            url=url,
            status_code=status,
        )

    # 4. HTTP 404 -- page not found (not retriable)
    if status == 404:
        raise PageNotFound(
            f"Page not found (404) for {url}",
            url=url,
            status_code=404,
        )

    # 5. Any other HTTP error >= 400
    if status >= 400:
        raise HLTVFetchError(
            f"HTTP {status} for {url}",
            url=url,
            status_code=status,
        )

    # 6. Response is valid -- no exception


class HLTVClient:
    """HTTP client for HLTV with curl_cffi impersonation and anti-detection.

    Uses a single curl_cffi Session for the entire lifetime (cookie and
    connection persistence). Integrates RateLimiter for request pacing,
    UserAgentRotator for UA consistency, and tenacity for retry logic.

    Usage:
        with HLTVClient() as client:
            html = client.fetch("https://www.hltv.org/matches/12345/...")
    """

    def __init__(self, config: ScraperConfig | None = None):
        if config is None:
            config = ScraperConfig()

        self._config = config

        # Single session for entire client lifetime -- cookie/connection persistence
        self.session = Session(
            impersonate=config.impersonate_target,
            timeout=config.timeout,
        )

        # Rate limiter for request pacing
        self.rate_limiter = RateLimiter(config)

        # UA rotator matching the impersonation target's browser family
        self._ua_rotator = UserAgentRotator(config.impersonate_target)

        # Set initial UA headers (only User-Agent + Client Hints, not all headers)
        self.session.headers.update(self._ua_rotator.get_headers())

        # Request counters
        self._request_count = 0
        self._success_count = 0
        self._challenge_count = 0

        # Override tenacity stop condition with config value
        self._patch_retry()

    @retry(
        retry=retry_if_exception_type(
            (CloudflareChallenge, RateLimited, ConnectionError, TimeoutError, OSError)
        ),
        wait=wait_exponential_jitter(initial=10, max=120, jitter=5),
        stop=stop_after_attempt(5),  # overridden in _patch_retry
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def fetch(self, url: str) -> str:
        """Fetch a URL and return the response body as text.

        Rate-limits before each request, detects Cloudflare challenges,
        and retries with exponential backoff via tenacity.

        Args:
            url: The full URL to fetch.

        Returns:
            The response body as a string.

        Raises:
            PageNotFound: If the page returns 404 (not retried).
            HLTVFetchError: If a non-retriable HTTP error occurs.
            CloudflareChallenge: If all retries exhausted on Cloudflare challenges.
            RateLimited: If all retries exhausted on rate limiting.
        """
        self.rate_limiter.wait()
        self._request_count += 1

        try:
            response = self.session.get(url)
            _check_response(response)
        except (CloudflareChallenge, RateLimited):
            self.rate_limiter.backoff()
            self._challenge_count += 1
            raise

        # Success path
        self.rate_limiter.recover()
        self._success_count += 1
        logger.debug("Fetched %s (%d bytes)", url, len(response.text))
        return response.text

    def close(self) -> None:
        """Close the underlying curl_cffi session."""
        self.session.close()

    def __enter__(self) -> "HLTVClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    @property
    def stats(self) -> dict:
        """Return current client statistics.

        Returns:
            Dict with requests, successes, challenges, success_rate,
            and current_delay from the rate limiter.
        """
        total = self._request_count
        return {
            "requests": total,
            "successes": self._success_count,
            "challenges": self._challenge_count,
            "success_rate": (self._success_count / total) if total > 0 else 0.0,
            "current_delay": self.rate_limiter.current_delay,
        }

    def _patch_retry(self) -> None:
        """Patch tenacity stop condition to use config.max_retries.

        Called internally -- the @retry decorator uses a fixed default,
        but we override stop_after_attempt with the config value.
        """
        self.fetch.retry.stop = stop_after_attempt(self._config.max_retries)
