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
    min_delay: float = 0.08
    max_delay: float = 3.0

    # Adaptive backoff on challenge/error
    backoff_factor: float = 2.0

    # Gradual recovery on success (multiply current delay by this)
    # 0.85 recovers ~3× faster than 0.95 after a backoff spike
    recovery_factor: float = 0.85

    # Maximum delay ceiling (seconds)
    max_backoff: float = 30.0

    # tenacity stop_after_attempt
    max_retries: int = 5

    # Seconds to wait after navigation for page to load (fallback retries).
    # Ready-selector polling is the real gate; this is only used for
    # content-marker misses and short-extraction retries.
    page_load_wait: float = 0.4

    # Save raw HTML to disk for debugging/resumability.
    # Set to False for large production runs to avoid 250k+ gzip files and
    # blocking I/O overhead (~10 sync writes per match).
    save_html: bool = True

    # Number of browser tabs per instance.
    # With 8 workers × 2 tabs = 16 concurrent fetches, which maximises
    # throughput while keeping nav_lock contention low within each browser.
    concurrent_tabs: int = 2

    # CDP navigation timeout (asyncio.wait_for around tab.get())
    navigation_timeout: float = 30.0

    # CDP evaluate timeout (asyncio.wait_for around tab.evaluate())
    evaluate_timeout: float = 15.0

    # Hard ceiling per match — defense-in-depth (5 minutes)
    per_match_timeout: float = 300.0

    # Seconds to poll for Cloudflare challenge to clear during fetches
    challenge_wait: float = 90.0

    # HLTV base URL (single-site scraper)
    base_url: str = HLTV_BASE_URL

    # Persistent data storage
    data_dir: str = "data"
    db_path: str = "data/hltv.db"

    # Discovery pagination
    game_type: str = "CS2"           # Game filter: CS2, CSGO, or CS16
    max_offset: int = 25000          # Last offset to paginate to (exclusive)
    results_per_page: int = 100      # Entries per results page (HLTV constant)

    # Match overview batch size
    overview_batch_size: int = 10    # Matches to fetch per batch before parsing

    # Map stats batch size (maps per batch, not matches)
    map_stats_batch_size: int = 10

    # Maps per batch for performance+economy extraction
    perf_economy_batch_size: int = 10

    # Proxy configuration
    proxy_file: str | None = None      # Path to file with one proxy per line

    # Pipeline orchestration
    start_offset: int = 0              # Start offset for results pagination
    consecutive_failure_threshold: int = 3  # Halt pipeline after N consecutive failures
    stage_poll_interval: float = 5.0   # Seconds between polls when downstream stage has no work
