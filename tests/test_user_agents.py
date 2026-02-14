"""Unit tests for User-Agent rotation with fingerprint consistency."""

from scraper.user_agents import UserAgentRotator


class TestBrowserFamilyMatching:
    """Tests that UA strings match the impersonation target."""

    def test_chrome_target_returns_chrome_ua(self):
        """UA string contains 'Chrome/' when target is 'chrome136'."""
        rotator = UserAgentRotator(impersonate_target="chrome136")
        ua = rotator.get()
        assert "Chrome/" in ua, f"Expected Chrome UA, got: {ua}"

    def test_safari_target_returns_safari_ua(self):
        """UA string contains 'Safari' when target is 'safari17_3'."""
        rotator = UserAgentRotator(impersonate_target="safari17_3")
        ua = rotator.get()
        assert "Safari" in ua, f"Expected Safari UA, got: {ua}"

    def test_unknown_target_defaults_to_chrome(self):
        """Unknown target falls back to Chrome family."""
        rotator = UserAgentRotator(impersonate_target="unknown_browser_99")
        ua = rotator.get()
        assert "Chrome/" in ua, f"Expected Chrome UA for unknown target, got: {ua}"


class TestClientHintsHeaders:
    """Tests for Sec-CH-UA headers in get_headers()."""

    def test_get_headers_includes_client_hints_for_chrome(self):
        """Headers dict has Sec-CH-UA-Platform and Sec-CH-UA-Mobile for Chrome."""
        rotator = UserAgentRotator(impersonate_target="chrome136")
        headers = rotator.get_headers()

        assert "User-Agent" in headers
        assert "Sec-CH-UA-Platform" in headers
        assert headers["Sec-CH-UA-Platform"] == '"Windows"'
        assert "Sec-CH-UA-Mobile" in headers
        assert headers["Sec-CH-UA-Mobile"] == "?0"

    def test_get_headers_no_client_hints_for_non_chrome(self):
        """Safari/Firefox targets do NOT get Client Hints headers."""
        rotator = UserAgentRotator(impersonate_target="safari17_3")
        headers = rotator.get_headers()

        assert "User-Agent" in headers
        assert "Sec-CH-UA-Platform" not in headers
        assert "Sec-CH-UA-Mobile" not in headers


class TestRotation:
    """Tests that rotation produces diverse UA strings."""

    def test_different_calls_can_return_different_uas(self):
        """Call get() 10 times, at least 2 unique values (proves rotation)."""
        rotator = UserAgentRotator(impersonate_target="chrome136")
        results = {rotator.get() for _ in range(10)}
        assert len(results) >= 2, (
            f"Expected at least 2 unique UAs from 10 calls, got {len(results)}: {results}"
        )
