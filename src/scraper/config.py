"""Scraper configuration with sensible defaults for HLTV scraping."""

from dataclasses import dataclass

HLTV_BASE_URL = "https://www.hltv.org"


@dataclass
class ScraperConfig:
    """Configuration for the HLTV scraper.

    All timing values are in seconds. These defaults are tuned for
    HLTV's Cloudflare protection level based on empirical testing.
    """

    # Rate limiting: delay between requests
    min_delay: float = 3.0
    max_delay: float = 8.0

    # Adaptive backoff on challenge/error
    backoff_factor: float = 2.0

    # Gradual recovery on success (multiply current delay by this)
    recovery_factor: float = 0.95

    # Maximum delay ceiling (seconds)
    max_backoff: float = 120.0

    # tenacity stop_after_attempt
    max_retries: int = 5

    # Seconds to wait after navigation for page to load
    page_load_wait: float = 4.0

    # Seconds of extra wait when a challenge is detected (before rechecking)
    challenge_wait: float = 5.0

    # HLTV base URL (single-site scraper)
    base_url: str = HLTV_BASE_URL

    # Persistent data storage
    data_dir: str = "data"
    db_path: str = "data/hltv.db"
