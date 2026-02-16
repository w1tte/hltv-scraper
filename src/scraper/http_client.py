"""HLTV HTTP client using nodriver for Cloudflare bypass.

Uses a real Chrome browser (off-screen window) to navigate HLTV pages,
solving Cloudflare challenges automatically. Integrates RateLimiter
for request pacing and tenacity for retry logic.

On start(), navigates to HLTV and waits for Cloudflare to clear. All
subsequent fetches reuse the SAME browser tab (navigating it to new
URLs) so the Cloudflare clearance persists.

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

# Warm-up: max seconds to wait for Cloudflare to clear on first visit
_WARMUP_TIMEOUT = 30
_POLL_INTERVAL = 2


class HLTVClient:
    """HTTP client for HLTV using nodriver (real Chrome) for Cloudflare bypass.

    Uses a single Chrome browser instance with an off-screen window.
    On start(), navigates to the HLTV homepage and waits for Cloudflare
    to clear. All subsequent fetches reuse the same browser tab
    (navigating it to new URLs) so the clearance persists.

    Usage:
        async with HLTVClient() as client:
            html = await client.fetch("https://www.hltv.org/matches/12345/...")
            results = await client.fetch_many(["url1", "url2", "url3"])
    """

    def __init__(self, config: ScraperConfig | None = None):
        if config is None:
            config = ScraperConfig()

        self._config = config
        self.rate_limiter = RateLimiter(config)
        self._browser: nodriver.Browser | None = None
        self._tab = None  # The single reused browser tab

        # Request counters
        self._request_count = 0
        self._success_count = 0
        self._challenge_count = 0

        # Override tenacity stop condition with config value
        self._patch_retry()

    async def start(self) -> None:
        """Launch Chrome off-screen and warm up Cloudflare trust.

        Navigates to an HLTV results page and polls until the Cloudflare
        challenge clears (up to 30s). This ensures that the harder CF
        protection on /results (and /stats) paths is solved before any
        real fetching begins. The warm-up tab is saved and reused for
        all subsequent fetches.
        """
        self._browser = await nodriver.start(
            headless=False,
            browser_args=[
                "--window-position=-32000,-32000",
                "--window-size=800,600",
            ],
        )

        # Warm-up: visit a results page with gameType to match real fetch URLs
        warmup_url = (
            f"{self._config.base_url}/results?offset=0"
            f"&gameType={self._config.game_type}"
        )
        logger.info("Warming up browser on %s ...", warmup_url)
        self._tab = await self._browser.get(warmup_url)
        await asyncio.sleep(self._config.page_load_wait)

        elapsed = 0.0
        while elapsed < _WARMUP_TIMEOUT:
            title = await self._tab.evaluate("document.title")
            if not any(sig in title for sig in _CHALLENGE_TITLES):
                logger.info(
                    "Cloudflare cleared after %.1fs",
                    elapsed + self._config.page_load_wait,
                )
                # Let CF cookies settle before real fetches begin
                await asyncio.sleep(1.0)
                return
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL

        logger.warning(
            "Cloudflare challenge did not clear after %ds warm-up. "
            "Proceeding anyway — fetches may retry.",
            _WARMUP_TIMEOUT,
        )

    @retry(
        retry=retry_if_exception_type(CloudflareChallenge),
        wait=wait_exponential_jitter(initial=10, max=120, jitter=5),
        stop=stop_after_attempt(5),  # overridden in _patch_retry
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch(self, url: str) -> str:
        """Navigate the reused tab to a URL and return the page HTML.

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
        if self._browser is None or self._tab is None:
            raise HLTVFetchError("Browser not started. Call start() first.", url=url)

        await self.rate_limiter.wait()
        self._request_count += 1

        try:
            # Navigate the existing tab (preserves Cloudflare cookies)
            await self._tab.get(url)
            await asyncio.sleep(self._config.page_load_wait)

            # Check for Cloudflare challenge via page title
            title = await self._tab.evaluate("document.title")

            if any(sig in title for sig in _CHALLENGE_TITLES):
                # Poll until challenge clears on this same tab (up to 30s)
                logger.info("Challenge detected on %s — waiting for auto-solve...", url)
                elapsed = 0.0
                while elapsed < self._config.challenge_wait:
                    await asyncio.sleep(_POLL_INTERVAL)
                    elapsed += _POLL_INTERVAL
                    title = await self._tab.evaluate("document.title")
                    if not any(sig in title for sig in _CHALLENGE_TITLES):
                        logger.info("Challenge cleared after %.1fs", elapsed)
                        break
                else:
                    # Still challenged after full wait
                    self._challenge_count += 1
                    self.rate_limiter.backoff()
                    raise CloudflareChallenge(
                        f"Cloudflare challenge on {url} (title: {title!r})",
                        url=url,
                    )

            # Extract full HTML — retry extraction if page hasn't loaded yet
            html = await self._tab.evaluate(
                "document.documentElement.outerHTML"
            )

            if not html or len(html) < 10000:
                # Page may still be loading; wait and retry extraction
                await asyncio.sleep(self._config.page_load_wait)
                html = await self._tab.evaluate(
                    "document.documentElement.outerHTML"
                )

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

    async def fetch_many(self, urls: list[str]) -> list[str | Exception]:
        """Fetch multiple URLs sequentially using the reused tab.

        Each URL is fetched via fetch() which navigates the same
        browser tab. Failures are captured per-URL without aborting
        the rest.

        Args:
            urls: List of full URLs to fetch.

        Returns:
            List of results in the same order as urls. Each element is
            either the HTML string on success or the Exception on failure.
        """
        results: list[str | Exception] = []
        for url in urls:
            try:
                html = await self.fetch(url)
                results.append(html)
            except Exception as exc:
                results.append(exc)
        return results

    async def close(self) -> None:
        """Stop the Chrome browser."""
        if self._browser:
            self._browser.stop()
            self._browser = None
            self._tab = None

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
