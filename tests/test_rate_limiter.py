"""Unit tests for the adaptive rate limiter."""

from unittest.mock import patch, AsyncMock

import pytest

from scraper.config import ScraperConfig
from scraper.rate_limiter import RateLimiter


def _make_limiter(**overrides) -> RateLimiter:
    """Create a RateLimiter with optional config overrides."""
    config = ScraperConfig(**overrides)
    return RateLimiter(config)


class TestWait:
    """Tests for RateLimiter.wait()."""

    @pytest.mark.asyncio
    @patch("scraper.rate_limiter.time")
    @patch("scraper.rate_limiter.asyncio.sleep", new_callable=AsyncMock)
    async def test_wait_returns_jittered_delay(self, mock_async_sleep, mock_time):
        """Delay is between [current_delay, current_delay * 1.5]."""
        limiter = _make_limiter(min_delay=4.0)
        limiter._last_request_time = 100.0

        mock_time.monotonic.return_value = 100.0

        delay = await limiter.wait()

        # Jittered delay should be in [4.0, 6.0]
        assert 4.0 <= delay <= 6.0

    @pytest.mark.asyncio
    @patch("scraper.rate_limiter.time")
    @patch("scraper.rate_limiter.asyncio.sleep", new_callable=AsyncMock)
    async def test_wait_accounts_for_elapsed_time(self, mock_async_sleep, mock_time):
        """If 4s elapsed since last request and delay is 5s, sleep is ~1s."""
        mock_time.monotonic.return_value = 104.0

        limiter = _make_limiter(min_delay=5.0)
        limiter._last_request_time = 100.0

        # Force specific jitter value by patching random
        with patch("scraper.rate_limiter.random.uniform", return_value=5.0):
            delay = await limiter.wait()

        # Jittered delay is 5.0, elapsed is 4.0, so sleep should be 1.0
        assert delay == 5.0
        mock_async_sleep.assert_called_once_with(1.0)


class TestBackoff:
    """Tests for RateLimiter.backoff()."""

    def test_backoff_increases_delay(self):
        """After backoff(), current_delay doubles (with default factor 2.0)."""
        limiter = _make_limiter(min_delay=3.0, backoff_factor=2.0)
        initial = limiter.current_delay
        limiter.backoff()
        assert limiter.current_delay == initial * 2.0

    def test_backoff_caps_at_max(self):
        """current_delay never exceeds max_backoff."""
        limiter = _make_limiter(
            min_delay=3.0, backoff_factor=2.0, max_backoff=10.0
        )
        # Backoff several times to exceed the cap
        for _ in range(10):
            limiter.backoff()
        assert limiter.current_delay == 10.0


class TestRecover:
    """Tests for RateLimiter.recover()."""

    def test_recover_decreases_delay(self):
        """After recover(), current_delay decreases."""
        limiter = _make_limiter(min_delay=3.0, recovery_factor=0.95)
        # First increase the delay so there's room to recover
        limiter.backoff()
        elevated = limiter.current_delay
        limiter.recover()
        assert limiter.current_delay < elevated

    def test_recover_floors_at_min(self):
        """current_delay never drops below min_delay."""
        limiter = _make_limiter(min_delay=3.0, recovery_factor=0.5)
        # Recover many times
        for _ in range(100):
            limiter.recover()
        assert limiter.current_delay == 3.0


class TestReset:
    """Tests for RateLimiter.reset()."""

    def test_reset_returns_to_min(self):
        """reset() sets current_delay to min_delay."""
        limiter = _make_limiter(min_delay=3.0)
        # Increase delay first
        limiter.backoff()
        limiter.backoff()
        assert limiter.current_delay > 3.0
        limiter.reset()
        assert limiter.current_delay == 3.0
