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
    }
    defaults.update(overrides)
    return ScraperConfig(**defaults)


def _mock_page(title: str = "Match Page | HLTV.org", html: str = "<html>" + "x" * 20000 + "</html>"):
    """Create a mock nodriver page with evaluate() returning title/html."""
    page = AsyncMock()

    async def evaluate_side_effect(js: str):
        if "document.title" in js:
            return title
        if "document.documentElement.outerHTML" in js:
            return html
        return ""

    page.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    return page


def _mock_browser(page=None):
    """Create a mock nodriver browser that returns a mock page on get()."""
    if page is None:
        page = _mock_page()
    browser = AsyncMock()
    browser.get = AsyncMock(return_value=page)
    browser.stop = MagicMock()
    return browser


# ---------------------------------------------------------------------------
# Test 1: Successful fetch returns HTML
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("time.sleep")
@patch("nodriver.start")
async def test_fetch_success_returns_html(mock_start, mock_sleep):
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
@patch("time.sleep")
@patch("nodriver.start")
async def test_fetch_success_increments_counters(mock_start, mock_sleep):
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
@patch("time.sleep")
@patch("nodriver.start")
async def test_fetch_calls_rate_limiter_wait(mock_start, mock_sleep):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()
    client.rate_limiter.wait = MagicMock(return_value=0.0)

    await client.fetch("https://www.hltv.org/test")
    await client.close()

    client.rate_limiter.wait.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: fetch() calls rate_limiter.recover() on success
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("time.sleep")
@patch("nodriver.start")
async def test_fetch_recovers_on_success(mock_start, mock_sleep):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()
    client.rate_limiter.wait = MagicMock(return_value=0.0)
    client.rate_limiter.recover = MagicMock()

    await client.fetch("https://www.hltv.org/test")
    await client.close()

    client.rate_limiter.recover.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5: Challenge title raises CloudflareChallenge
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("time.sleep")
@patch("nodriver.start")
async def test_cloudflare_challenge_detected_by_title(mock_start, mock_sleep):
    page = _mock_page(title="Just a moment...")
    browser = _mock_browser(page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=1))
    await client.start()

    with pytest.raises(CloudflareChallenge):
        await client.fetch("https://www.hltv.org/test")

    await client.close()
    assert client.stats["challenges"] >= 1


# ---------------------------------------------------------------------------
# Test 6: Challenge triggers rate_limiter.backoff()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("time.sleep")
@patch("nodriver.start")
async def test_fetch_backoff_on_challenge(mock_start, mock_sleep):
    page = _mock_page(title="Just a moment...")
    browser = _mock_browser(page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=1))
    await client.start()
    client.rate_limiter.wait = MagicMock(return_value=0.0)
    client.rate_limiter.backoff = MagicMock()

    with pytest.raises(CloudflareChallenge):
        await client.fetch("https://www.hltv.org/test")

    await client.close()
    client.rate_limiter.backoff.assert_called()


# ---------------------------------------------------------------------------
# Test 7: Tenacity retries on challenge then succeeds
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("time.sleep")
@patch("nodriver.start")
async def test_retry_on_challenge_then_success(mock_start, mock_sleep):
    call_count = 0
    ok_html = "<html>" + "x" * 20000 + "</html>"

    async def evaluate_switching(js):
        nonlocal call_count
        if "document.title" in js:
            call_count += 1
            # First 2 calls return challenge title, then OK
            if call_count <= 2:
                return "Just a moment..."
            return "Match Page | HLTV.org"
        if "document.documentElement.outerHTML" in js:
            return ok_html
        return ""

    page = AsyncMock()
    page.evaluate = AsyncMock(side_effect=evaluate_switching)
    browser = _mock_browser(page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=3))
    await client.start()

    result = await client.fetch("https://www.hltv.org/test")
    await client.close()

    assert result == ok_html


# ---------------------------------------------------------------------------
# Test 8: Too-short response raises HLTVFetchError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("time.sleep")
@patch("nodriver.start")
async def test_short_response_raises_error(mock_start, mock_sleep):
    page = _mock_page(html="<html>tiny</html>")
    browser = _mock_browser(page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=1))
    await client.start()

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
@patch("time.sleep")
@patch("nodriver.start")
async def test_async_context_manager(mock_start, mock_sleep):
    browser = _mock_browser()
    mock_start.return_value = browser

    async with HLTVClient(_make_config()) as client:
        assert client._browser is not None
        await client.fetch("https://www.hltv.org/test")

    # After exit, browser should be stopped
    browser.stop.assert_called_once()
    assert client._browser is None


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


# ---------------------------------------------------------------------------
# Test 12: stats reports correct success rate
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("time.sleep")
@patch("nodriver.start")
async def test_stats_accuracy(mock_start, mock_sleep):
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
