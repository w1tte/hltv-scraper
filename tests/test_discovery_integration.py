"""Live integration test for match discovery.

Fetches 1-2 real HLTV results pages, parses entries, and persists
to a temporary database. Requires Chrome + network access.

    python -m pytest tests/test_discovery_integration.py -v -s -m integration
"""

import pytest

from scraper.config import ScraperConfig
from scraper.db import Database
from scraper.discovery import run_discovery
from scraper.discovery_repository import DiscoveryRepository
from scraper.http_client import HLTVClient
from scraper.storage import HtmlStorage

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_discover_first_two_pages(tmp_path):
    """Fetch offset 0 and 100, verify matches persisted and HTML archived."""
    config = ScraperConfig(
        max_offset=100,  # Only 2 pages (offset 0 and 100)
        data_dir=str(tmp_path),
        db_path=str(tmp_path / "test.db"),
    )

    db = Database(config.db_path)
    db.initialize()

    storage = HtmlStorage(tmp_path / "raw")
    repo = DiscoveryRepository(db.conn)

    try:
        async with HLTVClient(config) as client:
            stats = await run_discovery([client], repo, storage, config)

        # Verify stats
        assert stats["pages_fetched"] == 2
        assert stats["pages_skipped"] == 0
        assert stats["errors"] == 0
        # Allow slight variation (unlikely but possible on edge pages)
        assert stats["matches_found"] >= 180, (
            f"Expected ~200 matches, got {stats['matches_found']}"
        )

        # Verify database
        assert repo.count_total() >= 180
        assert repo.count_pending() >= 180

        # Verify progress tracking
        completed = repo.get_completed_offsets()
        assert completed == {0, 100}

        # Verify resume: run again, should skip both pages
        async with HLTVClient(config) as client2:
            stats2 = await run_discovery([client2], repo, storage, config)

        assert stats2["pages_fetched"] == 0
        assert stats2["pages_skipped"] == 2
        assert stats2["matches_found"] == 0

    finally:
        db.close()
