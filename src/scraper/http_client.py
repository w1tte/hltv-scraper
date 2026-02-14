"""HLTV HTTP client using nodriver for Cloudflare bypass.

Uses a real Chrome browser (off-screen window) to navigate HLTV pages,
solving Cloudflare challenges automatically. Integrates RateLimiter
for request pacing and tenacity for retry logic.

Why nodriver instead of curl_cffi:
  HLTV's /stats/matches/performance/ pages serve an active Cloudflare
  JavaScript challenge (Turnstile) that no HTTP-only client can solve.
  nodriver runs real Chrome, which solves challenges natively. The
  off-screen window (--window-position=-32000,-32000) makes it
  effectively invisible.
"""

import asyncio
import logging
from typing import Any

import nodriver

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
)
from scraper.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Challenge page indicators in the page title
_CHALLENGE_TITLES = ("Just a moment...", "Checking your browser")


class HLTVClient:
    """HTTP client for HLTV using nodriver (real Chrome) for Cloudflare bypass.

    Uses a single Chrome browser instance with an off-screen window to
    navigate HLTV pages. Cloudflare challenges are solved automatically
    by Chrome's JavaScript engine. Integrates RateLimiter for adaptive
    request pacing.

    Usage:
        async with HLTVClient() as client:
            html = await client.fetch("https://www.hltv.org/matches/12345/...")
    """

    def __init__(self, config: ScraperConfig | None = None):
        if config is None:
            config = ScraperConfig()

        self._config = config
        self.rate_limiter = RateLimiter(config)
        self._browser: nodriver.Browser | None = None

        # Request counters
        self._request_count = 0
        self._success_count = 0
        self._challenge_count = 0

        # Override tenacity stop condition with config value
        self._patch_retry()

    async def start(self) -> None:
        """Launch the Chrome browser off-screen."""
        self._browser = await nodriver.start(
            headless=False,
            browser_args=[
                "--window-position=-32000,-32000",
                "--window-size=1,1",
            ],
        )

    @retry(
        retry=retry_if_exception_type(CloudflareChallenge),
        wait=wait_exponential_jitter(initial=10, max=120, jitter=5),
        stop=stop_after_attempt(5),  # overridden in _patch_retry
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch(self, url: str) -> str:
        """Navigate to a URL and return the page HTML.

        Rate-limits before each navigation, detects Cloudflare challenges
        by page title, and retries with exponential backoff via tenacity.

        Args:
            url: The full URL to fetch.

        Returns:
            The page HTML as a string.

        Raises:
            CloudflareChallenge: If Cloudflare challenge persists after retries.
            HLTVFetchError: If the page content is empty or invalid.
        """
        if self._browser is None:
            raise HLTVFetchError("Browser not started. Call start() first.", url=url)

        self.rate_limiter.wait()
        self._request_count += 1

        try:
            page = await self._browser.get(url)
            await asyncio.sleep(self._config.page_load_wait)

            # Check for Cloudflare challenge via page title
            title = await page.evaluate("document.title")

            if any(sig in title for sig in _CHALLENGE_TITLES):
                # Wait longer — Chrome may auto-solve the challenge
                await asyncio.sleep(self._config.challenge_wait)
                title = await page.evaluate("document.title")

                if any(sig in title for sig in _CHALLENGE_TITLES):
                    self._challenge_count += 1
                    self.rate_limiter.backoff()
                    raise CloudflareChallenge(
                        f"Cloudflare challenge on {url} (title: {title!r})",
                        url=url,
                    )

            # Extract full HTML
            html = await page.evaluate("document.documentElement.outerHTML")

            if not html or len(html) < 10000:
                raise HLTVFetchError(
                    f"Response too short from {url} ({len(html or '')} chars)",
                    url=url,
                )

        except CloudflareChallenge:
            raise
        except Exception as exc:
            raise HLTVFetchError(
                f"Failed to fetch {url}: {exc}", url=url
            ) from exc

        # Success
        self.rate_limiter.recover()
        self._success_count += 1
        logger.debug("Fetched %s (%d chars)", url, len(html))
        return html

    async def close(self) -> None:
        """Stop the Chrome browser."""
        if self._browser:
            self._browser.stop()
            self._browser = None

    async def __aenter__(self) -> "HLTVClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    @property
    def stats(self) -> dict:
        """Return current client statistics."""
        total = self._request_count
        return {
            "requests": total,
            "successes": self._success_count,
            "challenges": self._challenge_count,
            "success_rate": (self._success_count / total) if total > 0 else 0.0,
            "current_delay": self.rate_limiter.current_delay,
        }

    def _patch_retry(self) -> None:
        """Patch tenacity stop condition to use config.max_retries."""
        self.fetch.retry.stop = stop_after_attempt(self._config.max_retries)
