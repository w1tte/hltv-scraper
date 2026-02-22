"""HLTV HTTP client using nodriver for Cloudflare bypass.

Uses a real Chrome browser (off-screen window) to navigate HLTV pages,
solving Cloudflare challenges automatically. Integrates RateLimiter
for request pacing and tenacity for retry logic.

On start(), navigates to HLTV and waits for Cloudflare to clear, then
opens ``concurrent_tabs`` browser tabs (default 3). All tabs share the
same browser cookie jar so Cloudflare clearance persists across them.
``fetch_many()`` dispatches URLs across the tab pool concurrently via
``asyncio.gather()``, giving up to Nx throughput where N is the number
of tabs.

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

# Challenge page indicators in the page title (including localized variants)
_CHALLENGE_TITLES = (
    "Just a moment",       # English
    "Checking your browser",
    "Et øjeblik",          # Danish
    "Einen Moment",        # German
    "Un instant",          # French
    "Un momento",          # Spanish
    "Um momento",          # Portuguese
    "Een moment",          # Dutch
    "Un momento",          # Italian
    "Bir an",              # Turkish
    "Chwileczkę",          # Polish
    "Подождите",           # Russian
    "少々お待ちください",    # Japanese
    "请稍候",              # Chinese (Simplified)
)

# Warm-up: max seconds to wait for Cloudflare to clear on first visit
_WARMUP_TIMEOUT = 90
_POLL_INTERVAL = 2


class HLTVClient:
    """HTTP client for HLTV using nodriver (real Chrome) for Cloudflare bypass.

    Uses a single Chrome browser instance with an off-screen window and
    a pool of ``concurrent_tabs`` tabs. On start(), navigates to the HLTV
    homepage and waits for Cloudflare to clear, then opens additional tabs
    that share the browser's cookie jar.

    ``fetch()`` acquires a tab from the pool, navigates it, and returns it.
    ``fetch_many()`` dispatches all URLs concurrently via ``asyncio.gather()``,
    with the tab pool naturally limiting concurrency to N simultaneous fetches.

    Usage:
        async with HLTVClient() as client:
            html = await client.fetch("https://www.hltv.org/matches/12345/...")
            results = await client.fetch_many(["url1", "url2", "url3"])
    """

    def __init__(self, config: ScraperConfig | None = None, proxy_url: str | None = None):
        if config is None:
            config = ScraperConfig()

        self._config = config
        self._proxy_url = proxy_url
        self.rate_limiter = RateLimiter(config)
        self._browser: nodriver.Browser | None = None
        self._tabs: list = []
        self._tab_pool: asyncio.Queue | None = None

        # Request counters
        self._request_count = 0
        self._success_count = 0
        self._challenge_count = 0

        # Override tenacity stop condition with config value
        self._patch_retry()

    @property
    def _tab(self):
        """First tab, for backward compatibility."""
        return self._tabs[0] if self._tabs else None

    async def start(self) -> None:
        """Launch Chrome off-screen and warm up Cloudflare trust.

        Navigates to an HLTV results page and polls until the Cloudflare
        challenge clears (up to 30s). Then opens additional tabs (up to
        ``concurrent_tabs`` total) that share the browser's CF cookies.
        """
        browser_args = [
            # Place window inside the virtual display — off-screen coords leak via JS
            "--window-position=0,0",
            "--window-size=1280,900",
            # Anti-detection: remove navigator.webdriver and automation signals
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins",
            # Realistic browser environment
            "--lang=en-US,en",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            # Enable software GL so canvas fingerprint isn't empty/wrong
            "--use-gl=swiftshader",
            "--enable-gpu-rasterization",
            "--ignore-gpu-blocklist",
        ]
        if self._proxy_url:
            browser_args.append(f"--proxy-server={self._proxy_url}")
        self._browser = await nodriver.start(
            headless=False,
            browser_args=browser_args,
            no_sandbox=True,
        )

        # Warm-up: visit a results page with gameType to match real fetch URLs
        warmup_url = (
            f"{self._config.base_url}/results?offset=0"
            f"&gameType={self._config.game_type}"
        )
        logger.info("Warming up browser on %s ...", warmup_url)
        first_tab = await self._browser.get(warmup_url)
        await asyncio.sleep(self._config.page_load_wait)

        elapsed = 0.0
        while elapsed < _WARMUP_TIMEOUT:
            title = await first_tab.evaluate("document.title")
            if not isinstance(title, str):
                title = ""
            # Detect Chrome network error pages (ERR_NO_SUPPORTED_PROXIES, etc.)
            html_snippet = await first_tab.evaluate(
                "document.documentElement.outerHTML.slice(0, 4000)"
            )
            if not isinstance(html_snippet, str):
                html_snippet = ""
            if (
                'id="main-frame-error"' in html_snippet
                or "ERR_NO_SUPPORTED_PROXIES" in html_snippet
                or "Access denied" in title
                or "error code: 1005" in html_snippet
                or "error code: 1006" in html_snippet
                or "error code: 1007" in html_snippet
            ):
                import re as _re
                codes = _re.findall(r"ERR_[A-Z_]+", html_snippet)
                code = codes[0] if codes else "ERR_UNKNOWN"
                raise HLTVFetchError(
                    f"Proxy IP blocked or network error during warmup ({code}). "
                    "Datacenter proxy IPs are blocked by HLTV (CF-1005). Use residential proxies.",
                    url=warmup_url,
                )
            if not any(sig in title for sig in _CHALLENGE_TITLES):
                logger.info(
                    "Cloudflare cleared after %.1fs",
                    elapsed + self._config.page_load_wait,
                )
                # Let CF cookies settle before real fetches begin
                await asyncio.sleep(1.0)
                break
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
        else:
            logger.warning(
                "Cloudflare challenge did not clear after %ds warm-up. "
                "Proceeding anyway — fetches may retry.",
                _WARMUP_TIMEOUT,
            )

        # Build the tab pool
        num_tabs = self._config.concurrent_tabs
        self._tabs = [first_tab]
        self._tab_pool = asyncio.Queue()
        self._tab_pool.put_nowait(first_tab)

        # Additional tabs share the browser's cookie jar (CF clearance)
        for i in range(1, num_tabs):
            tab = await self._browser.get(warmup_url)
            await asyncio.sleep(self._config.page_load_wait)
            self._tabs.append(tab)
            self._tab_pool.put_nowait(tab)

        if num_tabs > 1:
            logger.info("Browser ready with %d tabs", num_tabs)

    async def _fetch_with_tab(
        self, tab, url: str,
        content_marker: str | None = None,
        ready_selector: str | None = None,
    ) -> str:
        """Navigate a specific tab to a URL and return the page HTML.

        Handles rate limiting, Cloudflare challenge detection/polling,
        and page content validation. Does NOT handle retries — the
        caller (``fetch()``) wraps this with tenacity.

        Args:
            tab: The browser tab to use.
            url: The full URL to fetch.
            content_marker: Optional string that must appear in the HTML text.
            ready_selector: Optional CSS selector that must exist in the DOM
                before the page is considered loaded.  Uses
                ``document.querySelector()`` to check the live DOM, which is
                more reliable than text-matching the serialised HTML.
        """
        await self.rate_limiter.wait()
        self._request_count += 1

        try:
            # Navigate the tab (preserves Cloudflare cookies)
            await tab.get(url)
            await asyncio.sleep(self._config.page_load_wait)

            # Check for Cloudflare challenge via page title
            # nodriver may return ExceptionDetails instead of str on error
            title = await tab.evaluate("document.title")
            if not isinstance(title, str):
                title = ""

            if any(sig in title for sig in _CHALLENGE_TITLES):
                # Poll until challenge clears on this same tab (up to 30s)
                logger.info("Challenge detected on %s — waiting for auto-solve...", url)
                elapsed = 0.0
                while elapsed < self._config.challenge_wait:
                    await asyncio.sleep(_POLL_INTERVAL)
                    elapsed += _POLL_INTERVAL
                    title = await tab.evaluate("document.title")
                    if not isinstance(title, str):
                        title = ""
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

            # Wait for ready_selector in the live DOM before extracting HTML
            if ready_selector:
                await self._wait_for_selector(tab, url, ready_selector)

            # Extract full HTML — retry extraction if page hasn't loaded yet
            # nodriver may return ExceptionDetails instead of str on error
            html = await tab.evaluate(
                "document.documentElement.outerHTML"
            )
            if not isinstance(html, str):
                html = ""

            if len(html) < 10000:
                # Page may still be loading; wait and retry extraction
                await asyncio.sleep(self._config.page_load_wait)
                html = await tab.evaluate(
                    "document.documentElement.outerHTML"
                )
                if not isinstance(html, str):
                    html = ""

            # Detect Cloudflare IP block (error 1005/1006/1007 — Access Denied)
            # These pages pass the size check but are useless — treat as CF challenge
            if html and "Access denied" in title and "cloudflare" in html.lower():
                self._challenge_count += 1
                self.rate_limiter.backoff()
                raise CloudflareChallenge(
                    f"Cloudflare IP block (Access Denied) on {url} — datacenter proxy blocked",
                    url=url,
                )

            # Fallback: detect Cloudflare challenge by HTML content
            # (catches localized titles not in _CHALLENGE_TITLES)
            if html and "/cdn-cgi/challenge-platform/" in html and "cf-turnstile-response" in html:
                self._challenge_count += 1
                self.rate_limiter.backoff()
                raise CloudflareChallenge(
                    f"Cloudflare challenge detected in HTML on {url} (title: {title!r})",
                    url=url,
                )

            if len(html) < 10000:
                raise HLTVFetchError(
                    f"Response too short from {url} ({len(html)} chars)",
                    url=url,
                )

            # Content marker check: verify page has expected dynamic content
            if content_marker and content_marker not in html:
                logger.debug(
                    "Content marker %r not found on %s, waiting for render...",
                    content_marker, url,
                )
                await asyncio.sleep(self._config.page_load_wait)
                html = await tab.evaluate("document.documentElement.outerHTML")
                if not isinstance(html, str):
                    html = ""

                if content_marker not in html:
                    await asyncio.sleep(self._config.page_load_wait * 2)
                    html = await tab.evaluate("document.documentElement.outerHTML")
                    if not isinstance(html, str):
                        html = ""

                if content_marker not in html:
                    raise HLTVFetchError(
                        f"Content marker {content_marker!r} not found on {url} "
                        f"after retries ({len(html)} chars)",
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

    async def _wait_for_selector(
        self, tab, url: str, selector: str, timeout: float = 15.0,
    ) -> None:
        """Poll the live DOM until a CSS selector matches an element.

        Raises HLTVFetchError if the selector is not found within *timeout*.
        """
        js = f"!!document.querySelector({selector!r})"
        elapsed = 0.0
        interval = 0.5
        while elapsed < timeout:
            found = await tab.evaluate(js)
            if found is True:
                return
            await asyncio.sleep(interval)
            elapsed += interval
        raise HLTVFetchError(
            f"Ready selector {selector!r} not found on {url} "
            f"after {timeout:.0f}s",
            url=url,
        )

    @retry(
        retry=retry_if_exception_type((CloudflareChallenge, HLTVFetchError)),
        wait=wait_exponential_jitter(initial=10, max=120, jitter=5),
        stop=stop_after_attempt(5),  # overridden in _patch_retry
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch(
        self, url: str,
        content_marker: str | None = None,
        ready_selector: str | None = None,
    ) -> str:
        """Fetch a URL using a tab from the pool.

        Acquires a tab, navigates it, and returns the tab to the pool.
        On CloudflareChallenge, tenacity retries with exponential backoff;
        the tab is returned to the pool between retries so other fetches
        can proceed.

        Args:
            url: The full URL to fetch.
            content_marker: Optional string that must appear in the HTML.
                If provided and not found after retries, raises HLTVFetchError.
            ready_selector: Optional CSS selector that must exist in the
                live DOM before the page is considered loaded.

        Returns:
            The page HTML as a string.

        Raises:
            CloudflareChallenge: If Cloudflare challenge persists after retries.
            HLTVFetchError: If the page content is empty or invalid.
        """
        if self._browser is None or not self._tabs:
            raise HLTVFetchError("Browser not started. Call start() first.", url=url)

        tab = await self._tab_pool.get()
        try:
            return await self._fetch_with_tab(
                tab, url, content_marker=content_marker, ready_selector=ready_selector,
            )
        finally:
            self._tab_pool.put_nowait(tab)

    async def fetch_many(
        self, urls: list[str],
        content_marker: str | None = None,
        ready_selector: str | None = None,
    ) -> list[str | Exception]:
        """Fetch multiple URLs concurrently using the tab pool.

        Dispatches all URLs via ``asyncio.gather()``. The tab pool
        naturally limits concurrency to ``concurrent_tabs`` simultaneous
        fetches. Failures are captured per-URL without aborting the rest.

        Args:
            urls: List of full URLs to fetch.
            content_marker: Optional string that must appear in each page's HTML.
            ready_selector: Optional CSS selector that must exist in the
                live DOM before each page is considered loaded.

        Returns:
            List of results in the same order as urls. Each element is
            either the HTML string on success or the Exception on failure.
        """
        async def _safe_fetch(url: str) -> str | Exception:
            try:
                return await self.fetch(url, content_marker=content_marker, ready_selector=ready_selector)
            except Exception as exc:
                return exc

        results = await asyncio.gather(*[_safe_fetch(url) for url in urls])
        return list(results)

    async def close(self) -> None:
        """Stop the Chrome browser and clean up subprocess transports."""
        if self._browser:
            try:
                self._browser.stop()
            except Exception:
                pass
            # Give the event loop a chance to process transport cleanup
            await asyncio.sleep(0.5)
            self._browser = None
            self._tabs.clear()
            self._tab_pool = None

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


async def fetch_distributed(
    clients: list[HLTVClient], urls: list[str],
    content_marker: str | None = None,
    ready_selector: str | None = None,
) -> list[str | Exception]:
    """Split URLs round-robin across clients, fetch in parallel, reassemble in order.

    When only one client is provided, delegates directly to ``client.fetch_many()``.
    With multiple clients, each gets a round-robin subset of URLs and fetches
    concurrently via ``asyncio.gather()``.

    Args:
        clients: List of started HLTVClient instances.
        urls: List of full URLs to fetch.
        content_marker: Optional string that must appear in each page's HTML.
        ready_selector: Optional CSS selector that must exist in the live DOM
            before each page is considered loaded.

    Returns:
        List of results in the same order as *urls*. Each element is
        either the HTML string on success or the Exception on failure.
    """
    if not clients:
        raise ValueError("fetch_distributed requires at least one client")
    if len(clients) == 1:
        return await clients[0].fetch_many(urls, content_marker=content_marker, ready_selector=ready_selector)

    n = len(clients)
    buckets: list[list[tuple[int, str]]] = [[] for _ in range(n)]
    for i, url in enumerate(urls):
        buckets[i % n].append((i, url))

    async def _fetch_bucket(
        client: HLTVClient, indexed_urls: list[tuple[int, str]]
    ) -> list[tuple[int, str | Exception]]:
        results = await client.fetch_many(
            [u for _, u in indexed_urls], content_marker=content_marker, ready_selector=ready_selector,
        )
        return [(idx, res) for (idx, _), res in zip(indexed_urls, results)]

    all_indexed = await asyncio.gather(*[
        _fetch_bucket(c, b) for c, b in zip(clients, buckets) if b
    ])

    out: list[str | Exception | None] = [None] * len(urls)
    for group in all_indexed:
        for idx, res in group:
            out[idx] = res
    return out
