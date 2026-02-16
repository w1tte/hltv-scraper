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

    # Discovery pagination
    max_offset: int = 9900           # Last offset to paginate to (inclusive)
    results_per_page: int = 100      # Entries per results page (HLTV constant)

    # Match overview batch size
    overview_batch_size: int = 10    # Matches to fetch per batch before parsing

    # Map stats batch size (maps per batch, not matches)
    map_stats_batch_size: int = 10

    # Maps per batch for performance+economy extraction
    perf_economy_batch_size: int = 10

    # Pipeline orchestration
    start_offset: int = 0              # Start offset for results pagination
    consecutive_failure_threshold: int = 3  # Halt pipeline after N consecutive failures
