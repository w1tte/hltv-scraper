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
from contextlib import asynccontextmanager
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

# Targeted DOM extractors per page type.
# Instead of dumping the full 5–12 MB outerHTML, extract only the elements
# each parser actually reads.  This cuts CDP transfer from ~5 s to ~0.05 s.
# Returns a minimal "<html><body>…</body></html>" string that parsers can
# consume identically to the full page — all parent/child relationships inside
# the extracted containers are preserved.
_JS_EXTRACTORS: dict[str, str] = {
    # Overview: extract only elements the match_parser actually selects.
    "overview": """(function(){
        var s=['.team1-gradient','.team2-gradient','.timeAndEvent',
               '.padding.preformatted-text','.mapholder','.veto-box',
               '.standard-headline'];
        var p=[];
        s.forEach(function(q){
            document.querySelectorAll(q).forEach(function(e){p.push(e.outerHTML);});
        });
        return p.length?'<html><body>'+p.join('')+'</body></html>':'';
    })()""",

    # Map stats: only what the parser actually selects:
    # - .match-info-box (map name, score)
    # - .team-left, .team-right (team names/IDs/scores — small elements)
    # - .match-info-row (half-score breakdown)
    # - .stats-table.totalstats (player scoreboard — 2 tables)
    # - .round-history-con (round timeline)
    # Deduplicated: elements already inside a captured parent are skipped.
    "map_stats": """(function(){
        var s=['.match-info-box','.team-left','.team-right',
               '.match-info-row','.stats-table.totalstats',
               '.totalstats','.round-history-con'];
        var seen=new Set();
        var p=[];
        s.forEach(function(q){
            document.querySelectorAll(q).forEach(function(e){
                if(seen.has(e))return;
                seen.add(e);
                p.push(e.outerHTML);
            });
        });
        return p.length?'<html><body>'+p.join('')+'</body></html>':'';
    })()""",

    # Performance: player stat cards + kill matrix + overview table.
    # Parser uses [data-fusionchart-config] and walks up to .standard-box parent.
    # We extract only .standard-box that contain a chart, plus killmatrix and overview.
    "map_performance": """(function(){
        var p=[], seen=new Set();
        document.querySelectorAll('[data-fusionchart-config]').forEach(function(el){
            var box=el.closest('.standard-box');
            var target=box||el;
            if(!seen.has(target)){seen.add(target);p.push(target.outerHTML);}
        });
        ['.killmatrix-content','.overview-table'].forEach(function(q){
            document.querySelectorAll(q).forEach(function(e){
                if(!seen.has(e)){seen.add(e);p.push(e.outerHTML);}
            });
        });
        return p.length?'<html><body>'+p.join('')+'</body></html>':'';
    })()""",

    # Economy: just the FusionChart config element (contains all round data)
    "map_economy": """(function(){
        var els=document.querySelectorAll('[data-fusionchart-config]');
        if(!els.length)return '';
        var p=[];
        els.forEach(function(e){p.push(e.outerHTML);});
        return '<html><body>'+p.join('')+'</body></html>';
    })()""",
}


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
        self.rate_limiter = RateLimiter(config)  # kept for global backoff/stats
        self._tab_rate_limiters: dict[int, RateLimiter] = {}  # per-tab, keyed by id(tab)
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

    @property
    def is_healthy(self) -> bool:
        """Check if the browser process is still alive."""
        if self._browser is None:
            return False
        proc = getattr(self._browser, "_process", None)
        return proc is not None and proc.returncode is None

    async def restart(self) -> None:
        """Close and re-start the browser (crash recovery).

        Preserves the same config/proxy. The caller should retry
        the failed match after calling this.
        """
        logger.warning("Restarting browser (crash recovery)...")
        await self.close()
        await self.start()
        logger.info("Browser restarted successfully")

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
            # Click the Turnstile "Verify you are human" checkbox via CDP mouse
            # events. The widget is inside a cross-origin iframe so JS can't
            # reach it, but physical input events dispatched at the correct
            # screen coordinates cross iframe boundaries natively.
            # Coordinates (216, 337) are the checkbox position in a 1280x900 window.
            try:
                from nodriver.cdp.input_ import dispatch_mouse_event, MouseButton
                await first_tab.send(dispatch_mouse_event(
                    "mousePressed", x=216, y=337,
                    button=MouseButton.LEFT, click_count=1,
                ))
                await asyncio.sleep(0.1)
                await first_tab.send(dispatch_mouse_event(
                    "mouseReleased", x=216, y=337,
                    button=MouseButton.LEFT, click_count=1,
                ))
                logger.debug("Clicked Turnstile checkbox at (216,337), waiting for verification...")
                await asyncio.sleep(3.0)
            except Exception:
                pass
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
        self._tab_rate_limiters[id(first_tab)] = RateLimiter(self._config)

        # Additional tabs share the browser's cookie jar (CF clearance)
        for i in range(1, num_tabs):
            tab = await self._browser.get(warmup_url)
            await asyncio.sleep(self._config.page_load_wait)
            self._tabs.append(tab)
            self._tab_pool.put_nowait(tab)
            self._tab_rate_limiters[id(tab)] = RateLimiter(self._config)

        if num_tabs > 1:
            logger.info("Browser ready with %d tabs (per-tab rate limiters)", num_tabs)

    async def _fetch_with_tab(
        self, tab, url: str,
        content_marker: str | None = None,
        ready_selector: str | None = None,
        page_type: str | None = None,
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
                before the page is considered loaded.
            page_type: If set and present in _JS_EXTRACTORS, runs a targeted
                JS expression to extract only the elements the parser needs
                (~50–100 KB) instead of the full 5–12 MB outerHTML.  This
                cuts CDP transfer time from ~5 s to ~0.05 s per fetch.
        """
        # Use per-tab rate limiter so concurrent tabs don't queue behind each other
        tab_rl = self._tab_rate_limiters.get(id(tab), self.rate_limiter)
        await tab_rl.wait()
        self._request_count += 1

        try:
            await tab.get(url)
            # When we have a ready_selector we'll poll the DOM for content,
            # so a short initial sleep (just enough for title to load) is fine.
            # Without a ready_selector, keep the full page_load_wait.
            initial_wait = 0.1 if ready_selector else self._config.page_load_wait
            await asyncio.sleep(initial_wait)

            # Check for Cloudflare challenge via page title
            # nodriver may return ExceptionDetails instead of str on error
            title = await tab.evaluate("document.title")
            if not isinstance(title, str):
                title = ""

            if any(sig in title for sig in _CHALLENGE_TITLES):
                # Poll until challenge clears — click the Turnstile checkbox each cycle
                logger.info("Challenge detected on %s — clicking Turnstile checkbox...", url)
                elapsed = 0.0
                while elapsed < self._config.challenge_wait:
                    # Click Turnstile checkbox via CDP (crosses cross-origin iframe)
                    try:
                        from nodriver.cdp.input_ import dispatch_mouse_event, MouseButton
                        await tab.send(dispatch_mouse_event(
                            "mousePressed", x=216, y=337,
                            button=MouseButton.LEFT, click_count=1,
                        ))
                        await asyncio.sleep(0.1)
                        await tab.send(dispatch_mouse_event(
                            "mouseReleased", x=216, y=337,
                            button=MouseButton.LEFT, click_count=1,
                        ))
                    except Exception:
                        pass
                    await asyncio.sleep(_POLL_INTERVAL)
                    elapsed += _POLL_INTERVAL
                    title = await tab.evaluate("document.title")
                    if not isinstance(title, str):
                        title = ""
                    if not any(sig in title for sig in _CHALLENGE_TITLES):
                        logger.info("Challenge cleared after %.1fs", elapsed)
                        break
                else:
                    # Still challenged after full wait — backoff this tab AND global
                    self._challenge_count += 1
                    tab_rl.backoff()
                    self.rate_limiter.backoff()
                    raise CloudflareChallenge(
                        f"Cloudflare challenge on {url} (title: {title!r})",
                        url=url,
                    )

            # Wait for ready_selector in the live DOM before extracting HTML
            if ready_selector:
                await self._wait_for_selector(tab, url, ready_selector)

            # Extract HTML — targeted for known page types, full page otherwise.
            # Targeted extraction cuts CDP transfer from ~5 MB to ~50–100 KB.
            extractor_js = _JS_EXTRACTORS.get(page_type or "")
            _min_size = 200 if extractor_js else 10000

            if extractor_js:
                html = await tab.evaluate(extractor_js)
            else:
                html = await tab.evaluate("document.documentElement.outerHTML")
            if not isinstance(html, str):
                html = ""

            if len(html) < _min_size:
                # Page still rendering — re-poll selector (if any) then retry.
                if ready_selector:
                    await self._wait_for_selector(tab, url, ready_selector)
                else:
                    await asyncio.sleep(self._config.page_load_wait)
                if extractor_js:
                    html = await tab.evaluate(extractor_js)
                if not isinstance(html, str):
                    html = ""
                # If targeted extraction still empty, fall back to full page.
                # Some matches have different DOM structures.
                if len(html) < _min_size and extractor_js:
                    logger.debug("Targeted extraction empty for %s — falling back to full page", url)
                    html = await tab.evaluate("document.documentElement.outerHTML")
                    if not isinstance(html, str):
                        html = ""
                    _min_size = 10000  # use full-page threshold for size check

            # Detect Cloudflare IP block (error 1005/1006/1007 — Access Denied)
            # These pages pass the size check but are useless — treat as CF challenge
            if html and "Access denied" in title and "cloudflare" in html.lower():
                self._challenge_count += 1
                tab_rl.backoff()
                self.rate_limiter.backoff()
                raise CloudflareChallenge(
                    f"Cloudflare IP block (Access Denied) on {url} — datacenter proxy blocked",
                    url=url,
                )

            # Fallback: detect Cloudflare challenge by HTML content
            # (catches localized titles not in _CHALLENGE_TITLES)
            if html and "/cdn-cgi/challenge-platform/" in html and "cf-turnstile-response" in html:
                self._challenge_count += 1
                tab_rl.backoff()
                self.rate_limiter.backoff()
                raise CloudflareChallenge(
                    f"Cloudflare challenge detected in HTML on {url} (title: {title!r})",
                    url=url,
                )

            if len(html) < _min_size:
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
                if extractor_js:
                    html = await tab.evaluate(extractor_js)
                else:
                    html = await tab.evaluate("document.documentElement.outerHTML")
                if not isinstance(html, str):
                    html = ""

                if content_marker not in html:
                    await asyncio.sleep(self._config.page_load_wait * 2)
                    if extractor_js:
                        html = await tab.evaluate(extractor_js)
                    else:
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
        except ValueError:
            # Raised by _wait_for_selector when page is loaded but element
            # genuinely missing (no data).  Don't wrap in HLTVFetchError —
            # that would trigger tenacity retries on a permanent condition.
            raise
        except Exception as exc:
            raise HLTVFetchError(
                f"Failed to fetch {url}: {exc}", url=url
            ) from exc

        # Success — recover this tab's rate limiter
        tab_rl.recover()
        self.rate_limiter.recover()
        self._success_count += 1
        logger.debug("Fetched %s (%d chars)", url, len(html))
        return html

    async def _wait_for_selector(
        self, tab, url: str, selector: str, timeout: float = 5.0,
    ) -> None:
        """Poll the live DOM until a CSS selector matches an element.

        Raises HLTVFetchError if the selector is not found within *timeout*.
        """
        js = f"!!document.querySelector({selector!r})"
        elapsed = 0.0
        # Start polling fast (0.1s), back off to 0.5s after first few misses.
        # JS-rendered content on a warm tab often appears within 100–200 ms.
        interval = 0.1
        polls = 0
        while elapsed < timeout:
            found = await tab.evaluate(js)
            if found is True:
                return
            await asyncio.sleep(interval)
            elapsed += interval
            polls += 1
            if polls >= 3:  # after 300 ms, slow down to 0.5 s intervals
                interval = 0.5
        # Selector not found — check if page actually finished loading.
        # If document.readyState is 'complete', the page is loaded but the
        # expected element simply isn't there (no data).  Raise ValueError
        # so tenacity does NOT retry and the pipeline logs it as a warning.
        # If the page is still loading, raise HLTVFetchError to trigger retry.
        try:
            ready = await tab.evaluate("document.readyState === 'complete'")
        except Exception:
            ready = False
        if ready is True:
            raise ValueError(
                f"Selector {selector!r} not found on loaded page {url} "
                f"— data not available"
            )
        raise HLTVFetchError(
            f"Ready selector {selector!r} not found on {url} "
            f"after {timeout:.0f}s",
            url=url,
        )

    @retry(
        retry=retry_if_exception_type((CloudflareChallenge, HLTVFetchError)),
        wait=wait_exponential_jitter(initial=1, max=15, jitter=1),
        stop=stop_after_attempt(5),  # overridden in _patch_retry
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch(
        self, url: str,
        content_marker: str | None = None,
        ready_selector: str | None = None,
        page_type: str | None = None,
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
            page_type: If set and a JS extractor exists for this type,
                extracts only the relevant DOM elements (~50–100 KB) instead
                of the full 5–12 MB page.  Drastically reduces CDP transfer.

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
                tab, url,
                content_marker=content_marker,
                ready_selector=ready_selector,
                page_type=page_type,
            )
        finally:
            self._tab_pool.put_nowait(tab)

    @asynccontextmanager
    async def pinned_tab(self):
        """Async context manager that pins a single tab for multiple fetches.

        Acquires one tab from the pool and holds it for the lifetime of the
        ``async with`` block.  Use this when a pipeline makes several
        sequential fetches that must not be interrupted by another pipeline
        grabbing the same tab mid-flight.

        Example::

            async with client.pinned_tab() as tab:
                stats_html = await client.fetch_with_tab(tab, stats_url, ...)
                perf_html  = await client.fetch_with_tab(tab, perf_url, ...)
                econ_html  = await client.fetch_with_tab(tab, econ_url, ...)
        """
        if self._browser is None or not self._tabs:
            raise HLTVFetchError("Browser not started. Call start() first.", url="")
        tab = await self._tab_pool.get()
        try:
            yield tab
        finally:
            self._tab_pool.put_nowait(tab)

    @retry(
        retry=retry_if_exception_type((CloudflareChallenge, HLTVFetchError)),
        wait=wait_exponential_jitter(initial=1, max=15, jitter=1),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch_with_tab(
        self, tab, url: str,
        content_marker: str | None = None,
        ready_selector: str | None = None,
        page_type: str | None = None,
    ) -> str:
        """Fetch a URL using a *specific* (already-acquired) tab.

        Use inside a ``pinned_tab()`` context to keep the same tab for a
        series of sequential fetches — prevents other pipelines from
        interleaving on the same tab.

        Has the same tenacity retry decorator as ``fetch()`` so transient
        CDP errors and Cloudflare challenges are retried automatically.
        """
        return await self._fetch_with_tab(
            tab, url,
            content_marker=content_marker,
            ready_selector=ready_selector,
            page_type=page_type,
        )

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
        """Stop Chrome, clean up temp profile dir, and kill orphan subprocesses.

        Uses nodriver's ``util.free()`` so the temp ``/tmp/uc_*`` profile dir
        is removed.  Then escalates from SIGTERM → SIGKILL for any surviving
        Chrome child processes to prevent accumulation across runs.
        """
        if not self._browser:
            return

        browser = self._browser
        self._browser = None
        self._tabs.clear()
        self._tab_pool = None

        # nodriver util.free(): stops browser + deletes /tmp/uc_* profile dir
        try:
            import nodriver.core.util as _nd_util
            task = _nd_util.free(browser)
            if task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=4.0)
                except (asyncio.TimeoutError, Exception):
                    pass
        except Exception:
            # Fall back to plain stop() if util.free() is unavailable
            try:
                browser.stop()
            except Exception:
                pass

        await asyncio.sleep(0.3)

        # Kill any surviving Chrome children of this browser's PID
        try:
            import signal as _signal
            import psutil
            _proc = getattr(browser, "_process", None)
            pid = _proc.pid if _proc is not None else None
            if pid:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        try:
                            child.send_signal(_signal.SIGKILL)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    # Also kill the parent if still alive
                    try:
                        parent.send_signal(_signal.SIGKILL)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                except psutil.NoSuchProcess:
                    pass  # Already dead — good
        except ImportError:
            pass  # psutil optional — best-effort only
        except Exception:
            pass

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
        self.fetch_with_tab.retry.stop = stop_after_attempt(self._config.max_retries)


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
