"""Tests for match overview orchestrator (run_match_overview).

Uses mocked HLTVClient with real HTML samples from data/recon/ and real
in-memory database instances for repository/storage. This tests the full
fetch-store-parse-persist pipeline without needing Chrome.
"""

import gzip
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.config import ScraperConfig
from scraper.db import Database
from scraper.discovery_repository import DiscoveryRepository
from scraper.match_overview import run_match_overview
from scraper.repository import MatchRepository
from scraper.storage import HtmlStorage

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"


def load_sample(filename: str) -> str:
    """Load and decompress a gzipped HTML sample."""
    path = RECON_DIR / filename
    if not path.exists():
        pytest.skip(f"Sample not found: {path}")
    return gzip.decompress(path.read_bytes()).decode("utf-8")


# Sample data: match_id -> (filename, relative URL)
SAMPLE_2389951 = {
    "filename": "match-2389951-overview.html.gz",
    "url": "/matches/2389951/vitality-vs-g2-pgl-cluj-napoca-2026",
    "match_id": 2389951,
}

SAMPLE_2380434 = {
    "filename": "match-2380434-overview.html.gz",
    "url": "/matches/2380434/adalyamigos-vs-bounty-hunters-esl-challenger-league-season-49-south-america",
    "match_id": 2380434,
}

SAMPLE_2371389 = {
    "filename": "match-2371389-overview.html.gz",
    "url": "/matches/2371389/some-match-url",
    "match_id": 2371389,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Create an in-memory-style DB at tmp_path with all migrations applied."""
    db = Database(tmp_path / "test.db")
    db.initialize()
    return db


@pytest.fixture
def match_repo(tmp_db):
    """MatchRepository backed by temporary database."""
    return MatchRepository(tmp_db.conn)


@pytest.fixture
def discovery_repo(tmp_db):
    """DiscoveryRepository backed by temporary database."""
    return DiscoveryRepository(tmp_db.conn)


@pytest.fixture
def storage(tmp_path):
    """HtmlStorage using temporary directory."""
    return HtmlStorage(tmp_path / "raw")


@pytest.fixture
def config(tmp_path):
    """ScraperConfig with small batch size for testing."""
    return ScraperConfig(
        data_dir=str(tmp_path),
        overview_batch_size=2,
    )


@pytest.fixture
def mock_client():
    """Mock HLTVClient with async fetch and fetch_many methods."""
    client = MagicMock()
    client.fetch = AsyncMock()

    async def _fetch_many(urls, **kwargs):
        results = []
        for url in urls:
            try:
                result = await client.fetch(url)
                results.append(result)
            except Exception as e:
                results.append(e)
        return results

    client.fetch_many = AsyncMock(side_effect=_fetch_many)
    return client


def seed_pending(discovery_repo, match_id, url):
    """Insert a pending entry into scrape_queue."""
    discovery_repo.conn.execute(
        "INSERT INTO scrape_queue (match_id, url, offset, discovered_at, is_forfeit, status) "
        "VALUES (?, ?, 0, '2026-01-01T00:00:00', 0, 'pending')",
        (match_id, url),
    )
    discovery_repo.conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunMatchOverview:
    """Test the full orchestrator pipeline."""

    @pytest.mark.asyncio
    async def test_fetches_parses_persists_match(
        self, mock_client, match_repo, discovery_repo, storage, config
    ):
        """Seed one pending match, run orchestrator, verify full persistence."""
        sample = SAMPLE_2389951
        html = load_sample(sample["filename"])
        seed_pending(discovery_repo, sample["match_id"], sample["url"])
        mock_client.fetch.return_value = html

        stats = await run_match_overview(
            [mock_client], match_repo, discovery_repo, storage, config
        )

        # Verify stats
        assert stats["batch_size"] == 1
        assert stats["fetched"] == 1
        assert stats["parsed"] == 1
        assert stats["failed"] == 0
        assert stats["fetch_errors"] == 0

        # Verify match persisted
        match = match_repo.get_match(sample["match_id"])
        assert match is not None
        assert match["team1_name"] == "Vitality"
        assert match["team2_name"] == "G2"

        # Verify maps persisted
        maps = match_repo.get_maps(sample["match_id"])
        assert len(maps) > 0

        # Verify vetoes persisted
        vetoes = match_repo.get_vetoes(sample["match_id"])
        assert len(vetoes) > 0

        # Verify queue status updated
        entry = discovery_repo.get_queue_entry(sample["match_id"])
        assert entry["status"] == "scraped"

    @pytest.mark.asyncio
    async def test_no_pending_matches_returns_early(
        self, mock_client, match_repo, discovery_repo, storage, config
    ):
        """No pending matches => stats show 0 work, client.fetch never called."""
        stats = await run_match_overview(
            [mock_client], match_repo, discovery_repo, storage, config
        )

        assert stats["batch_size"] == 0
        assert stats["fetched"] == 0
        assert stats["parsed"] == 0
        assert stats["failed"] == 0
        mock_client.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_failure_skips_failed_continues_others(
        self, mock_client, match_repo, discovery_repo, storage, config
    ):
        """Fetch failure on one match skips it; other match still succeeds."""
        html = load_sample(SAMPLE_2371389["filename"])
        seed_pending(discovery_repo, SAMPLE_2371389["match_id"], SAMPLE_2371389["url"])
        seed_pending(discovery_repo, SAMPLE_2389951["match_id"], SAMPLE_2389951["url"])

        # Queue order is by match_id ASC: 2371389 first, 2389951 second
        # First fetch succeeds (2371389), second raises (2389951)
        mock_client.fetch.side_effect = [html, Exception("Connection timeout")]

        stats = await run_match_overview(
            [mock_client], match_repo, discovery_repo, storage, config
        )

        assert stats["fetch_errors"] == 1
        assert stats["parsed"] == 1

        # Successfully fetched match was parsed
        entry1 = discovery_repo.get_queue_entry(SAMPLE_2371389["match_id"])
        assert entry1["status"] == "scraped"

        # Failed match remains pending
        entry2 = discovery_repo.get_queue_entry(SAMPLE_2389951["match_id"])
        assert entry2["status"] == "pending"

    @pytest.mark.asyncio
    async def test_parse_failure_marks_individual_failed(
        self, mock_client, match_repo, discovery_repo, storage, config
    ):
        """Parse failure on one match marks it failed, other succeeds.

        Note: get_pending_matches orders by match_id ASC, so 2371389 is
        processed first (gets good HTML) and 2389951 second (gets garbage).
        """
        html_good = load_sample(SAMPLE_2389951["filename"])
        html_bad = "<html><body>garbage that will fail parsing</body></html>"

        seed_pending(discovery_repo, SAMPLE_2389951["match_id"], SAMPLE_2389951["url"])
        seed_pending(discovery_repo, SAMPLE_2371389["match_id"], SAMPLE_2371389["url"])

        # Queue order is by match_id ASC: 2371389 first, 2389951 second
        # First fetch gets good HTML, second gets garbage
        mock_client.fetch.side_effect = [html_good, html_bad]

        stats = await run_match_overview(
            [mock_client], match_repo, discovery_repo, storage, config
        )

        assert stats["fetched"] == 2
        assert stats["parsed"] == 1
        assert stats["failed"] == 1

        # Lower match_id (2371389) processed first with good HTML => scraped
        entry1 = discovery_repo.get_queue_entry(SAMPLE_2371389["match_id"])
        assert entry1["status"] == "scraped"
        assert match_repo.get_match(SAMPLE_2371389["match_id"]) is not None

        # Higher match_id (2389951) processed second with garbage HTML => failed
        entry2 = discovery_repo.get_queue_entry(SAMPLE_2389951["match_id"])
        assert entry2["status"] == "failed"

    @pytest.mark.asyncio
    async def test_forfeit_match_persisted_correctly(
        self, mock_client, match_repo, discovery_repo, storage, config
    ):
        """Forfeit match is parsed and persisted; maps include forfeit map."""
        sample = SAMPLE_2380434
        html = load_sample(sample["filename"])
        seed_pending(discovery_repo, sample["match_id"], sample["url"])
        mock_client.fetch.return_value = html

        stats = await run_match_overview(
            [mock_client], match_repo, discovery_repo, storage, config
        )

        assert stats["parsed"] == 1
        assert stats["failed"] == 0

        # Match exists in DB
        match = match_repo.get_match(sample["match_id"])
        assert match is not None

        # Maps include a forfeit map (map_name == "Default")
        maps = match_repo.get_maps(sample["match_id"])
        assert len(maps) > 0
        forfeit_maps = [m for m in maps if m["map_name"] == "Default"]
        assert len(forfeit_maps) > 0

        # Forfeit maps have no mapstatsid
        for m in forfeit_maps:
            assert m["mapstatsid"] is None

        # Queue status updated
        entry = discovery_repo.get_queue_entry(sample["match_id"])
        assert entry["status"] == "scraped"

    @pytest.mark.asyncio
    async def test_stats_dict_returned(
        self, mock_client, match_repo, discovery_repo, storage, config
    ):
        """Returned stats dict has all expected keys."""
        html = load_sample(SAMPLE_2389951["filename"])
        seed_pending(discovery_repo, SAMPLE_2389951["match_id"], SAMPLE_2389951["url"])
        mock_client.fetch.return_value = html

        stats = await run_match_overview(
            [mock_client], match_repo, discovery_repo, storage, config
        )

        assert "batch_size" in stats
        assert "fetched" in stats
        assert "parsed" in stats
        assert "failed" in stats
        assert "fetch_errors" in stats

    @pytest.mark.asyncio
    async def test_date_converted_to_iso(
        self, mock_client, match_repo, discovery_repo, storage, config
    ):
        """Match date column is ISO 8601 format (YYYY-MM-DD)."""
        html = load_sample(SAMPLE_2389951["filename"])
        seed_pending(discovery_repo, SAMPLE_2389951["match_id"], SAMPLE_2389951["url"])
        mock_client.fetch.return_value = html

        await run_match_overview(
            [mock_client], match_repo, discovery_repo, storage, config
        )

        match = match_repo.get_match(SAMPLE_2389951["match_id"])
        assert match is not None
        date_str = match["date"]
        # ISO 8601 date format: YYYY-MM-DD
        assert len(date_str) == 10
        assert date_str[4] == "-"
        assert date_str[7] == "-"
        # Verify it's parseable as a date
        year, month, day = date_str.split("-")
        assert 2000 <= int(year) <= 2030
        assert 1 <= int(month) <= 12
        assert 1 <= int(day) <= 31

    @pytest.mark.asyncio
    async def test_match_overview_quarantines_invalid_match(
        self, mock_client, match_repo, discovery_repo, storage, config
    ):
        """Match with team1_id==team2_id fails validation, gets quarantined."""
        sample = SAMPLE_2389951
        html = load_sample(sample["filename"])
        seed_pending(discovery_repo, sample["match_id"], sample["url"])
        mock_client.fetch.return_value = html

        # Patch the parser to return a result where team1_id == team2_id
        from scraper.match_parser import parse_match_overview as real_parse

        def patched_parse(html_str, match_id):
            result = real_parse(html_str, match_id)
            # Mutate to create invalid data (same team IDs)
            object.__setattr__(result, "team2_id", result.team1_id)
            return result

        with patch(
            "scraper.match_overview.parse_match_overview",
            side_effect=patched_parse,
        ):
            stats = await run_match_overview(
                [mock_client], match_repo, discovery_repo, storage, config
            )

        # Match should fail validation
        assert stats["failed"] == 1
        assert stats["parsed"] == 0

        # Queue entry marked as failed
        entry = discovery_repo.get_queue_entry(sample["match_id"])
        assert entry["status"] == "failed"

        # Quarantine table has a record
        rows = match_repo.conn.execute(
            "SELECT * FROM quarantine WHERE match_id = ?",
            (sample["match_id"],),
        ).fetchall()
        assert len(rows) >= 1
        assert rows[0]["entity_type"] == "MatchModel"
