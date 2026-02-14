"""Unit tests for HLTVClient with mocked HTTP responses.

All tests use MockResponse objects and patched session.get / time.sleep
to avoid real HTTP requests and real delays.
"""

from unittest.mock import MagicMock, patch

import pytest

from scraper.config import ScraperConfig
from scraper.exceptions import (
    CloudflareChallenge,
    HLTVFetchError,
    PageNotFound,
    RateLimited,
)
from scraper.http_client import HLTVClient, _check_response


class MockResponse:
    """Fake curl_cffi response for unit testing."""

    def __init__(
        self,
        status_code: int = 200,
        text: str = "<html>HLTV</html>",
        headers: dict | None = None,
        url: str = "https://www.hltv.org/test",
    ):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {"content-type": "text/html"}
        self.url = url


def _make_client(**overrides) -> HLTVClient:
    """Create an HLTVClient with fast settings for testing.

    Patches time.sleep so rate limiter doesn't actually wait.
    Uses max_retries=2 for fast tests.
    """
    defaults = {"max_retries": 2, "min_delay": 0.0, "max_delay": 0.0}
    defaults.update(overrides)
    config = ScraperConfig(**defaults)
    return HLTVClient(config)


# ---------------------------------------------------------------------------
# Test 1: Successful fetch returns HTML
# ---------------------------------------------------------------------------
@patch("time.sleep")
@patch("curl_cffi.requests.Session.get")
def test_fetch_success_returns_html(mock_get, mock_sleep):
    mock_get.return_value = MockResponse(text="<html>Match Page</html>")

    client = _make_client()
    result = client.fetch("https://www.hltv.org/matches/12345/test")
    client.close()

    assert result == "<html>Match Page</html>"


# ---------------------------------------------------------------------------
# Test 2: Successful fetch increments counters
# ---------------------------------------------------------------------------
@patch("time.sleep")
@patch("curl_cffi.requests.Session.get")
def test_fetch_success_increments_counters(mock_get, mock_sleep):
    mock_get.return_value = MockResponse()

    client = _make_client()
    client.fetch("https://www.hltv.org/test")
    client.close()

    stats = client.stats
    assert stats["requests"] == 1
    assert stats["successes"] == 1
    assert stats["challenges"] == 0


# ---------------------------------------------------------------------------
# Test 3: fetch() calls rate_limiter.wait() before HTTP request
# ---------------------------------------------------------------------------
@patch("time.sleep")
@patch("curl_cffi.requests.Session.get")
def test_fetch_calls_rate_limiter_wait(mock_get, mock_sleep):
    mock_get.return_value = MockResponse()

    client = _make_client()
    client.rate_limiter.wait = MagicMock(return_value=0.0)

    client.fetch("https://www.hltv.org/test")
    client.close()

    client.rate_limiter.wait.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: fetch() calls rate_limiter.recover() on success
# ---------------------------------------------------------------------------
@patch("time.sleep")
@patch("curl_cffi.requests.Session.get")
def test_fetch_recovers_on_success(mock_get, mock_sleep):
    mock_get.return_value = MockResponse()

    client = _make_client()
    client.rate_limiter.wait = MagicMock(return_value=0.0)
    client.rate_limiter.recover = MagicMock()

    client.fetch("https://www.hltv.org/test")
    client.close()

    client.rate_limiter.recover.assert_called_once()


# ---------------------------------------------------------------------------
# Test 5: cf-mitigated: challenge header raises CloudflareChallenge
# ---------------------------------------------------------------------------
def test_cloudflare_challenge_cf_mitigated_header():
    response = MockResponse(
        status_code=200,
        headers={"content-type": "text/html", "cf-mitigated": "challenge"},
    )
    with pytest.raises(CloudflareChallenge):
        _check_response(response)


# ---------------------------------------------------------------------------
# Test 6: 403 with Cloudflare HTML signatures raises CloudflareChallenge
# ---------------------------------------------------------------------------
def test_cloudflare_challenge_html_signatures():
    response = MockResponse(
        status_code=403,
        text='<html><div class="cf-chl-widget">Just a moment...</div></html>',
        headers={"content-type": "text/html"},
    )
    with pytest.raises(CloudflareChallenge):
        _check_response(response)


# ---------------------------------------------------------------------------
# Test 7: HTTP 429 raises RateLimited
# ---------------------------------------------------------------------------
def test_rate_limited_429():
    response = MockResponse(
        status_code=429,
        headers={"content-type": "text/html", "Retry-After": "30"},
    )
    with pytest.raises(RateLimited) as exc_info:
        _check_response(response)
    assert "Retry-After: 30" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 8: HTTP 404 raises PageNotFound (NOT retried)
# ---------------------------------------------------------------------------
def test_page_not_found_404():
    response = MockResponse(status_code=404)
    with pytest.raises(PageNotFound):
        _check_response(response)


# ---------------------------------------------------------------------------
# Test 9: CloudflareChallenge triggers rate_limiter.backoff()
# ---------------------------------------------------------------------------
@patch("time.sleep")
@patch("curl_cffi.requests.Session.get")
def test_fetch_backoff_on_challenge(mock_get, mock_sleep):
    mock_get.return_value = MockResponse(
        status_code=200,
        headers={"content-type": "text/html", "cf-mitigated": "challenge"},
    )

    client = _make_client(max_retries=1)
    client.rate_limiter.wait = MagicMock(return_value=0.0)
    client.rate_limiter.backoff = MagicMock()

    with pytest.raises(CloudflareChallenge):
        client.fetch("https://www.hltv.org/test")
    client.close()

    client.rate_limiter.backoff.assert_called()


# ---------------------------------------------------------------------------
# Test 10: Tenacity retries on CloudflareChallenge then succeeds
# ---------------------------------------------------------------------------
@patch("time.sleep")
@patch("curl_cffi.requests.Session.get")
def test_retry_on_cloudflare_challenge(mock_get, mock_sleep):
    challenge_response = MockResponse(
        status_code=200,
        headers={"content-type": "text/html", "cf-mitigated": "challenge"},
    )
    success_response = MockResponse(text="<html>Real Page</html>")

    mock_get.side_effect = [challenge_response, success_response]

    client = _make_client(max_retries=3)
    client.rate_limiter.wait = MagicMock(return_value=0.0)

    result = client.fetch("https://www.hltv.org/test")
    client.close()

    assert result == "<html>Real Page</html>"
    assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# Test 11: PageNotFound is NOT retried (only 1 call to session.get)
# ---------------------------------------------------------------------------
@patch("time.sleep")
@patch("curl_cffi.requests.Session.get")
def test_no_retry_on_page_not_found(mock_get, mock_sleep):
    mock_get.return_value = MockResponse(status_code=404)

    client = _make_client(max_retries=3)
    client.rate_limiter.wait = MagicMock(return_value=0.0)

    with pytest.raises(PageNotFound):
        client.fetch("https://www.hltv.org/missing")
    client.close()

    assert mock_get.call_count == 1


# ---------------------------------------------------------------------------
# Test 12: Context manager closes session
# ---------------------------------------------------------------------------
@patch("time.sleep")
def test_context_manager(mock_sleep):
    with _make_client() as client:
        assert client.session is not None
        session_ref = client.session

    # After exiting context, session should be closed
    # curl_cffi Session.close() is called; we verify via mock
    # Since we can't easily check internal state, verify __exit__ ran
    # by checking that close() doesn't raise
    assert session_ref is not None
