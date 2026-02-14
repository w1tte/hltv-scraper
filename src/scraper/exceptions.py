"""Custom exception hierarchy for the HLTV scraper.

Exception tree:
    HLTVScraperError
    +-- CloudflareChallenge  (Cloudflare served a challenge page)
    +-- RateLimited          (HTTP 429)
    +-- HLTVFetchError       (non-retriable fetch error)
        +-- PageNotFound     (HTTP 404)
"""

from typing import Optional


class HLTVScraperError(Exception):
    """Base exception for all HLTV scraper errors."""

    def __init__(
        self,
        message: str,
        *,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        self.url = url
        self.status_code = status_code
        super().__init__(message)


class CloudflareChallenge(HLTVScraperError):
    """Cloudflare served a challenge page instead of real content.

    This is a retriable error -- the scraper should back off and retry.
    """

    pass


class RateLimited(HLTVScraperError):
    """Server returned HTTP 429 Too Many Requests.

    This is a retriable error -- respect Retry-After header if present.
    """

    pass


class HLTVFetchError(HLTVScraperError):
    """Non-retriable fetch error (unexpected status code, malformed response).

    Do NOT retry these -- the page is genuinely unavailable or invalid.
    """

    pass


class PageNotFound(HLTVFetchError):
    """HTTP 404 -- the requested page does not exist on HLTV.

    Distinct from HLTVFetchError to allow callers to handle missing
    pages differently (e.g., skip vs. abort).
    """

    pass
