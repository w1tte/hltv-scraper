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
import time
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

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
from scraper.proxy_health import ProxyHealthTracker
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
               '.match-info-row','.stats-table',
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

    def __init__(
        self,
        config: ScraperConfig | None = None,
        proxy_url: str | None = None,
        proxy_urls: list[str] | None = None,
        forwarder_port: int = 18080,
    ):
        if config is None:
            config = ScraperConfig()

        self._config = config
        # Proxy rotation: cycle through the list on each start()/restart().
        # If proxy_urls is provided, proxy_url is ignored.
        self._proxy_urls = proxy_urls or ([proxy_url] if proxy_url else [])
        self._proxy_index = 0
        self._apply_proxy(self._proxy_urls[0] if self._proxy_urls else None)
        # Health-based proxy selection (replaces blind round-robin)
        self._proxy_health = ProxyHealthTracker(self._proxy_urls) if self._proxy_urls else None
        self.rate_limiter = RateLimiter(config)  # kept for global backoff/stats
        self._tab_rate_limiters: dict[int, RateLimiter] = {}  # per-tab, keyed by id(tab)
        self._browser: nodriver.Browser | None = None
        self._tabs: list = []
        self._tab_pool: asyncio.Queue | None = None
        # Serialise CDP Page.navigate calls across tabs (~50-200ms hold).
        # Prevents CDP response-routing confusion on the shared WebSocket
        # when two tabs send navigation requests within milliseconds.
        # With a single tab, no lock is needed (use a no-op context manager).
        self._nav_lock: asyncio.Lock | None = None  # set in start() based on tab count

        # Request counters
        self._request_count = 0
        self._success_count = 0
        self._challenge_count = 0
        self._proxy_forwarder = None
        self._forwarder_port = forwarder_port  # unique per worker

        # Track last successful CDP evaluate for unresponsiveness detection
        self._last_eval_ok: float = time.monotonic()

        # Override tenacity stop condition with config value
        self._patch_retry()

    @property
    def _tab(self):
        """First tab, for backward compatibility."""
        return self._tabs[0] if self._tabs else None

    @property
    def is_healthy(self) -> bool:
        """Check if the browser process is still alive and responsive.

        Returns False if the Chrome process exited OR if no CDP evaluate
        has succeeded within 2× evaluate_timeout (zombie process detection).
        """
        if self._browser is None:
            return False
        proc = getattr(self._browser, "_process", None)
        if proc is None or proc.returncode is not None:
            return False
        stale = time.monotonic() - self._last_eval_ok
        if stale > self._config.navigation_timeout * 2 + 5:
            logger.warning("Browser unresponsive: no eval success in %.0fs", stale)
            return False
        return True

    def _apply_proxy(self, proxy_url: str | None) -> None:
        """Set the active proxy URL, parsing credentials."""
        self._proxy_url, self._proxy_user, self._proxy_pass = self._parse_proxy(proxy_url)

    def _rotate_proxy(self) -> None:
        """Select the best proxy based on health scoring.

        Uses ProxyHealthTracker to pick the proxy with the lowest
        average latency among non-blacklisted candidates, falling
        back to round-robin if no health tracker is available.
        """
        if not self._proxy_urls:
            return
        if self._proxy_health:
            best = self._proxy_health.select_best_proxy(self._proxy_url)
            if best and best in self._proxy_urls:
                self._proxy_index = self._proxy_urls.index(best)
                self._apply_proxy(best)
                logger.info("Rotated to best proxy %d/%d: %s",
                             self._proxy_index + 1, len(self._proxy_urls),
                             self._proxy_url)
                return
        # Fallback: round-robin
        self._proxy_index = (self._proxy_index + 1) % len(self._proxy_urls)
        self._apply_proxy(self._proxy_urls[self._proxy_index])
        logger.info("Rotated to proxy %d/%d: %s",
                     self._proxy_index + 1, len(self._proxy_urls),
                     self._proxy_url)

    async def restart(self) -> None:
        """Close and re-start the browser with the next proxy.

        Rotates to a fresh proxy IP on each restart to distribute
        load and avoid Cloudflare IP-level throttling.

        Retries up to 3 times with aggressive Chrome cleanup between
        attempts to recover from zombie processes or stale temp dirs.
        """
        self._rotate_proxy()
        logger.warning("Restarting browser (proxy rotation)...")
        await self.close()
        self._nav_lock = None  # set in start() based on tab count
        self._last_eval_ok = time.monotonic()  # reset staleness timer
        # Reset rate limiters — the old proxy was throttled, new one is fresh
        self.rate_limiter = RateLimiter(self._config)
        self._tab_rate_limiters.clear()

        last_exc = None
        for attempt in range(3):
            try:
                await self.start()
                logger.info("Browser restarted successfully")
                return
            except Exception as exc:
                last_exc = exc
                logger.warning("Restart attempt %d/3 failed: %s", attempt + 1, exc)
                if attempt < 2:
                    await self._kill_stale_chrome()
                    await asyncio.sleep(2.0 * (attempt + 1))
        raise HLTVFetchError(
            f"Browser restart failed after 3 attempts: {last_exc}", url=""
        )

    async def _kill_stale_chrome(self) -> None:
        """Kill orphaned Chrome processes from this client and clean temp dirs.

        Called between restart attempts when nodriver.start() fails.
        Only kills Chrome processes that belong to this client's last
        known PID tree — safe with multiple workers in the same container.
        """
        try:
            import psutil
            # Kill any chrome processes whose parent is PID 1 (orphans) or
            # that match our last known browser PID
            for proc in psutil.process_iter(["pid", "name", "ppid"]):
                try:
                    name = proc.info.get("name", "") or ""
                    if "chrome" not in name.lower():
                        continue
                    ppid = proc.info.get("ppid", -1)
                    # Orphaned (parent is init/PID 1) or zombie
                    if ppid in (0, 1):
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except ImportError:
            # psutil not available — fall back to pkill (less safe but
            # better than a completely stuck browser)
            import subprocess
            try:
                subprocess.run(
                    ["pkill", "-9", "-f", "chrome"],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
        except Exception:
            pass
        await asyncio.sleep(0.5)

    @staticmethod
    def _parse_proxy(proxy_url: str | None) -> tuple[str | None, str | None, str | None]:
        """Parse proxy URL, extracting credentials if present.

        Supports: socks5://user:pass@host:port, http://user:pass@host:port
        Returns: (url_without_auth, username, password)
        """
        if not proxy_url:
            return None, None, None
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)
        if parsed.username:
            # Rebuild URL without credentials
            netloc = parsed.hostname
            if parsed.port:
                netloc += f":{parsed.port}"
            clean_url = f"{parsed.scheme}://{netloc}"
            return clean_url, parsed.username, parsed.password
        return proxy_url, None, None

    async def _start_proxy_forwarder(self, proxy_url: str, port: int) -> None:
        """Start a local proxy forwarder for transparent auth.

        Chrome connects to 127.0.0.1:{port} (no auth), the forwarder
        handles upstream proxy auth via Proxy-Authorization header.
        """
        from scraper.proxy_forwarder import ProxyForwarder
        if self._proxy_forwarder:
            await self._proxy_forwarder.stop()
        self._proxy_forwarder = ProxyForwarder(proxy_url, port)
        await self._proxy_forwarder.start()

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
            # Prevent Chrome from throttling background/occluded windows
            # (needed for Turnstile clicks and JS rendering when not focused)
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
            # Enable software GL so canvas fingerprint isn't empty/wrong
            "--use-gl=swiftshader",
            "--enable-gpu-rasterization",
            "--ignore-gpu-blocklist",
        ]
        if self._proxy_url:
            if self._proxy_user:
                # Use local forwarder for transparent proxy auth.
                # Chrome connects to 127.0.0.1 (no auth), forwarder
                # handles upstream auth — avoids CDP Fetch and extension issues.
                original_proxy = (
                    f"{urlparse(self._proxy_url).scheme}://"
                    f"{self._proxy_user}:{self._proxy_pass}@"
                    f"{urlparse(self._proxy_url).hostname}:{urlparse(self._proxy_url).port}"
                )
                await self._start_proxy_forwarder(original_proxy, self._forwarder_port)
                browser_args.append(f"--proxy-server=http://127.0.0.1:{self._forwarder_port}")
            else:
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

        _warmup_eval_timeout = 15.0  # longer timeout during warmup (proxy still connecting)
        elapsed = 0.0
        while elapsed < _WARMUP_TIMEOUT:
            title = await self._safe_evaluate(first_tab, "document.title", timeout=_warmup_eval_timeout)
            if not isinstance(title, str):
                title = ""
            body_text = await self._safe_evaluate(
                first_tab, "document.body ? document.body.innerText : ''",
                timeout=_warmup_eval_timeout,
            )
            if not isinstance(body_text, str):
                body_text = ""
            is_chrome_error = await self._safe_evaluate(
                first_tab,
                "document.getElementById('main-frame-error') !== null",
                timeout=_warmup_eval_timeout,
            )
            if (
                is_chrome_error is True
                or "This site can't be reached" in body_text
                or "ERR_" in body_text
                or "Access denied" in title
                or "error code: 1005" in body_text
                or "error code: 1006" in body_text
                or "error code: 1007" in body_text
            ):
                import re as _re
                codes = _re.findall(r"ERR_[A-Z_]+", body_text)
                code = codes[0] if codes else "ERR_UNKNOWN"
                raise HLTVFetchError(
                    f"Proxy/network error during warmup ({code}): {body_text[:200]}",
                    url=warmup_url,
                )
            if not any(sig in title for sig in _CHALLENGE_TITLES):
                if not title or "hltv" not in title.lower():
                    logger.debug(
                        "Warmup page has no HLTV title (%r) after %.1fs — waiting...",
                        title, elapsed + self._config.page_load_wait,
                    )
                    await asyncio.sleep(_POLL_INTERVAL)
                    elapsed += _POLL_INTERVAL
                    continue
                logger.info(
                    "Cloudflare cleared after %.1fs (title: %r)",
                    elapsed + self._config.page_load_wait, title,
                )
                await self._dismiss_consent(first_tab)
                await asyncio.sleep(0.5)
                break
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
                logger.debug("Clicked Turnstile checkbox at (216,337)")
                _click_failures = 0
                await asyncio.sleep(3.0)
            except Exception as click_exc:
                _click_failures = getattr(self, "_warmup_click_failures", 0) + 1
                self._warmup_click_failures = _click_failures
                logger.debug("Turnstile click failed (%d): %s", _click_failures, click_exc)
                if _click_failures >= 5:
                    logger.warning("Turnstile click failed %d times — CDP may be broken", _click_failures)
                    break
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
        else:
            logger.warning(
                "Cloudflare challenge did not clear after %ds warm-up. "
                "Proceeding anyway — fetches may retry.",
                _WARMUP_TIMEOUT,
            )

        # NOTE: Resource blocking (images/fonts/tracking) was tested but HLTV's
        # map_stats pages depend on resource load events to populate DOM elements
        # like .match-info-box and .stats-table. Blocking images caused 69/100
        # maps to fail targeted extraction. Disabled for correctness.

        # Build the tab pool
        num_tabs = self._config.concurrent_tabs
        # Nav lock only needed with multiple tabs sharing one WebSocket
        self._nav_lock = asyncio.Lock() if num_tabs > 1 else None
        self._tabs = [first_tab]
        self._tab_pool = asyncio.Queue()
        self._tab_pool.put_nowait(first_tab)
        self._tab_rate_limiters[id(first_tab)] = RateLimiter(self._config)

        # Additional tabs share the browser's cookie jar (CF clearance)
        # and proxy auth session — no need for Fetch domain setup.
        for i in range(1, num_tabs):
            tab = await self._browser.get(warmup_url)
            await asyncio.sleep(0.2)
            self._tabs.append(tab)
            self._tab_pool.put_nowait(tab)
            self._tab_rate_limiters[id(tab)] = RateLimiter(self._config)

        if num_tabs > 1:
            logger.info("Browser ready with %d tabs (per-tab rate limiters)", num_tabs)

    async def _dismiss_consent(self, tab) -> bool:
        """Click Cookiebot 'Allow All' if the consent dialog is visible.

        Returns True if consent was dismissed, False if not present.
        """
        try:
            clicked = await asyncio.wait_for(
                tab.evaluate(
                    "(() => {"
                    "  const btn = document.getElementById("
                    "    'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll'"
                    "  );"
                    "  if (btn && btn.offsetParent !== null) {"
                    "    btn.click(); return true;"
                    "  }"
                    "  return false;"
                    "})()"
                ),
                timeout=3.0,
            )
            if clicked is True:
                logger.info("Dismissed Cookiebot consent dialog")
                await asyncio.sleep(1.0)  # let overlay disappear
                return True
        except Exception:
            pass
        return False

    async def _safe_evaluate(self, tab, js: str, timeout: float | None = None):
        """Wrap tab.evaluate() with asyncio.wait_for to prevent indefinite hangs.

        If CDP drops a response, this times out instead of waiting forever.
        Records last successful eval time for unresponsiveness detection.
        """
        if timeout is None:
            timeout = self._config.evaluate_timeout
        try:
            result = await asyncio.wait_for(tab.evaluate(js), timeout=timeout)
            self._last_eval_ok = time.monotonic()
            return result
        except asyncio.TimeoutError:
            # Timeout means CDP didn't respond in time, but the browser
            # process is likely still alive — update health timestamp.
            self._last_eval_ok = time.monotonic()
            raise HLTVFetchError(
                f"CDP evaluate timed out after {timeout}s", url=""
            )

    async def _fetch_with_tab(
        self, tab, url: str,
        content_marker: str | None = None,
        ready_selector: str | None = None,
        page_type: str | None = None,
        stable_selector: bool = False,
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
        _t0 = time.monotonic()

        try:
            # Capture pre-navigation content fingerprint for stale DOM
            # detection.  After navigation, if readyState never dropped to
            # 'loading', we verify content changed — identical content
            # means the old DOM is still showing.
            _pre_nav_fp = None
            try:
                _pre_nav_fp = await self._safe_evaluate(
                    tab,
                    "document.body ? document.body.innerText.slice(200, 600) : ''",
                    timeout=2.0,
                )
                if not isinstance(_pre_nav_fp, str) or len(_pre_nav_fp) < 30:
                    _pre_nav_fp = None
            except Exception:
                pass

            # Navigate with a minimal post-nav sleep.  The two-phase
            # readyState detection below handles actual DOM readiness;
            # this just avoids racing the very first CDP eval.
            _orig_sleep = tab.sleep
            tab.sleep = lambda t=0.05: _orig_sleep(0.05)
            try:
                # Nav lock serialises CDP Page.navigate across tabs (multi-tab only)
                nav_coro = asyncio.wait_for(
                    tab.get(url),
                    timeout=self._config.navigation_timeout,
                )
                if self._nav_lock is not None:
                    async with self._nav_lock:
                        await nav_coro
                else:
                    await nav_coro
            except asyncio.TimeoutError:
                # Nav timeout — page didn't load but browser is alive.
                # Update health timestamp so retry loop doesn't trigger
                # false "unresponsive" restarts.
                self._last_eval_ok = time.monotonic()
                tab_rl.backoff()
                self.rate_limiter.backoff()
                if self._proxy_health and self._proxy_url:
                    self._proxy_health.record_failure(self._proxy_url)
                raise HLTVFetchError(
                    f"Navigation timed out after {self._config.navigation_timeout}s for {url}",
                    url=url,
                )
            finally:
                tab.sleep = _orig_sleep
            _t_nav = time.monotonic()

            # Check for Cloudflare challenge via page title
            # nodriver may return ExceptionDetails instead of str on error
            title = await self._safe_evaluate(tab, "document.title")
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
                    except Exception as click_exc:
                        logger.debug("Turnstile click failed during challenge: %s", click_exc)
                    await asyncio.sleep(_POLL_INTERVAL)
                    elapsed += _POLL_INTERVAL
                    title = await self._safe_evaluate(tab, "document.title")
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

            # Wait for the new page DOM to replace the old one.
            #
            # Problem: after tab.get(url), the URL updates immediately but
            # the old DOM can persist briefly.  readyState stays 'complete'
            # from the old page, so checking URL+readyState=='complete' can
            # pass before the new page actually loads.
            #
            # Solution: first wait for readyState to drop to 'loading' or
            # 'interactive' (proving the old DOM was torn down), then wait
            # for 'complete' (new page fully loaded).
            expected_path = urlparse(url).path
            saw_loading = False
            _phase1_deadline = time.monotonic() + 2.0  # 2s wall-clock max
            while time.monotonic() < _phase1_deadline:
                try:
                    result = await self._safe_evaluate(
                        tab,
                        "document.location.pathname + '|' + document.readyState",
                        timeout=2.0,
                    )
                    if isinstance(result, str) and "|" in result:
                        path, state = result.rsplit("|", 1)
                        if state in ("loading", "interactive"):
                            saw_loading = True
                            break
                except Exception:
                    # CDP busy — likely mid-navigation, which is what we want
                    saw_loading = True
                    break
                await asyncio.sleep(0.1)

            # Now wait for readyState to reach 'complete' (new page loaded)
            settled = False
            _phase2_deadline = time.monotonic() + 5.0  # 5s wall-clock max
            while time.monotonic() < _phase2_deadline:
                try:
                    result = await self._safe_evaluate(
                        tab,
                        "document.location.pathname + '|' + document.readyState",
                        timeout=3.0,
                    )
                    if isinstance(result, str) and "|" in result:
                        path, state = result.rsplit("|", 1)
                        if path == expected_path and state == "complete":
                            settled = True
                            break
                except Exception:
                    pass
                await asyncio.sleep(0.2)
            if not settled:
                logger.debug("Page load not confirmed for %s (saw_loading=%s)", url, saw_loading)

            # When readyState never dropped to 'loading', the old DOM may
            # still be showing.  Verify via content fingerprint — if the
            # page text hasn't changed, wait up to 3s for the real load.
            if _pre_nav_fp and not saw_loading:
                _fp_deadline = time.monotonic() + 2.0  # 2s wall-clock max
                _fp_matched = False
                while time.monotonic() < _fp_deadline:
                    try:
                        _post_fp = await self._safe_evaluate(
                            tab,
                            "document.body ? document.body.innerText.slice(200, 600) : ''",
                            timeout=2.0,
                        )
                        if isinstance(_post_fp, str) and _post_fp != _pre_nav_fp:
                            _fp_matched = True
                            break
                    except Exception:
                        _fp_matched = True  # CDP error — likely mid-navigation
                        break
                    await asyncio.sleep(0.2)
                if not _fp_matched:
                    # Content identical after 3s — definitely stale DOM
                    raise HLTVFetchError(
                        f"Stale DOM: content unchanged after navigation to {url}",
                        url=url,
                    )

            # Wait for ready_selector in the live DOM before extracting HTML
            _t_sel = time.monotonic()
            if ready_selector:
                await self._wait_for_selector(tab, url, ready_selector, stable=stable_selector, page_type=page_type)
                # Minimal settle — selector match means DOM is ready
                await asyncio.sleep(0.02)

            # For map_stats pages, also wait for round-history images to render.
            # These load after the stats table and were being missed with only
            # a 20ms settle.  Use stable=True so the image count must stabilize
            # (same on two consecutive polls), ensuring all rounds are loaded.
            # Non-fatal: forfeits may not have round history.
            if page_type == "map_stats":
                try:
                    await self._wait_for_selector(
                        tab, url,
                        ".round-history-con img.round-history-outcome",
                        timeout=6.0,
                        stable=True,
                        dump_on_fail=False,
                    )
                    await asyncio.sleep(0.05)
                except Exception:
                    logger.debug("No round-history found for %s (forfeit?)", url)
            _t_sel_done = time.monotonic()

            # Extract HTML — targeted for known page types, full page otherwise.
            # Targeted extraction cuts CDP transfer from ~5 MB to ~50–100 KB.
            extractor_js = _JS_EXTRACTORS.get(page_type or "")
            _min_size = 200 if extractor_js else 10000

            _t_ext = time.monotonic()
            _t_lock = _t_ext  # no lock wait
            if extractor_js:
                html = await self._safe_evaluate(tab, extractor_js)
            else:
                html = await self._safe_evaluate(tab, "document.documentElement.outerHTML")
            _t_ext_done = time.monotonic()
            if not isinstance(html, str):
                html = ""

            if len(html) < _min_size and extractor_js:
                # Targeted extraction returned too little — retry once
                logger.debug("Short extraction: %d chars for %s", len(html), url)
                await asyncio.sleep(0.5)
                html = await self._safe_evaluate(tab, extractor_js)
                if not isinstance(html, str):
                    html = ""
                if len(html) < _min_size:
                    # Extractor still empty despite ready_selector match.
                    # Page state likely changed (CF re-challenge or DOM mutation).
                    # Raise error so tenacity retries the full navigation.
                    raise HLTVFetchError(
                        f"Targeted extraction empty for {url} ({len(html)} chars) "
                        f"— page state changed after selector matched",
                        url=url,
                    )
            elif len(html) < _min_size:
                await asyncio.sleep(self._config.page_load_wait)
                html = await self._safe_evaluate(tab, "document.documentElement.outerHTML")
                if not isinstance(html, str):
                    html = ""

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
                    html = await self._safe_evaluate(tab, extractor_js)
                else:
                    html = await self._safe_evaluate(tab, "document.documentElement.outerHTML")
                if not isinstance(html, str):
                    html = ""

                if content_marker not in html:
                    await asyncio.sleep(self._config.page_load_wait * 2)
                    if extractor_js:
                        html = await self._safe_evaluate(tab, extractor_js)
                    else:
                        html = await self._safe_evaluate(tab, "document.documentElement.outerHTML")
                    if not isinstance(html, str):
                        html = ""

                if content_marker not in html:
                    raise HLTVFetchError(
                        f"Content marker {content_marker!r} not found on {url} "
                        f"after retries ({len(html)} chars)",
                        url=url,
                    )

        except CloudflareChallenge:
            if self._proxy_health and self._proxy_url:
                self._proxy_health.record_failure(self._proxy_url)
            raise
        except HLTVFetchError:
            if self._proxy_health and self._proxy_url:
                self._proxy_health.record_failure(self._proxy_url)
            raise
        except ValueError:
            # Raised by _wait_for_selector when page is loaded but element
            # genuinely missing (no data).  Don't wrap in HLTVFetchError —
            # that would trigger tenacity retries on a permanent condition.
            # Not a proxy issue — don't record as failure.
            raise
        except Exception as exc:
            if self._proxy_health and self._proxy_url:
                self._proxy_health.record_failure(self._proxy_url)
            raise HLTVFetchError(
                f"Failed to fetch {url}: {exc}", url=url
            ) from exc

        # Success — recover this tab's rate limiter
        tab_rl.recover()
        self.rate_limiter.recover()
        self._success_count += 1
        _t_done = time.monotonic()
        # Record proxy health on success
        if self._proxy_health and self._proxy_url:
            self._proxy_health.record_success(self._proxy_url, _t_done - _t0)
        logger.debug(
            "TIMING %s nav=%.2fs sel=%.2fs lock=%.2fs ext=%.2fs total=%.2fs (%d chars)",
            url.split("/")[-2] if "/mapstatsid/" in url else url.split("/")[-1],
            _t_nav - _t0, _t_sel_done - _t_sel,
            _t_lock - _t_ext, _t_ext_done - _t_lock,
            _t_done - _t0, len(html),
        )
        return html

    async def _wait_for_selector(
        self, tab, url: str, selector: str, timeout: float = 5.0,
        stable: bool = False, dump_on_fail: bool = True,
        page_type: str | None = None,
    ) -> None:
        """Poll the live DOM until a CSS selector matches an element.

        When *stable* is True, waits for the element count to stabilise
        (same count on two consecutive polls) instead of returning on
        the first match.  Use this for listing pages where the DOM is
        populated incrementally (e.g. 100 result entries).

        Raises HLTVFetchError if the selector is not found within *timeout*.
        """
        # Stable mode needs more time: DOM count must match on two consecutive
        # polls, which requires all ~100 elements to finish rendering.
        # Docker/Xvfb environments render slower than native displays.
        if stable and timeout <= 5.0:
            timeout = 15.0
        count_js = f"document.querySelectorAll({selector!r}).length"
        # Use wall-clock deadline instead of accumulated sleep intervals,
        # because _safe_evaluate can take seconds when Chrome is slow.
        _sel_deadline = time.monotonic() + timeout
        # Start polling very fast — SSR pages usually have content by 30-80ms.
        # Back off after a few misses to avoid hammering CDP.
        interval = 0.03
        polls = 0
        prev_count = 0
        elapsed = 0.0  # kept for logging
        while time.monotonic() < _sel_deadline:
            count = await self._safe_evaluate(tab, count_js)
            if not isinstance(count, (int, float)):
                count = 0
            else:
                count = int(count)
            if count > 0:
                if not stable:
                    return
                # Stable mode: count must match previous poll
                if count == prev_count:
                    return
                prev_count = count
                # Once elements start appearing, poll at steady interval
                interval = 0.15
            await asyncio.sleep(interval)
            elapsed = timeout - (_sel_deadline - time.monotonic())
            polls += 1
            if polls >= 3:  # after ~90ms, slow to 0.15s
                interval = 0.15
            if polls >= 6:  # after ~540ms, slow to 0.4s
                interval = 0.4
        # Selector not found — try dismissing consent overlay first.
        # If consent was blocking, raise HLTVFetchError so tenacity retries
        # the full navigation — the consent cookie is now set so the next
        # load will show actual content instead of the consent overlay.
        if await self._dismiss_consent(tab):
            raise HLTVFetchError(
                f"Consent overlay dismissed on {url} — retrying navigation",
                url=url,
            )

        # Selector not found — dump page HTML for debugging
        if dump_on_fail:
            try:
                debug_html = await self._safe_evaluate(
                    tab, "document.documentElement.outerHTML"
                )
                if isinstance(debug_html, str):
                    from pathlib import Path
                    dump_path = Path("data") / "debug_selector_fail.html"
                    dump_path.parent.mkdir(parents=True, exist_ok=True)
                    dump_path.write_text(debug_html, encoding="utf-8")
                    # Also get body text and title for the log
                    body_text = await self._safe_evaluate(
                        tab, "document.body ? document.body.innerText.slice(0, 500) : '(no body)'"
                    )
                    page_title = await self._safe_evaluate(tab, "document.title")
                    logger.warning(
                        "Selector %r not found after %.1fs (%d polls, last count=%d). "
                        "HTML dumped to %s (%d bytes). Title: %r. Body text: %s",
                        selector, elapsed, polls, prev_count, dump_path,
                        len(debug_html), page_title,
                        body_text if isinstance(body_text, str) else "(unavailable)",
                    )
            except Exception:
                pass

        # Check if page actually finished loading.
        try:
            ready = await self._safe_evaluate(tab, "document.readyState === 'complete'")
        except Exception:
            ready = False

        if ready is True:
            # Page is loaded — but is it actually HLTV content?
            # A Cloudflare interstitial or error page can also have readyState 'complete'.
            # Only raise ValueError (non-retryable) if we're confident this is real HLTV content.
            try:
                is_hltv = await self._safe_evaluate(
                    tab,
                    "document.querySelector('.results') !== null "
                    "|| document.querySelector('.contentCol') !== null "
                    "|| document.querySelector('.navbar') !== null",
                )
            except Exception:
                is_hltv = False

            if is_hltv is True:
                # Stale DOM detection: check if DOM has elements from a
                # DIFFERENT page type (e.g. economy elements on a stats
                # page).  If so, the old DOM hasn't been torn down yet —
                # raise HLTVFetchError (retryable) instead of ValueError.
                if page_type:
                    _WRONG_PAGE = {
                        "map_stats": "[data-fusionchart-config]",
                        "map_performance": "[data-fusionchart-config]",
                        "map_economy": ".player-nick",
                        "overview": "[data-fusionchart-config]",
                    }
                    wrong_sel = _WRONG_PAGE.get(page_type)
                    if wrong_sel:
                        try:
                            wrong_count = await self._safe_evaluate(
                                tab,
                                f"document.querySelectorAll({wrong_sel!r}).length",
                            )
                            if isinstance(wrong_count, (int, float)) and int(wrong_count) > 0:
                                raise HLTVFetchError(
                                    f"Stale DOM on {url}: found {wrong_sel} from "
                                    f"previous page (expected {selector})",
                                    url=url,
                                )
                        except HLTVFetchError:
                            raise
                        except Exception:
                            pass
                raise ValueError(
                    f"Selector {selector!r} not found on loaded page {url} "
                    f"— data not available"
                )
            # Page loaded but doesn't look like HLTV — likely CF interstitial.
            # Raise HLTVFetchError to allow tenacity retry.
            logger.warning(
                "Page loaded but no HLTV markers found — likely Cloudflare interstitial. "
                "Retrying via HLTVFetchError."
            )

        raise HLTVFetchError(
            f"Ready selector {selector!r} not found on {url} "
            f"after {timeout:.0f}s",
            url=url,
        )

    @retry(
        retry=retry_if_exception_type((CloudflareChallenge, HLTVFetchError)),
        wait=wait_exponential_jitter(initial=1, max=8, jitter=1),
        stop=stop_after_attempt(4),  # overridden in _patch_retry
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch(
        self, url: str,
        content_marker: str | None = None,
        ready_selector: str | None = None,
        page_type: str | None = None,
        stable_selector: bool = False,
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
            stable_selector: If True, wait for the ready_selector element
                count to stabilise (same on two consecutive polls) before
                extracting HTML.  Use for listing pages.

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
                stable_selector=stable_selector,
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
        wait=wait_exponential_jitter(initial=1, max=8, jitter=1),
        stop=stop_after_attempt(4),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def fetch_with_tab(
        self, tab, url: str,
        content_marker: str | None = None,
        ready_selector: str | None = None,
        page_type: str | None = None,
        stable_selector: bool = False,
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
            stable_selector=stable_selector,
        )

    async def fetch_many(
        self, urls: list[str],
        content_marker: str | None = None,
        ready_selector: str | None = None,
        page_type: str | None = None,
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
            page_type: Optional page type for targeted extraction/wait logic.

        Returns:
            List of results in the same order as urls. Each element is
            either the HTML string on success or the Exception on failure.
        """
        async def _safe_fetch(url: str) -> str | Exception:
            try:
                return await self.fetch(url, content_marker=content_marker, ready_selector=ready_selector, page_type=page_type)
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

        # Stop proxy forwarder
        if self._proxy_forwarder:
            try:
                await self._proxy_forwarder.stop()
            except Exception:
                pass
            self._proxy_forwarder = None

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
        """Patch tenacity stop/wait to use config.max_retries."""
        self.fetch.retry.stop = stop_after_attempt(self._config.max_retries)
        self.fetch_with_tab.retry.stop = stop_after_attempt(self._config.max_retries)
        _wait = wait_exponential_jitter(initial=1, max=8, jitter=1)
        self.fetch.retry.wait = _wait
        self.fetch_with_tab.retry.wait = _wait


async def fetch_distributed(
    clients: list[HLTVClient], urls: list[str],
    content_marker: str | None = None,
    ready_selector: str | None = None,
    page_type: str | None = None,
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
        page_type: Optional page type for targeted extraction/wait logic.

    Returns:
        List of results in the same order as *urls*. Each element is
        either the HTML string on success or the Exception on failure.
    """
    if not clients:
        raise ValueError("fetch_distributed requires at least one client")
    if len(clients) == 1:
        return await clients[0].fetch_many(urls, content_marker=content_marker, ready_selector=ready_selector, page_type=page_type)

    n = len(clients)
    buckets: list[list[tuple[int, str]]] = [[] for _ in range(n)]
    for i, url in enumerate(urls):
        buckets[i % n].append((i, url))

    async def _fetch_bucket(
        client: HLTVClient, indexed_urls: list[tuple[int, str]]
    ) -> list[tuple[int, str | Exception]]:
        results = await client.fetch_many(
            [u for _, u in indexed_urls], content_marker=content_marker,
            ready_selector=ready_selector, page_type=page_type,
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
