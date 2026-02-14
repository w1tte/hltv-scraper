"""User-Agent rotation with browser fingerprint consistency.

CRITICAL CONSTRAINT: When curl_cffi impersonates a browser (e.g., chrome136),
the TLS fingerprint identifies it as Chrome 136. Sending a Firefox or Safari
User-Agent with a Chrome TLS fingerprint is instantly detected by Cloudflare.
This module enforces that the UA string matches the impersonation target's
browser family.

USAGE NOTE: Real browsers do NOT change User-Agent mid-session. The recommended
pattern is to call get() once per session or per batch of 10-20 requests, NOT
per request. The HLTVClient (Plan 02) should manage this -- this class does
not enforce session-level stickiness itself.
"""

from fake_useragent import UserAgent


class UserAgentRotator:
    """Rotates User-Agent strings consistent with curl_cffi impersonation target.

    Filters fake-useragent output to only return UA strings from the same
    browser family as the curl_cffi impersonation target, preventing
    TLS/UA fingerprint mismatches that Cloudflare detects.
    """

    def __init__(self, impersonate_target: str = "chrome136"):
        self._target = impersonate_target
        self._browser_family = self._get_browser_family(impersonate_target)
        self._ua = UserAgent(
            browsers=[self._browser_family],
            platforms=["desktop"],
            min_version=120.0,
        )

    @staticmethod
    def _get_browser_family(target: str) -> str:
        """Map impersonation target prefix to browser family name.

        Args:
            target: curl_cffi impersonation target string (e.g., "chrome136").

        Returns:
            Browser family name for fake-useragent filtering.
            Defaults to "Chrome" for unknown targets.
        """
        target_lower = target.lower()
        if target_lower.startswith("chrome") or target_lower.startswith("edge"):
            return "Chrome"
        elif target_lower.startswith("safari"):
            return "Safari"
        elif target_lower.startswith("firefox"):
            return "Firefox"
        return "Chrome"

    def get(self) -> str:
        """Return a random UA string from the matching browser family."""
        return self._ua.random

    def get_headers(self) -> dict[str, str]:
        """Return headers dict with User-Agent and optional Client Hints.

        For Chrome-family targets, includes Sec-CH-UA-Platform and
        Sec-CH-UA-Mobile headers that real Chrome browsers send.
        Non-Chrome browsers do not send Client Hints.
        """
        ua_string = self.get()
        headers: dict[str, str] = {"User-Agent": ua_string}

        if self._browser_family == "Chrome":
            headers["Sec-CH-UA-Platform"] = '"Windows"'
            headers["Sec-CH-UA-Mobile"] = "?0"

        return headers
