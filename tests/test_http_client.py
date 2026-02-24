"""Unit tests for HLTVClient with mocked nodriver browser.

All tests mock nodriver.start() and page.evaluate() to avoid
launching a real browser or making real HTTP requests.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.config import ScraperConfig
from scraper.exceptions import CloudflareChallenge, HLTVFetchError
from scraper.http_client import HLTVClient, fetch_distributed


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
        "concurrent_tabs": 1,
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
    # browser.get() is used during warm-up and for creating additional tabs
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
# Test 3: fetch() calls per-tab rate_limiter.wait() before navigation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_calls_rate_limiter_wait(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()

    # Mock the per-tab rate limiter (concurrent_tabs=1 → single tab)
    tab_rl = client._tab_rate_limiters[id(client._tabs[0])]
    tab_rl.wait = AsyncMock(return_value=0.0)

    await client.fetch("https://www.hltv.org/test")
    await client.close()

    tab_rl.wait.assert_called_once()


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

    # Mock the per-tab rate limiter
    tab_rl = client._tab_rate_limiters[id(client._tabs[0])]
    tab_rl.wait = AsyncMock(return_value=0.0)
    tab_rl.recover = MagicMock()

    await client.fetch("https://www.hltv.org/test")
    await client.close()

    tab_rl.recover.assert_called_once()


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
# Test 6: Challenge triggers rate_limiter.backoff() on both tab + global
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_backoff_on_challenge(mock_start):
    warmup_page = _mock_page()
    browser = _mock_browser(warmup_page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=1))
    await client.start()

    # Mock both the per-tab and global rate limiters
    tab_rl = client._tab_rate_limiters[id(client._tabs[0])]
    tab_rl.wait = AsyncMock(return_value=0.0)
    tab_rl.backoff = MagicMock()
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
    tab_rl.backoff.assert_called()
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
            fetch_count += 1  # count navigations by title checks
            # Return challenge on the 2nd fetch
            if fetch_count == 2:
                return "Just a moment..."
            return "Match Page | HLTV.org"
        if "document.documentElement.outerHTML" in js:
            return ok_html
        return ""

    client._tab.evaluate = AsyncMock(side_effect=switching_evaluate)

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


# ---------------------------------------------------------------------------
# Test 15: start() creates correct number of tabs
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_start_creates_tab_pool(mock_start):
    page = _mock_page()
    browser = _mock_browser(page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(concurrent_tabs=3))
    await client.start()

    assert len(client._tabs) == 3
    assert client._tab_pool.qsize() == 3
    await client.close()


# ---------------------------------------------------------------------------
# Test 16: fetch_many with multiple tabs runs concurrently
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_many_concurrent_tabs(mock_start):
    """Verify that multiple tabs fetch pages concurrently.

    Uses 3 tabs with a real (non-zero) page_load_wait to ensure
    concurrent execution is faster than sequential.
    """
    # Create 3 distinct mock pages so each tab is a separate object
    pages = [_mock_page() for _ in range(3)]
    browser = AsyncMock()
    browser.get = AsyncMock(side_effect=pages)
    browser.stop = MagicMock()
    mock_start.return_value = browser

    # Use a small but nonzero page_load_wait to simulate real delays
    client = HLTVClient(_make_config(concurrent_tabs=3, page_load_wait=0.05))
    await client.start()

    urls = [f"https://www.hltv.org/test{i}" for i in range(6)]
    results = await client.fetch_many(urls)
    await client.close()

    assert len(results) == 6
    for r in results:
        assert isinstance(r, str)
        assert len(r) > 10000


# ---------------------------------------------------------------------------
# Test 17: tab is returned to pool even on failure
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_tab_returned_to_pool_on_failure(mock_start):
    warmup_page = _mock_page()
    browser = _mock_browser(warmup_page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=1))
    await client.start()

    # Make fetch fail
    async def fail_evaluate(js):
        if "document.title" in js:
            return "Just a moment..."
        return ""

    client._tab.evaluate = AsyncMock(side_effect=fail_evaluate)

    with pytest.raises(CloudflareChallenge):
        await client.fetch("https://www.hltv.org/test")

    # Tab should be back in the pool
    assert client._tab_pool.qsize() == 1

    await client.close()


# ---------------------------------------------------------------------------
# Test 18: concurrent_tabs=1 still works (sequential fallback)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_single_tab_fallback(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config(concurrent_tabs=1))
    await client.start()

    assert len(client._tabs) == 1
    assert client._tab_pool.qsize() == 1

    urls = ["https://www.hltv.org/test1", "https://www.hltv.org/test2"]
    results = await client.fetch_many(urls)
    await client.close()

    assert len(results) == 2
    for r in results:
        assert isinstance(r, str)


# ---------------------------------------------------------------------------
# Test 19: fetch_distributed with single client delegates to fetch_many
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_distributed_single_client(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()

    urls = [
        "https://www.hltv.org/test1",
        "https://www.hltv.org/test2",
        "https://www.hltv.org/test3",
    ]
    results = await fetch_distributed([client], urls)
    await client.close()

    assert len(results) == 3
    for r in results:
        assert isinstance(r, str)
        assert len(r) > 10000


# ---------------------------------------------------------------------------
# Test 20: fetch_distributed with multiple clients splits work round-robin
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_distributed_multiple_clients(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client1 = HLTVClient(_make_config())
    await client1.start()
    client2 = HLTVClient(_make_config())
    await client2.start()

    urls = [f"https://www.hltv.org/test{i}" for i in range(5)]
    results = await fetch_distributed([client1, client2], urls)
    await client1.close()
    await client2.close()

    assert len(results) == 5
    for r in results:
        assert isinstance(r, str)
        assert len(r) > 10000


# ---------------------------------------------------------------------------
# Test 21: fetch_distributed preserves order with multiple clients
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_distributed_preserves_order():
    """Verify results are in the same order as input URLs regardless of
    round-robin distribution across clients."""
    ok_html = "<html>" + "x" * 20000 + "</html>"

    async def make_client(label):
        client = MagicMock(spec=HLTVClient)

        async def fake_fetch_many(urls, content_marker=None, ready_selector=None):
            return [f"{label}:{url}" for url in urls]

        client.fetch_many = AsyncMock(side_effect=fake_fetch_many)
        return client

    c1 = await make_client("c1")
    c2 = await make_client("c2")
    c3 = await make_client("c3")

    urls = [f"url{i}" for i in range(7)]
    results = await fetch_distributed([c1, c2, c3], urls)

    assert len(results) == 7
    # url0 -> c1, url1 -> c2, url2 -> c3, url3 -> c1, url4 -> c2, url5 -> c3, url6 -> c1
    assert results[0] == "c1:url0"
    assert results[1] == "c2:url1"
    assert results[2] == "c3:url2"
    assert results[3] == "c1:url3"
    assert results[4] == "c2:url4"
    assert results[5] == "c3:url5"
    assert results[6] == "c1:url6"


# ---------------------------------------------------------------------------
# Test 22: fetch_distributed with empty URL list
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_distributed_empty_urls(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()

    results = await fetch_distributed([client], [])
    await client.close()

    assert results == []


# ---------------------------------------------------------------------------
# Test 23: fetch_distributed captures errors without aborting
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_distributed_captures_errors():
    """Verify per-URL errors are captured even when distributed."""
    err = Exception("fail")

    async def fetch_many_with_error(urls, content_marker=None, ready_selector=None):
        return [err if "bad" in u else f"ok:{u}" for u in urls]

    c1 = MagicMock(spec=HLTVClient)
    c1.fetch_many = AsyncMock(side_effect=fetch_many_with_error)
    c2 = MagicMock(spec=HLTVClient)
    c2.fetch_many = AsyncMock(side_effect=fetch_many_with_error)

    urls = ["good0", "bad1", "good2", "good3"]
    results = await fetch_distributed([c1, c2], urls)

    assert len(results) == 4
    assert results[0] == "ok:good0"
    assert isinstance(results[1], Exception)
    assert results[2] == "ok:good2"
    assert results[3] == "ok:good3"


# ---------------------------------------------------------------------------
# Test 24: HLTVClient stores proxy_url
# ---------------------------------------------------------------------------
def test_proxy_url_stored():
    client = HLTVClient(_make_config(), proxy_url="socks5://127.0.0.1:1080")
    assert client._proxy_url == "socks5://127.0.0.1:1080"


# ---------------------------------------------------------------------------
# Test 25: HLTVClient passes proxy to browser_args
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_proxy_passed_to_browser(mock_start):
    browser = _mock_browser()
    mock_start.return_value = browser

    client = HLTVClient(_make_config(), proxy_url="http://proxy:8080")
    await client.start()
    await client.close()

    call_kwargs = mock_start.call_args
    browser_args = call_kwargs.kwargs.get("browser_args", call_kwargs[1].get("browser_args", []))
    assert any("--proxy-server=http://proxy:8080" in arg for arg in browser_args)


# ---------------------------------------------------------------------------
# Test 26: content_marker found on first extraction — succeeds immediately
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_content_marker_found(mock_start):
    html_content = "<html>" + "x" * 20000 + '<div class="team1-gradient">Team</div></html>'
    page = _mock_page(html=html_content)
    browser = _mock_browser(page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()
    result = await client.fetch("https://www.hltv.org/test", content_marker="team1-gradient")
    await client.close()

    assert result == html_content


# ---------------------------------------------------------------------------
# Test 27: content_marker not found on first extraction, found on retry
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_content_marker_not_found_then_found(mock_start):
    incomplete_html = "<html>" + "x" * 20000 + "</html>"
    complete_html = "<html>" + "x" * 20000 + '<div class="match-info-box">Info</div></html>'
    warmup_page = _mock_page()
    browser = _mock_browser(warmup_page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()

    # First outerHTML call returns incomplete, second returns complete
    call_count = 0

    async def staged_evaluate(js):
        nonlocal call_count
        if "document.title" in js:
            return "Match Page | HLTV.org"
        if "document.documentElement.outerHTML" in js:
            call_count += 1
            if call_count <= 1:
                return incomplete_html
            return complete_html
        return ""

    client._tab.evaluate = AsyncMock(side_effect=staged_evaluate)

    result = await client.fetch("https://www.hltv.org/test", content_marker="match-info-box")
    await client.close()

    assert result == complete_html


# ---------------------------------------------------------------------------
# Test 28: content_marker never found — raises HLTVFetchError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_content_marker_never_found(mock_start):
    incomplete_html = "<html>" + "x" * 20000 + "</html>"
    page = _mock_page(html=incomplete_html)
    browser = _mock_browser(page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config(max_retries=1))
    await client.start()

    with pytest.raises(HLTVFetchError, match="Content marker"):
        await client.fetch("https://www.hltv.org/test", content_marker="match-info-box")

    await client.close()


# ---------------------------------------------------------------------------
# Test 29: content_marker=None — no check (backward compat)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_content_marker_none(mock_start):
    html_content = "<html>" + "x" * 20000 + "</html>"
    page = _mock_page(html=html_content)
    browser = _mock_browser(page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()
    result = await client.fetch("https://www.hltv.org/test", content_marker=None)
    await client.close()

    assert result == html_content


# ---------------------------------------------------------------------------
# Test 30: fetch_many passes content_marker through to each URL
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@patch("nodriver.start")
async def test_fetch_many_with_content_marker(mock_start):
    html_content = "<html>" + "x" * 20000 + '<div data-fusionchart-config="{}"></div></html>'
    page = _mock_page(html=html_content)
    browser = _mock_browser(page)
    mock_start.return_value = browser

    client = HLTVClient(_make_config())
    await client.start()

    urls = ["https://www.hltv.org/test1", "https://www.hltv.org/test2"]
    results = await client.fetch_many(urls, content_marker="data-fusionchart-config")
    await client.close()

    assert len(results) == 2
    for r in results:
        assert isinstance(r, str)
        assert "data-fusionchart-config" in r
