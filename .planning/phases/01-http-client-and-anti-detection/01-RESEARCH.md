# Phase 1: HTTP Client and Anti-Detection - Research

**Researched:** 2026-02-14
**Domain:** HTTP transport, TLS fingerprint impersonation, Cloudflare bypass, rate limiting
**Confidence:** HIGH (stack), MEDIUM (HLTV-specific Cloudflare behavior)

## Summary

This research investigates the technical requirements for building a reliable HTTP transport layer that can fetch any HLTV page type without triggering Cloudflare blocks. The primary technology is curl_cffi 0.14 for TLS-fingerprint-safe HTTP requests, with tenacity for retry logic and a custom rate limiter for delay management. The research confirms that HLTV uses Cloudflare bot management with at least passive TLS fingerprint checking, and that the `/stats/matches/performance/mapstatsid/{id}/{slug}` page is confirmed harder to reach -- the Node.js HLTV API project explicitly fetches it as a separate request and community reports confirm it triggers Cloudflare "checking your browser" challenges.

The critical finding is that curl_cffi may or may not suffice for all HLTV page types. It handles passive TLS fingerprinting well (impersonating Chrome/Safari JA3 fingerprints), but Cloudflare also checks IP reputation, request behavioral patterns, and may run JavaScript challenges on certain pages. The performance page is the litmus test. If curl_cffi fails on it, the fallback is SeleniumBase UC Mode. The architecture MUST be designed so the fetching strategy is swappable without touching any other code.

**Primary recommendation:** Start with curl_cffi impersonating `chrome136` (latest available target). Use a single Session per scraping run to maintain cookies and connections. Implement a custom rate limiter with 3-8 second random delays. Use tenacity for exponential backoff on retries. Detect Cloudflare challenges by checking for the `cf-mitigated: challenge` response header and/or HTML signatures. Test against all 5 HLTV page types in the integration test, with the performance page as the pass/fail gate.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| curl_cffi | 0.14.0 | HTTP client with TLS fingerprint impersonation | Impersonates real browser JA3/TLS/HTTP2 fingerprints. Bypasses Cloudflare passive detection without a browser. ~50ms per request vs ~2-5s for browser automation. requests-like API. Built-in RetryStrategy and cookie persistence. Supports both sync and async. |
| tenacity | 9.1.4 | Retry logic with exponential backoff and jitter | Declarative retry decorator. Supports custom retry conditions (retry on specific HTTP status codes), custom wait strategies (exponential with jitter, respect Retry-After header), and stop conditions. Well-maintained (Feb 2026 release). |
| fake-useragent | 2.2.0 | User-Agent string generation | Real-world UA database. Filter by browser, platform, minimum version. Generates realistic, current UA strings. Less critical when curl_cffi impersonates browsers, but needed for the User-Agent header value itself. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| seleniumbase | 4.46.5 | Fallback browser automation (UC Mode) | When curl_cffi gets Cloudflare Turnstile challenges (403 with `cf-mitigated: challenge`). Launches real undetectable Chrome. Only needed if empirical testing shows curl_cffi fails on specific page types. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| curl_cffi | nodriver (async Chrome automation) | Slower (~2-5s/request), but handles JS challenges natively. Use only if curl_cffi fails. nodriver last released Nov 2025, less active maintenance. |
| curl_cffi | Playwright + stealth | puppeteer-extra-stealth deprecated Feb 2025. Playwright detected by Cloudflare without patching. Not recommended. |
| tenacity | curl_cffi built-in RetryStrategy | curl_cffi has `RetryStrategy(count, delay, jitter, backoff)` but it operates at transport level (retries on connection errors), not at HTTP status code level. Cannot retry selectively on 403/429/503. Use tenacity for application-level retry logic on top of curl_cffi. |
| fake-useragent | Hardcoded UA list | Works but requires manual updates. fake-useragent auto-updates from real-world data. |

**Installation:**

```bash
pip install curl_cffi==0.14.0 tenacity==9.1.4 fake-useragent==2.2.0
# Only if curl_cffi proves insufficient for performance page:
pip install seleniumbase==4.46.5
```

## Architecture Patterns

### Recommended Project Structure

```
src/
  scraper/
    __init__.py
    config.py           # All configurable values (delays, retries, UA settings)
    http_client.py       # HLTVClient class wrapping curl_cffi Session
    rate_limiter.py      # RateLimiter with adaptive delay and jitter
    user_agents.py       # UA rotation with browser fingerprint consistency
    retry.py             # Retry decorators and Cloudflare challenge detection
    exceptions.py        # Custom exceptions (CloudflareChallenge, RateLimited, etc.)
tests/
    test_http_client.py  # Unit tests with mocked responses
    test_rate_limiter.py
    test_retry.py
    test_integration.py  # Live HLTV tests (20+ pages, all page types)
```

### Pattern 1: Single Session with Persistent Cookies

**What:** Use one `curl_cffi.requests.Session` for the entire scraping run. Do NOT create a new session per request.

**When to use:** Always. This is the default pattern for all HLTV scraping.

**Why:** Cloudflare tracks sessions via cookies (including `cf_clearance`). A session that has passed initial checks retains clearance for 30-60 minutes. Creating new sessions per request means re-validating with Cloudflare every time, which increases detection risk and wastes time. Additionally, HTTP/2 connection reuse within a session reduces latency.

**Example:**

```python
from curl_cffi.requests import Session

class HLTVClient:
    def __init__(self, impersonate: str = "chrome136"):
        self.session = Session(
            impersonate=impersonate,
            timeout=30,
        )

    def fetch(self, url: str) -> str:
        """Fetch a URL and return HTML content."""
        response = self.session.get(url)
        response.raise_for_status()
        return response.text

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
```

**Critical constraint:** When impersonating a browser, do NOT override the User-Agent header to a mismatched browser. If `impersonate="chrome136"`, the TLS fingerprint says Chrome 136. Sending a Firefox User-Agent header creates a detectable mismatch. The User-Agent rotation must stay within the Chrome family when impersonating Chrome.

### Pattern 2: Cloudflare Challenge Detection

**What:** Programmatically detect whether a response is a Cloudflare challenge page vs. real HLTV content.

**When to use:** After every HTTP response, before processing the HTML.

**Why:** A 403 from HLTV could mean "page not found" or "Cloudflare challenge." A 200 could contain challenge HTML instead of real content. Detection must happen at the response level, not just status code level.

**Example:**

```python
class CloudflareChallenge(Exception):
    """Raised when Cloudflare serves a challenge page instead of content."""
    pass

class RateLimited(Exception):
    """Raised on HTTP 429."""
    pass

def check_response(response) -> None:
    """Raise appropriate exception if response is not valid HLTV content."""
    # Method 1: Check cf-mitigated header (most reliable)
    if response.headers.get("cf-mitigated") == "challenge":
        raise CloudflareChallenge(
            f"Cloudflare challenge on {response.url} "
            f"(status={response.status_code})"
        )

    # Method 2: Check for challenge HTML signatures
    if response.status_code == 403:
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            text = response.text[:2000]  # Only check beginning
            if any(sig in text for sig in [
                "cf-chl-widget",
                "challenge-platform",
                "_cf_chl_opt",
                "Checking your browser",
                "Just a moment...",
            ]):
                raise CloudflareChallenge(
                    f"Cloudflare challenge HTML on {response.url}"
                )
        raise CloudflareChallenge(f"HTTP 403 on {response.url}")

    # Method 3: Check for rate limiting
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        raise RateLimited(
            f"Rate limited on {response.url}, "
            f"Retry-After: {retry_after}"
        )

    # Method 4: Check for server errors (retriable)
    if response.status_code == 503:
        raise CloudflareChallenge(
            f"HTTP 503 on {response.url} (possible Cloudflare)"
        )
```

### Pattern 3: Rate Limiter with Adaptive Backoff

**What:** A stateful rate limiter that manages delays between requests with randomized jitter and adaptive slowdown.

**When to use:** Wraps every HTTP request. The rate limiter is called BEFORE each request, not after.

**Why:** Fixed delays are detectable -- Cloudflare's behavioral analysis looks for regular timing patterns. Adaptive backoff slows down when challenges appear and speeds up (gradually) during sustained success.

**Example:**

```python
import time
import random

class RateLimiter:
    def __init__(
        self,
        min_delay: float = 3.0,
        max_delay: float = 8.0,
        backoff_factor: float = 2.0,
        recovery_factor: float = 0.95,
        max_backoff: float = 120.0,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.current_delay = min_delay
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self.max_backoff = max_backoff
        self._last_request_time = 0.0

    def wait(self) -> float:
        """Wait before making the next request. Returns actual delay used."""
        now = time.monotonic()
        elapsed = now - self._last_request_time

        # Add jitter: uniform random within [current_delay, current_delay * 1.5]
        jittered_delay = self.current_delay + random.uniform(
            0, self.current_delay * 0.5
        )

        # Account for time already elapsed since last request
        remaining = max(0, jittered_delay - elapsed)

        if remaining > 0:
            time.sleep(remaining)

        self._last_request_time = time.monotonic()
        return jittered_delay

    def backoff(self) -> None:
        """Increase delay after a failed request or challenge."""
        self.current_delay = min(
            self.current_delay * self.backoff_factor,
            self.max_backoff,
        )

    def recover(self) -> None:
        """Gradually decrease delay after a successful request."""
        self.current_delay = max(
            self.current_delay * self.recovery_factor,
            self.min_delay,
        )

    def reset(self) -> None:
        """Reset delay to minimum (after long pause or IP change)."""
        self.current_delay = self.min_delay
```

### Pattern 4: User-Agent Rotation with Fingerprint Consistency

**What:** Rotate User-Agent strings BUT keep them consistent with the impersonated browser's TLS fingerprint.

**When to use:** When rotating UA strings. Critical constraint when using curl_cffi with impersonation.

**Why:** curl_cffi impersonating `chrome136` sends a Chrome 136 TLS fingerprint. If the User-Agent header says Firefox or Safari, Cloudflare detects the mismatch instantly. The UA must be a Chrome variant matching the impersonated version range.

**Example:**

```python
from fake_useragent import UserAgent

class UserAgentRotator:
    """Rotates User-Agent strings consistent with curl_cffi impersonation target."""

    def __init__(self, impersonate_target: str = "chrome136"):
        self._target = impersonate_target
        self._browser_family = self._get_browser_family(impersonate_target)
        self._ua = UserAgent(
            browsers=[self._browser_family],
            platforms=["desktop"],
            min_version=120.0,  # Only modern versions
        )

    @staticmethod
    def _get_browser_family(target: str) -> str:
        if target.startswith("chrome") or target.startswith("edge"):
            return "Chrome"
        elif target.startswith("safari"):
            return "Safari"
        elif target.startswith("firefox"):
            return "Firefox"
        return "Chrome"  # default

    def get(self) -> str:
        """Get a random User-Agent string matching the impersonation target."""
        return self._ua.random

    def get_with_headers(self) -> dict:
        """Get UA string and matching Sec-CH-UA headers for Chrome."""
        ua_string = self.get()
        headers = {"User-Agent": ua_string}

        if self._browser_family == "Chrome":
            # Modern Chrome sends Client Hints headers
            headers.update({
                "Sec-CH-UA-Platform": '"Windows"',
                "Sec-CH-UA-Mobile": "?0",
            })

        return headers
```

**Important note on curl_cffi default headers:** When `impersonate` is set, curl_cffi automatically sets browser-appropriate headers including User-Agent and Sec-CH-UA. You can override the User-Agent while keeping other impersonation headers by passing a `headers` dict. However, overriding with a mismatched browser UA is counter-productive. The safest approach is:

1. Use curl_cffi's default UA for the impersonation target (safest, no mismatch possible)
2. Override only with same-family UAs (e.g., different Chrome version strings when impersonating Chrome)
3. Rotate across sessions, not within a session (real users don't change UA mid-browsing)

### Anti-Patterns to Avoid

- **Rotating UA on every request:** Real browsers keep the same UA for an entire session. Rotating per-request is a signal. Instead, rotate per-session or per-batch (e.g., every 10-20 requests).
- **Chrome TLS + Firefox UA:** Instant detection. TLS fingerprint and User-Agent must be from the same browser family.
- **Creating new Session per request:** Loses cookies, connection reuse, and Cloudflare clearance. Use one Session for the entire run.
- **Fixed delays between requests:** 5.000s, 5.000s, 5.000s is machine-like. Use random jitter: uniform(3.0, 8.0) or base + uniform(0, base * 0.5).
- **Retrying 403 without delay:** Cloudflare escalates when it sees rapid retries after a block. Always increase delay after a 403 before retrying.
- **Ignoring the cf-mitigated header:** Parsing HTML to detect challenges is fragile. The `cf-mitigated: challenge` header is the official, reliable detection method.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TLS fingerprint impersonation | Custom TLS configuration | curl_cffi `impersonate` parameter | TLS fingerprinting involves cipher suite ordering, extension ordering, supported groups, ALPN protocols, and dozens of other parameters. curl_cffi handles all of this by compiling actual browser TLS stacks. |
| Retry with exponential backoff | Custom retry loops with sleep() | tenacity decorator | Edge cases: jitter, max attempts, retry-on-specific-exceptions, Retry-After header respect, callback on retry. tenacity handles all of these. |
| User-Agent generation | Hardcoded UA string lists | fake-useragent library | UA strings go stale. fake-useragent pulls from real-world browser usage data. Supports filtering by browser, platform, and minimum version. |
| HTTP/2 support | Manual HTTP/2 frame ordering | curl_cffi (built-in) | Cloudflare checks HTTP/2 frame ordering (SETTINGS, WINDOW_UPDATE, HEADERS order). curl_cffi impersonation handles this automatically. Most Python HTTP libs use HTTP/1.1 which Cloudflare flags. |
| Cookie management | Manual cookie jar | curl_cffi Session (built-in) | Session automatically persists cookies including cf_clearance across requests. Thread-safe. Supports pickling for cross-process persistence. |

## Common Pitfalls

### Pitfall 1: User-Agent / TLS Fingerprint Mismatch

**What goes wrong:** Developer sets `impersonate="chrome136"` in curl_cffi but overrides User-Agent with a Firefox or Safari string. Cloudflare sees Chrome TLS fingerprint + non-Chrome UA and flags immediately.

**Why it happens:** Developer follows generic "rotate user agent" advice without understanding that curl_cffi's impersonation sets the TLS fingerprint to a specific browser. The UA header must match.

**How to avoid:** Only rotate within the same browser family as the impersonation target. If impersonating Chrome, only use Chrome User-Agent strings. Safest: use curl_cffi's default headers (`default_headers=True`, which is the default) and don't override UA at all.

**Warning signs:** First request succeeds (before Cloudflare checks), subsequent requests get 403.

### Pitfall 2: Over-Aggressive Retry on Cloudflare Challenge

**What goes wrong:** Scraper gets a 403, retries immediately 5 times in rapid succession. Cloudflare sees the burst and escalates from temporary challenge to sustained block.

**Why it happens:** Generic retry logic treats all errors the same. A network timeout deserves fast retry; a Cloudflare challenge deserves long backoff.

**How to avoid:** Differentiate error types:
- Network error (timeout, connection reset): Retry after 2-5 seconds
- HTTP 429 (rate limited): Respect Retry-After header, or wait 30-60 seconds
- HTTP 403 (Cloudflare challenge): Wait 60-120 seconds, then retry with increased base delay
- HTTP 503 (possible Cloudflare): Wait 30-60 seconds
- HTTP 404: Do NOT retry (page doesn't exist)

**Warning signs:** Success rate drops from 90% to 0% within a few minutes.

### Pitfall 3: Not Testing Against the Performance Page

**What goes wrong:** Developer tests against `/results` and `/matches/{id}` pages, everything works. Deploys to production. Performance pages (`/stats/matches/performance/mapstatsid/{id}/{slug}`) all return Cloudflare challenges. The chosen HTTP strategy is insufficient.

**Why it happens:** The `/stats/matches/performance/` path has stronger Cloudflare protection than the main `/matches/` path. This is confirmed by the gigobyte/HLTV Node.js API project where `getMatchMapStats` is reported as "consistently blocked by Cloudflare." The performance page requires a separate HTTP request from the overview page.

**How to avoid:** The Phase 1 integration test MUST include fetching at least one performance page URL. If it returns a challenge, the fallback strategy (SeleniumBase UC Mode) must be implemented before Phase 1 is considered complete.

**Warning signs:** Overview pages work fine but performance pages consistently return 403.

### Pitfall 4: Session State Loss Between Requests

**What goes wrong:** Developer creates a fresh `curl_cffi.requests.Session` for each request, or closes and reopens the session between pages. Cloudflare's `cf_clearance` cookie is lost, forcing re-validation on every request.

**Why it happens:** Copy-paste from examples that show `with Session() as s: s.get(url)` in a single block, not understanding that the session should persist across the entire scraping run.

**How to avoid:** Create the Session once at startup, pass it through the entire pipeline, close it at shutdown. The session is thread-safe.

**Warning signs:** Every request takes longer than expected because Cloudflare re-checks each time.

### Pitfall 5: Ignoring Header Order

**What goes wrong:** Developer manually constructs headers dict and passes it to curl_cffi, inadvertently overriding the impersonation's browser-consistent header order.

**Why it happens:** In standard Python `requests`, header order doesn't matter much. With Cloudflare, header order is an active fingerprinting vector. Real browsers send headers in a specific, consistent order.

**How to avoid:** Let curl_cffi handle headers via the `impersonate` parameter. Only override specific headers when absolutely necessary, and prefer adding headers rather than replacing the entire headers dict.

**Warning signs:** Requests fail even though TLS fingerprint and UA are correct.

## Code Examples

### Complete HLTVClient with Rate Limiting and Retry

```python
# Source: Synthesized from curl_cffi docs, tenacity docs, and HLTV-specific patterns

import time
import random
import logging
from typing import Optional

from curl_cffi.requests import Session
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)


class CloudflareChallenge(Exception):
    """Cloudflare served a challenge page instead of content."""
    pass


class RateLimited(Exception):
    """Server returned HTTP 429."""
    pass


class HLTVFetchError(Exception):
    """Non-retriable fetch error (404, unexpected status)."""
    pass


class RateLimiter:
    """Manages delays between requests with jitter and adaptive backoff."""

    def __init__(
        self,
        min_delay: float = 3.0,
        max_delay: float = 8.0,
        backoff_factor: float = 2.0,
        recovery_factor: float = 0.95,
        max_backoff: float = 120.0,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.current_delay = min_delay
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self.max_backoff = max_backoff
        self._last_request_time: float = 0.0

    def wait(self) -> float:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        jittered = random.uniform(self.current_delay, self.current_delay * 1.5)
        remaining = max(0, jittered - elapsed)
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_time = time.monotonic()
        return jittered

    def backoff(self) -> None:
        self.current_delay = min(
            self.current_delay * self.backoff_factor, self.max_backoff
        )
        logger.warning(f"Rate limiter backoff: delay now {self.current_delay:.1f}s")

    def recover(self) -> None:
        self.current_delay = max(
            self.current_delay * self.recovery_factor, self.min_delay
        )


def _check_response(response) -> None:
    """Detect Cloudflare challenges and rate limiting in response."""
    # Official Cloudflare detection: cf-mitigated header
    if response.headers.get("cf-mitigated") == "challenge":
        raise CloudflareChallenge(
            f"cf-mitigated:challenge on {response.url} (HTTP {response.status_code})"
        )

    if response.status_code == 429:
        raise RateLimited(
            f"HTTP 429 on {response.url}, "
            f"Retry-After: {response.headers.get('Retry-After', 'not set')}"
        )

    if response.status_code in (403, 503):
        # Check for Cloudflare challenge HTML
        if "text/html" in response.headers.get("content-type", ""):
            text_start = response.text[:2000]
            cf_signatures = [
                "cf-chl-widget", "challenge-platform", "_cf_chl_opt",
                "Checking your browser", "Just a moment...",
            ]
            if any(sig in text_start for sig in cf_signatures):
                raise CloudflareChallenge(
                    f"Challenge HTML detected on {response.url} "
                    f"(HTTP {response.status_code})"
                )
        if response.status_code == 403:
            raise CloudflareChallenge(f"HTTP 403 on {response.url}")
        raise CloudflareChallenge(f"HTTP 503 on {response.url}")

    if response.status_code == 404:
        raise HLTVFetchError(f"HTTP 404: {response.url} not found")

    if response.status_code >= 400:
        raise HLTVFetchError(
            f"HTTP {response.status_code} on {response.url}"
        )


class HLTVClient:
    """HTTP client for fetching HLTV pages with anti-detection."""

    def __init__(
        self,
        impersonate: str = "chrome136",
        min_delay: float = 3.0,
        max_delay: float = 8.0,
        max_retries: int = 5,
    ):
        self.session = Session(impersonate=impersonate, timeout=30)
        self.rate_limiter = RateLimiter(
            min_delay=min_delay, max_delay=max_delay
        )
        self.max_retries = max_retries
        self._request_count = 0
        self._success_count = 0

    @retry(
        retry=retry_if_exception_type((CloudflareChallenge, RateLimited)),
        wait=wait_exponential_jitter(
            initial=10, max=120, jitter=5
        ),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def fetch(self, url: str) -> str:
        """Fetch a URL, returning HTML content.

        Raises:
            CloudflareChallenge: if Cloudflare blocks the request (retriable)
            RateLimited: if rate limited (retriable)
            HLTVFetchError: if page not found or other non-retriable error
        """
        self.rate_limiter.wait()
        self._request_count += 1

        try:
            response = self.session.get(url)
            _check_response(response)

            # Success
            self.rate_limiter.recover()
            self._success_count += 1
            logger.debug(
                f"Fetched {url} ({response.status_code}, "
                f"{len(response.text)} chars)"
            )
            return response.text

        except (CloudflareChallenge, RateLimited) as e:
            self.rate_limiter.backoff()
            raise  # Let tenacity handle retry

    @property
    def stats(self) -> dict:
        return {
            "requests": self._request_count,
            "successes": self._success_count,
            "success_rate": (
                self._success_count / self._request_count
                if self._request_count > 0 else 0
            ),
            "current_delay": self.rate_limiter.current_delay,
        }

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
```

### Integration Test Pattern

```python
# Source: Synthesized from HLTV URL patterns and project requirements

import time

# All 5 page types that must be reachable
HLTV_TEST_URLS = {
    "results_listing": "https://www.hltv.org/results",
    "match_overview": "https://www.hltv.org/matches/2376513/faze-vs-natus-vincere-blast-premier-spring-final-2025",
    "map_overview": "https://www.hltv.org/stats/matches/mapstatsid/178889/faze-vs-natus-vincere",
    "map_performance": "https://www.hltv.org/stats/matches/performance/mapstatsid/178889/faze-vs-natus-vincere",
    "map_economy": "https://www.hltv.org/stats/matches/economy/mapstatsid/178889/faze-vs-natus-vincere",
}

def test_all_page_types_reachable():
    """Phase 1 gate: all 5 HLTV page types must return valid HTML."""
    with HLTVClient() as client:
        results = {}
        for page_type, url in HLTV_TEST_URLS.items():
            try:
                html = client.fetch(url)
                # Basic validation: not empty, not a challenge page
                assert len(html) > 1000, f"{page_type}: response too short"
                assert "hltv.org" in html.lower() or "HLTV" in html, (
                    f"{page_type}: doesn't look like HLTV content"
                )
                results[page_type] = "OK"
            except Exception as e:
                results[page_type] = f"FAILED: {e}"

        # Report results
        for page_type, result in results.items():
            print(f"  {page_type}: {result}")

        # All must pass
        failures = [k for k, v in results.items() if v != "OK"]
        assert not failures, f"Failed page types: {failures}"
```

## HLTV-Specific URL Patterns

Understanding HLTV's URL structure is critical for this phase. Each page type has a distinct URL pattern and potentially different Cloudflare protection levels.

### URL Pattern Reference

| Page Type | URL Pattern | Example | Cloudflare Level |
|-----------|------------|---------|-----------------|
| Results listing | `/results?offset={n}` | `/results?offset=0` | Standard |
| Match overview | `/matches/{match_id}/{slug}` | `/matches/2376513/faze-vs-natus-vincere-...` | Standard |
| Map overview | `/stats/matches/mapstatsid/{mapstats_id}/{slug}` | `/stats/matches/mapstatsid/178889/faze-vs-natus-vincere` | Standard-High |
| Map performance | `/stats/matches/performance/mapstatsid/{mapstats_id}/{slug}` | `/stats/matches/performance/mapstatsid/178889/faze-vs-natus-vincere` | HIGH (confirmed harder) |
| Map economy | `/stats/matches/economy/mapstatsid/{mapstats_id}/{slug}` | `/stats/matches/economy/mapstatsid/218557/vitality-vs-furia` | Unknown (assume HIGH) |

### The Performance Page Problem

**Confirmed finding:** The `/stats/matches/performance/mapstatsid/{id}/{slug}` page is harder to scrape than other HLTV pages. Evidence:

1. **gigobyte/HLTV Node.js API** -- The `getMatchMapStats` function makes TWO parallel requests: one to the overview URL and one to the performance URL. The performance URL (`/stats/matches/performance/mapstatsid/{id}/-`) is explicitly a separate endpoint. [Source: GitHub source code](https://github.com/gigobyte/HLTV/blob/master/src/endpoints/getMatchMapStats.ts)

2. **Community reports** -- The issue "getMatchMapStats is consistently blocked by Cloudflare" describes this endpoint returning "checking your browser" challenges when other pages work fine.

3. **URL prefix difference** -- The performance page lives under `/stats/matches/performance/` rather than `/stats/matches/mapstatsid/`. Cloudflare rules can be configured per URL path, and HLTV likely has stricter rules on `/stats/` sub-pages.

**Hypothesis for why it's harder:**

- The `/stats/` path prefix may have a different Cloudflare WAF rule set than `/matches/`
- Performance data may require additional server processing, so HLTV rate-limits it more aggressively
- The performance page may use JavaScript rendering that requires an actual browser environment
- Higher Cloudflare "Security Level" configured for this path (Cloudflare allows per-path rule configuration)

**Mitigation strategy:**

1. Test curl_cffi against the performance page URL first (before building the full client)
2. If curl_cffi returns challenges, try:
   a. Longer delay before performance page requests (e.g., 8-15s instead of 3-8s)
   b. Fetching the overview page first, then the performance page with the same session (may pass accumulated cookies/clearance)
   c. SeleniumBase UC Mode fallback specifically for performance/economy pages
3. The economy page (`/stats/matches/economy/mapstatsid/{id}/{slug}`) should be assumed to have the same protection level as performance until proven otherwise

### Page Fetch Order Strategy

Based on the URL hierarchy, the recommended fetch order for a single match is:

```
1. /matches/{match_id}/{slug}           -- match overview (get map IDs)
2. /stats/matches/mapstatsid/{id}/{slug} -- map overview (per map)
3. /stats/matches/performance/mapstatsid/{id}/{slug} -- map performance (per map)
4. /stats/matches/economy/mapstatsid/{id}/{slug}     -- map economy (per map)
```

For a BO3 match, this means 1 + 3 + 3 + 3 = 10 requests per match. At 5-second average delay, that's ~50 seconds per match.

## Rate Limiting Strategy

### Recommended Delay Ranges

| Scenario | Min Delay | Max Delay | Rationale |
|----------|-----------|-----------|-----------|
| Normal operation | 3.0s | 8.0s | Community consensus from multiple HLTV scraper projects. The gigobyte/HLTV Node.js API uses `delayBetweenPageRequests` parameter. |
| After 403/challenge | 60s | 120s | Cloudflare challenge means detection. Long pause allows reputation recovery. |
| After 429 rate limit | Retry-After header value, or 30-60s | 120s | Respect server signals. |
| After multiple failures (3+) | 120s | 300s | Circuit breaker: stop hammering a blocked endpoint. |
| Performance/economy pages | 5.0s | 12.0s | These pages are harder; slower is safer. |

### Behavioral Patterns to Avoid

Cloudflare's behavioral analysis (ML-based in 2026) detects:

1. **Perfectly regular timing:** 5.000s, 5.000s, 5.000s between requests. Real humans have irregular timing. Use uniform random jitter.
2. **Sequential URL patterns without variation:** Fetching `/results?offset=0`, then `offset=100`, then `offset=200` in rapid sequence looks like a crawler. Intersperse with other page types or add longer pauses between listing pages.
3. **No sub-resource requests:** Real browsers request CSS, JS, images. curl_cffi only requests HTML. This is detectable but not easily fixable without a real browser. Residential IP with good reputation helps compensate.
4. **Consistent request headers across thousands of requests:** While UA rotation within a session is unnatural, the accept-language, accept-encoding, and sec-ch-ua headers should be realistic and consistent within a session.

### Adaptive Rate Limiting Algorithm

```
On success:
    current_delay *= 0.95  (slow recovery toward min_delay)

On 403/challenge:
    current_delay *= 2.0   (double the delay)

On 429:
    current_delay = max(Retry-After, current_delay * 2.0)

On 3 consecutive failures:
    current_delay = 120.0  (circuit breaker: pause 2 minutes)

Bounds:
    min_delay <= current_delay <= max_backoff (120s default)
```

## Error Handling and Retry Strategy

### Error Classification

| HTTP Status | Error Type | Action | Retry? |
|-------------|-----------|--------|--------|
| 200 | Success | Process HTML | No |
| 200 + challenge HTML | Cloudflare challenge (sneaky) | Detect via HTML signatures | Yes, with long backoff |
| 403 | Cloudflare challenge or permanent block | Check cf-mitigated header | Yes, with long backoff |
| 404 | Page not found | Skip this URL | No |
| 429 | Rate limited | Respect Retry-After | Yes, after Retry-After |
| 500 | Server error | Transient failure | Yes, short backoff |
| 502 | Bad gateway | Transient failure | Yes, short backoff |
| 503 | Service unavailable / Cloudflare | Check for challenge HTML | Yes, medium backoff |
| Connection error | Network issue | Transient failure | Yes, short backoff |
| Timeout | Slow response | Transient failure | Yes, short backoff |

### Retry Configuration

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
    after_log,
)

# For Cloudflare challenges: long waits, few retries
CLOUDFLARE_RETRY = retry(
    retry=retry_if_exception_type(CloudflareChallenge),
    wait=wait_exponential_jitter(initial=30, max=120, jitter=10),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)

# For rate limiting: respect server, longer waits
RATE_LIMIT_RETRY = retry(
    retry=retry_if_exception_type(RateLimited),
    wait=wait_exponential_jitter(initial=30, max=300, jitter=15),
    stop=stop_after_attempt(3),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)

# For transient errors: quick retries
TRANSIENT_RETRY = retry(
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    wait=wait_exponential_jitter(initial=2, max=30, jitter=2),
    stop=stop_after_attempt(5),
)

# Combined: use a single decorator that handles all retriable errors
FETCH_RETRY = retry(
    retry=retry_if_exception_type(
        (CloudflareChallenge, RateLimited, ConnectionError, TimeoutError)
    ),
    wait=wait_exponential_jitter(initial=10, max=120, jitter=5),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
```

### What tenacity's wait_exponential_jitter Does

The `wait_exponential_jitter(initial=10, max=120, jitter=5)` strategy works as follows:

- Attempt 1 fails: wait ~10s (+ up to 5s random jitter)
- Attempt 2 fails: wait ~20s (+ up to 5s random jitter)
- Attempt 3 fails: wait ~40s (+ up to 5s random jitter)
- Attempt 4 fails: wait ~80s (+ up to 5s random jitter)
- Attempt 5 fails: wait ~120s (capped at max, + up to 5s random jitter)

This gives aggressive scrapers time to clear out, and the jitter prevents thundering herd if multiple scraper instances exist.

## State of the Art

| Old Approach (2023-2024) | Current Approach (2025-2026) | When Changed | Impact |
|--------------------------|------------------------------|--------------|--------|
| cloudscraper for Cloudflare bypass | curl_cffi for TLS impersonation | 2024-2025 | cloudscraper's js2py-based approach broke with Cloudflare updates. curl_cffi handles TLS layer directly. |
| undetected-chromedriver for browser automation | SeleniumBase UC Mode or nodriver | 2024 | undetected-chromedriver deprecated in favor of nodriver (by same author) and SeleniumBase UC Mode (more actively maintained). |
| puppeteer-extra-stealth (JS) | Deprecated Feb 2025 | Feb 2025 | Original maintainer stopped updates. Cloudflare detection outpaced stealth patches. |
| JA3 fingerprinting only | JA3 + JA4 + HTTP/2 frame order | 2024-2025 | Cloudflare added JA4 (TLS + QUIC) and HTTP/2 frame ordering analysis. curl_cffi handles all three. |
| Per-request User-Agent rotation | Session-consistent UA with Client Hints | 2024-2025 | Modern Chrome sends Sec-CH-UA headers that must match UA. Mismatched Client Hints are a new detection vector. curl_cffi handles this when using impersonation. |

**Deprecated/outdated:**
- cloudscraper: Cannot keep up with Cloudflare 2025-2026 updates, breaks frequently
- puppeteer-extra-stealth: Officially discontinued Feb 2025
- undetected-chromedriver: Succeeded by nodriver, no longer recommended
- Manual JA3 fingerprint setting: curl_cffi's impersonate parameter handles this comprehensively

## curl_cffi Impersonation Targets Reference

### Available Targets (v0.14.0)

| Target | Description |
|--------|-------------|
| `chrome99` through `chrome142` | Chrome versions 99-142 |
| `chrome` | Alias for latest Chrome (currently chrome136) |
| `chrome99_android`, `chrome131_android` | Chrome Android variants |
| `chrome_android` | Alias for latest Chrome Android |
| `safari153` through `safari260` | Safari desktop versions |
| `safari172_ios` through `safari260_ios` | Safari iOS variants |
| `safari`, `safari_ios` | Aliases for latest Safari versions |
| `firefox133` | Firefox 133 |
| `firefox` | Alias for latest Firefox |
| `tor145` | Tor Browser 145 |
| `edge99`, `edge101` | Edge versions |

**Recommended for HLTV:** Use `chrome136` or the `chrome` alias. Chrome is the most common browser globally, so its TLS fingerprint has the best reputation. Using a very recent version (136) is better than older ones (99-110) because Cloudflare considers outdated browser versions suspicious.

## Configuration Surface

### What Should Be Configurable

| Setting | Default | Why Configurable |
|---------|---------|-----------------|
| `min_delay` | 3.0 seconds | May need to increase if Cloudflare starts blocking |
| `max_delay` | 8.0 seconds | May need to increase for aggressive protection |
| `max_retries` | 5 | Trade-off between persistence and giving up |
| `impersonate_target` | "chrome136" | New browser versions may work better |
| `timeout` | 30 seconds | Network conditions vary |
| `backoff_factor` | 2.0 | How aggressively to back off |
| `max_backoff` | 120 seconds | Upper bound on delay |

### What Should Be Hardcoded

| Setting | Value | Why Hardcoded |
|---------|-------|--------------|
| Base URL | `https://www.hltv.org` | Single-site scraper |
| HTTP/2 | Enabled (via impersonate) | Required for Cloudflare bypass |
| Cookie persistence | Session-level | Required for cf_clearance |
| Challenge detection | cf-mitigated header + HTML signatures | Core logic, not user-facing |
| Error classification | Status code mapping table | Core logic |

## Open Questions

Things that couldn't be fully resolved through research alone:

1. **Does curl_cffi pass Cloudflare on HLTV's performance page?**
   - What we know: Overview pages likely work with curl_cffi. Performance pages have stricter protection confirmed by community reports.
   - What's unclear: Whether curl_cffi's TLS impersonation alone suffices, or if HLTV's performance page requires JavaScript execution (Turnstile challenge).
   - Recommendation: Phase 1 integration test must validate this empirically. If curl_cffi fails, implement SeleniumBase UC Mode fallback before moving to Phase 2.
   - **Impact:** If curl_cffi fails on performance pages, the architecture needs a two-tier fetch strategy (curl_cffi for most pages, browser for performance/economy). This should be designed for regardless.

2. **What is HLTV's exact rate limit threshold?**
   - What we know: Community reports suggest ~20-30 requests/minute triggers blocks. The gigobyte/HLTV project has a `delayBetweenPageRequests` parameter.
   - What's unclear: Exact threshold, whether it varies by page type, whether it's per-IP or per-session.
   - Recommendation: Start with 3-8 second delays (conservative). The integration test fetching 20+ pages will provide empirical data on the actual threshold.

3. **Are the economy pages as hard to reach as performance pages?**
   - What we know: Economy page URL confirmed as `/stats/matches/economy/mapstatsid/{id}/{slug}`. It's under the same `/stats/` path prefix as performance.
   - What's unclear: Whether Cloudflare rules for economy pages match performance pages.
   - Recommendation: Assume same difficulty level as performance pages until integration test proves otherwise.

4. **Does HLTV serve different Cloudflare protection to residential vs. datacenter IPs?**
   - What we know: Cloudflare assigns trust scores based on IP type. Datacenter IPs get lower trust. Residential IPs get higher trust.
   - What's unclear: Whether HLTV's specific Cloudflare configuration has explicit datacenter-IP blocking rules.
   - Recommendation: If the developer is running from a residential IP, curl_cffi may work fine. If running from a VPS/cloud, may need to budget for residential proxies. Test from the actual deployment environment.

## Sources

### Primary (HIGH confidence)
- [curl_cffi 0.14.0 GitHub](https://github.com/lexiforest/curl_cffi) -- Repository, capabilities, limitations
- [curl_cffi documentation - Quick Start](https://curl-cffi.readthedocs.io/en/latest/quick_start.html) -- Session API, impersonation, RetryStrategy, cookies
- [curl_cffi documentation - Impersonation Targets](https://curl-cffi.readthedocs.io/en/latest/impersonate/targets.html) -- Complete list of supported browser targets
- [curl_cffi FAQ](https://curl-cffi.readthedocs.io/en/stable/faq.html) -- Cloudflare bypass limitations acknowledged
- [Cloudflare - Detect Challenge Response](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/) -- cf-mitigated header detection method
- [gigobyte/HLTV getMatchMapStats.ts](https://github.com/gigobyte/HLTV/blob/master/src/endpoints/getMatchMapStats.ts) -- Performance page URL pattern confirmed as separate endpoint
- [tenacity documentation](https://tenacity.readthedocs.io/) -- Retry strategies, wait functions
- [fake-useragent 2.2.0 PyPI](https://pypi.org/project/fake-useragent/) -- UA generation capabilities

### Secondary (MEDIUM confidence)
- [curl_cffi Discussion #591](https://github.com/lexiforest/curl_cffi/discussions/591) -- Users reporting increased Cloudflare blocking despite impersonation
- [gigobyte/HLTV Issue #43](https://github.com/gigobyte/HLTV/issues/43) -- HLTV IP bans after sustained scraping
- [Scrapfly - Bypass Cloudflare 2026](https://scrapfly.io/blog/posts/how-to-bypass-cloudflare-anti-scraping) -- Multi-layer detection system, passive vs active challenges
- [hltv-async-api GitHub](https://github.com/akimerslys/hltv-async-api) -- Adaptive delay patterns, proxy support
- [ScrapingBee - User Agent rotation](https://www.scrapingbee.com/blog/list-of-user-agents-for-scraping/) -- UA rotation best practices, Client Hints matching
- [alexwlchan/handling-http-429-with-tenacity](https://github.com/alexwlchan/handling-http-429-with-tenacity) -- Custom tenacity retry conditions for HTTP status codes
- [BrightData - curl_cffi 2026](https://brightdata.com/blog/web-data/web-scraping-with-curl-cffi) -- Current curl_cffi usage patterns
- [Roundproxies - User-Agent rotation](https://roundproxies.com/blog/user-agent-rotation/) -- Session-consistent UA, avoid per-request rotation

### Tertiary (LOW confidence, needs empirical validation)
- HLTV rate limit thresholds (~20-30 req/min) -- Based on community anecdotes, not measured empirically
- Performance page Cloudflare protection level -- Confirmed harder but exact mechanism (passive vs Turnstile) unknown
- Economy page protection level -- Assumed same as performance, not independently verified
- Residential vs datacenter IP behavior on HLTV -- General Cloudflare behavior, not HLTV-specific testing

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- curl_cffi, tenacity, fake-useragent all verified via official docs and PyPI
- Architecture patterns: HIGH -- Session management, challenge detection, rate limiting are well-documented
- HLTV-specific Cloudflare behavior: MEDIUM -- Confirmed via community projects but exact thresholds need empirical testing
- Performance page difficulty: MEDIUM -- Confirmed harder by multiple sources but root cause (passive TLS vs active JS challenge) unknown
- Rate limiting thresholds: LOW -- Community anecdotes only, needs Phase 1 integration test to verify

**Research date:** 2026-02-14
**Valid until:** 2026-03-14 (30 days -- curl_cffi and Cloudflare both update frequently)
