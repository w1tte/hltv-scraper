"""Unit tests for HLTVClient with mocked nodriver browser.

All tests mock nodriver.start() and page.evaluate() to avoid
launching a real browser or making real HTTP requests.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.config import ScraperConfig
from scraper.exceptions import CloudflareChallenge, HLTVFetchError
from scraper.http_client import HLTVClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> ScraperConfig:
    """Create a config with fast settings for testing."""
    defaults = {
        "max_retries": 2,
        "min_delay": 0.0,
        "max_delay": 0.0,
        "page_load_wait": 0.0,
        "challenge_wait": 0.0,
        "concurrent_tabs": 3,
    }
    defaults.update(overrides)
    return ScraperConfig(**defaults)


def _mock_page(title: str = "Match Page | HLTV.org", html: str = "<html>" + "x" * 20000 + "</html>"):
    """Create a mock nodriver page/tab with evaluate() and get()."""
    page = AsyncMock()

    async def evaluate_side_effect(js: str):
        if "document.title" in js:
            return title
        if "document.documentElement.outerHTML" in js:
            return html
        return ""

    page.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    # tab.get(url) navigates the existing tab and returns self
    page.get = AsyncMock(return_value=page)
    return page


def _mock_browser(page=None):
    """Create a mock nodriver browser that returns a mock page on get()."""
    if page is None:
        page = _mock_page()
    browser = AsyncMock()
    # browser.get() is only used during warm-up; returns the tab
    browser.get = AsyncMock(return_value=page)
    browser.stop = MagicMock()
    return browser


# ---------------------------------------------------------------------------
# Test 1: Successful fetch returns HTML
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_success_returns_html(mock_start):
    html_content = "<html>" + "x" * 20000 + "</html>"
    page = _mock_page(html=html_content)
    browser = _mock_browser(page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()
    result = await client.fetch("https://www.hltv.org/matches/12345/test")
    await client.close()

    assert result == html_content


# ---------------------------------------------------------------------------
# Test 2: Successful fetch increments counters
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_success_increments_counters(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()
    await client.fetch("https://www.hltv.org/test")
    await client.close()

    stats = client.stats
    assert stats["requests"] == 1
    assert stats["successes"] == 1
    assert stats["challenges"] == 0


# ---------------------------------------------------------------------------
# Test 3: fetch() calls rate_limiter.wait() before navigation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_calls_rate_limiter_wait(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()
    client.rate_limiter.wait = AsyncMock(return_value=0.0)

    await client.fetch("https://www.hltv.org/test")
    await client.close()

    client.rate_limiter.wait.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: fetch() calls rate_limiter.recover() on success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_recovers_on_success(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()
    client.rate_limiter.wait = AsyncMock(return_value=0.0)
    client.rate_limiter.recover = MagicMock()

    await client.fetch("https://www.hltv.org/test")
    await client.close()

    client.rate_limiter.recover.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5: Challenge title raises CloudflareChallenge
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_cloudflare_challenge_detected_by_title(mock_start):
    # Warm-up page is OK, but then tab navigation returns challenge
    warmup_page = _mock_page()  # normal title for warm-up
    browser = _mock_browser(warmup_page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=1))
    await client.start()

    # After warm-up, replace evaluate to return challenge title
    async def challenge_evaluate(js):
        if "document.title" in js:
            return "Just a moment..."
        if "document.documentElement.outerHTML" in js:
            return "<html>challenge</html>"
        return ""

    client._tab.evaluate = AsyncMock(side_effect=challenge_evaluate)

    with pytest.raises(CloudflareChallenge):
        await client.fetch("https://www.hltv.org/test")

    await client.close()
    assert client.stats["challenges"] >= 1


# ---------------------------------------------------------------------------
# Test 6: Challenge triggers rate_limiter.backoff()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_backoff_on_challenge(mock_start):
    warmup_page = _mock_page()
    browser = _mock_browser(warmup_page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=1))
    await client.start()
    client.rate_limiter.wait = AsyncMock(return_value=0.0)
    client.rate_limiter.backoff = MagicMock()

    # Replace evaluate to return challenge
    async def challenge_evaluate(js):
        if "document.title" in js:
            return "Just a moment..."
        return ""

    client._tab.evaluate = AsyncMock(side_effect=challenge_evaluate)

    with pytest.raises(CloudflareChallenge):
        await client.fetch("https://www.hltv.org/test")

    await client.close()
    client.rate_limiter.backoff.assert_called()


# ---------------------------------------------------------------------------
# Test 7: Tenacity retries on challenge then succeeds
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_retry_on_challenge_then_success(mock_start):
    ok_html = "<html>" + "x" * 20000 + "</html>"
    warmup_page = _mock_page()
    browser = _mock_browser(warmup_page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=3))
    await client.start()

    # First fetch: challenge, second fetch: success
    call_count = 0

    async def switching_evaluate(js):
        nonlocal call_count
        if "document.title" in js:
            call_count += 1
            if call_count <= 1:
                return "Just a moment..."
            return "Match Page | HLTV.org"
        if "document.documentElement.outerHTML" in js:
            return ok_html
        return ""

    client._tab.evaluate = AsyncMock(side_effect=switching_evaluate)

    result = await client.fetch("https://www.hltv.org/test")
    await client.close()

    assert result == ok_html


# ---------------------------------------------------------------------------
# Test 8: Too-short response raises HLTVFetchError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_short_response_raises_error(mock_start):
    warmup_page = _mock_page()
    browser = _mock_browser(warmup_page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=1))
    await client.start()

    # Replace evaluate to return short HTML
    async def short_evaluate(js):
        if "document.title" in js:
            return "Match Page"
        if "document.documentElement.outerHTML" in js:
            return "<html>tiny</html>"
        return ""

    client._tab.evaluate = AsyncMock(side_effect=short_evaluate)

    with pytest.raises(HLTVFetchError, match="too short"):
        await client.fetch("https://www.hltv.org/test")

    await client.close()


# ---------------------------------------------------------------------------
# Test 9: fetch() without start() raises HLTVFetchError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_without_start_raises_error():
    client = HLTVClient(_make_config())

    with pytest.raises(HLTVFetchError, match="Browser not started"):
        await client.fetch("https://www.hltv.org/test")


# ---------------------------------------------------------------------------
# Test 10: Async context manager starts and stops browser
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_async_context_manager(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    async with HLTVClient(_make_config()) as client:
        assert client._browser is not None
        assert client._tab is not None
        await client.fetch("https://www.hltv.org/test")

    # After exit, browser should be stopped
    browser.stop.assert_called_once()
    assert client._browser is None
    assert client._tab is None


# ---------------------------------------------------------------------------
# Test 11: close() is safe to call multiple times
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_close_idempotent(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()
    await client.close()
    await client.close()  # should not raise

    assert client._browser is None
    assert client._tab is None


# ---------------------------------------------------------------------------
# Test 12: stats reports correct success rate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_stats_accuracy(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()

    await client.fetch("https://www.hltv.org/test1")
    await client.fetch("https://www.hltv.org/test2")
    await client.fetch("https://www.hltv.org/test3")
    await client.close()

    stats = client.stats
    assert stats["requests"] == 3
    assert stats["successes"] == 3
    assert stats["success_rate"] == 1.0
    assert stats["current_delay"] >= 0


# ---------------------------------------------------------------------------
# Test 13: fetch_many returns results in order
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_many_returns_ordered_results(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()

    urls = [
        "https://www.hltv.org/test1",
        "https://www.hltv.org/test2",
        "https://www.hltv.org/test3",
    ]
    results = await client.fetch_many(urls)
    await client.close()

    assert len(results) == 3
    for r in results:
        assert isinstance(r, str)
        assert len(r) > 10000


# ---------------------------------------------------------------------------
# Test 14: fetch_many captures per-URL errors without aborting
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_many_captures_errors(mock_start):
    warmup_page = _mock_page()
    browser = _mock_browser(warmup_page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=1))
    await client.start()

    # Track fetch calls to make 2nd one fail
    fetch_count = 0
    ok_html = "<html>" + "x" * 20000 + "</html>"

    async def switching_evaluate(js):
        nonlocal fetch_count
        if "document.title" in js:
            # Return challenge on the 2nd fetch
            if fetch_count == 2:
                return "Just a moment..."
            return "Match Page | HLTV.org"
        if "document.documentElement.outerHTML" in js:
            return ok_html
        return ""

    client._tab.evaluate = AsyncMock(side_effect=switching_evaluate)

    # Patch tab.get to track fetch count
    original_get = client._tab.get

    async def counting_get(url):
        nonlocal fetch_count
        fetch_count += 1
        return await original_get(url)

    client._tab.get = AsyncMock(side_effect=counting_get)

    urls = [
        "https://www.hltv.org/test1",
        "https://www.hltv.org/test2",
        "https://www.hltv.org/test3",
    ]
    results = await client.fetch_many(urls)
    await client.close()

    assert len(results) == 3
    assert isinstance(results[0], str)  # success
    assert isinstance(results[1], Exception)  # failed
    assert isinstance(results[2], str)  # success
