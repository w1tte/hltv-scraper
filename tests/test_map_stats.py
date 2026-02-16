"""Tests for map stats extraction orchestrator (run_map_stats).

Uses mocked HLTVClient with real HTML samples from data/recon/ and real
in-memory database instances for repository/storage.  This tests the full
fetch-store-parse-persist pipeline without needing Chrome.
"""

import gzip
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.config import ScraperConfig
from scraper.db import Database
from scraper.map_stats import run_map_stats
from scraper.repository import MatchRepository
from scraper.storage import HtmlStorage

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"


def load_sample(filename: str) -> str:
    """Load and decompress a gzipped HTML sample."""
    path = RECON_DIR / filename
    if not path.exists():
        pytest.skip(f"Sample not found: {path}")
    return gzip.decompress(path.read_bytes()).decode("utf-8")


# Sample: mapstatsid 164779, Rating 3.0 standard match
SAMPLE_MAPSTATSID = 164779
SAMPLE_FILENAME = "mapstats-164779-stats.html.gz"
SAMPLE_MATCH_ID = 2371389


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary DB with all migrations applied."""
    db = Database(tmp_path / "test.db")
    db.initialize()
    return db


@pytest.fixture
def match_repo(tmp_db):
    """MatchRepository backed by temporary database."""
    return MatchRepository(tmp_db.conn)


@pytest.fixture
def storage(tmp_path):
    """HtmlStorage using temporary directory."""
    return HtmlStorage(tmp_path / "raw")


@pytest.fixture
def config(tmp_path):
    """ScraperConfig with small batch size for testing."""
    return ScraperConfig(
        data_dir=str(tmp_path),
        map_stats_batch_size=2,
    )


@pytest.fixture
def mock_client():
    """Mock HLTVClient with async fetch and fetch_many methods."""
    client = MagicMock()
    client.fetch = AsyncMock()

    async def _fetch_many(urls):
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


# ---------------------------------------------------------------------------
# Seed helper
# ---------------------------------------------------------------------------


def seed_match_with_maps(match_repo, match_id, mapstatsids):
    """Insert a match and maps into the DB so get_pending_map_stats finds them.

    Creates a minimal match record and one map row per mapstatsid.
    Map numbers are 1-based indices matching the list order.
    """
    conn = match_repo.conn
    ts = "2026-01-15T00:00:00"
    url = "https://www.hltv.org/matches/" + str(match_id)
    conn.execute(
        "INSERT INTO matches ("
        "  match_id, date, team1_id, team1_name, team2_id, team2_name,"
        "  scraped_at, updated_at, source_url, parser_version"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (match_id, "2026-01-15", 4608, "Natus Vincere", 5995, "G2",
         ts, ts, url, "test_seed"),
    )
    for idx, msid in enumerate(mapstatsids, start=1):
        conn.execute(
            "INSERT INTO maps ("
            "  match_id, map_number, mapstatsid,"
            "  scraped_at, updated_at, source_url, parser_version"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (match_id, idx, msid, ts, ts, url, "test_seed"),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunMapStats:
    """Test the full map stats orchestrator pipeline."""

    @pytest.mark.asyncio
    async def test_fetches_parses_persists_map_stats(
        self, mock_client, match_repo, storage, config
    ):
        """Seed one pending map, run orchestrator, verify full persistence."""
        html = load_sample(SAMPLE_FILENAME)
        seed_match_with_maps(match_repo, SAMPLE_MATCH_ID, [SAMPLE_MAPSTATSID])
        mock_client.fetch.return_value = html

        stats = await run_map_stats(mock_client, match_repo, storage, config)

        # Verify stats
        assert stats["batch_size"] == 1
        assert stats["fetched"] == 1
        assert stats["parsed"] == 1
        assert stats["failed"] == 0
        assert stats["fetch_errors"] == 0

        # Verify player_stats rows exist (10 players per map)
        player_stats = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        assert len(player_stats) == 10

        # Verify round_history exists
        rounds = match_repo.conn.execute(
            "SELECT * FROM round_history WHERE match_id = ? AND map_number = ?",
            (SAMPLE_MATCH_ID, 1),
        ).fetchall()
        assert len(rounds) > 0

        # Verify map no longer pending
        pending = match_repo.get_pending_map_stats()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_no_pending_maps_returns_early(
        self, mock_client, match_repo, storage, config
    ):
        """No pending maps => stats show 0 work, client.fetch never called."""
        stats = await run_map_stats(mock_client, match_repo, storage, config)

        assert stats["batch_size"] == 0
        assert stats["fetched"] == 0
        assert stats["parsed"] == 0
        assert stats["failed"] == 0
        mock_client.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_failure_skips_failed_continues_others(
        self, mock_client, match_repo, storage, config
    ):
        """Fetch failure on second map skips it; first map still succeeds."""
        html = load_sample(SAMPLE_FILENAME)
        seed_match_with_maps(
            match_repo, SAMPLE_MATCH_ID, [SAMPLE_MAPSTATSID, 999999]
        )

        # First fetch succeeds, second raises
        mock_client.fetch.side_effect = [html, Exception("Connection timeout")]

        stats = await run_map_stats(mock_client, match_repo, storage, config)

        assert stats["fetch_errors"] == 1
        assert stats["parsed"] == 1

        # Player stats exist for the successfully fetched map
        player_stats = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        assert len(player_stats) == 10

        # Failed map still pending
        pending = match_repo.get_pending_map_stats()
        assert len(pending) == 1
        assert pending[0]["mapstatsid"] == 999999

    @pytest.mark.asyncio
    async def test_parse_failure_continues_batch(
        self, mock_client, match_repo, storage, config
    ):
        """Parse failure on one map: other maps succeed, failed map stays pending."""
        html_good = load_sample(SAMPLE_FILENAME)
        html_bad = "<html><body>garbage that will fail parsing</body></html>"

        seed_match_with_maps(
            match_repo, SAMPLE_MATCH_ID, [SAMPLE_MAPSTATSID, 999999]
        )

        # Queue order is by (match_id, map_number): map_number 1 first, 2 second
        # map_number 1 = SAMPLE_MAPSTATSID (good), map_number 2 = 999999 (bad)
        mock_client.fetch.side_effect = [html_good, html_bad]

        stats = await run_map_stats(mock_client, match_repo, storage, config)

        assert stats["fetched"] == 2
        assert stats["parsed"] == 1
        assert stats["failed"] == 1

        # Player stats exist for the successfully parsed map (map_number=1)
        player_stats = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        assert len(player_stats) == 10

        # Failed map (map_number=2) still appears as pending (no player_stats)
        pending = match_repo.get_pending_map_stats()
        assert len(pending) == 1
        assert pending[0]["mapstatsid"] == 999999

    @pytest.mark.asyncio
    async def test_raw_html_stored(
        self, mock_client, match_repo, storage, config
    ):
        """Raw HTML is saved to storage before parsing."""
        html = load_sample(SAMPLE_FILENAME)
        seed_match_with_maps(match_repo, SAMPLE_MATCH_ID, [SAMPLE_MAPSTATSID])
        mock_client.fetch.return_value = html

        await run_map_stats(mock_client, match_repo, storage, config)

        # Verify storage has the file
        assert storage.exists(
            match_id=SAMPLE_MATCH_ID,
            page_type="map_stats",
            mapstatsid=SAMPLE_MAPSTATSID,
        )

        # Verify it loads back correctly
        loaded = storage.load(
            match_id=SAMPLE_MATCH_ID,
            page_type="map_stats",
            mapstatsid=SAMPLE_MAPSTATSID,
        )
        assert len(loaded) > 10000  # Real HTML is large

    @pytest.mark.asyncio
    async def test_stats_dict_has_all_keys(
        self, mock_client, match_repo, storage, config
    ):
        """Returned stats dict has all expected keys, even on empty batch."""
        stats = await run_map_stats(mock_client, match_repo, storage, config)

        assert "batch_size" in stats
        assert "fetched" in stats
        assert "parsed" in stats
        assert "failed" in stats
        assert "fetch_errors" in stats

    @pytest.mark.asyncio
    async def test_map_stats_quarantines_invalid_stats(
        self, mock_client, match_repo, storage, config
    ):
        """Player with kills=-1 is quarantined; other valid players still persist."""
        html = load_sample(SAMPLE_FILENAME)
        seed_match_with_maps(match_repo, SAMPLE_MATCH_ID, [SAMPLE_MAPSTATSID])
        mock_client.fetch.return_value = html

        # Patch parser to corrupt one player's kills to -1
        from scraper.map_stats_parser import parse_map_stats as real_parse

        def patched_parse(html_str, mapstatsid):
            result = real_parse(html_str, mapstatsid)
            # Corrupt first player's kills to an invalid value
            object.__setattr__(result.players[0], "kills", -1)
            return result

        with patch(
            "scraper.map_stats.parse_map_stats",
            side_effect=patched_parse,
        ):
            stats = await run_map_stats(mock_client, match_repo, storage, config)

        # Map should still parse (partial data persisted)
        assert stats["parsed"] == 1
        assert stats["failed"] == 0

        # 9 valid players persisted (1 quarantined)
        player_stats = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        assert len(player_stats) == 9

        # Quarantine table has the invalid player
        rows = match_repo.conn.execute(
            "SELECT * FROM quarantine WHERE match_id = ? AND entity_type = ?",
            (SAMPLE_MATCH_ID, "PlayerStatsModel"),
        ).fetchall()
        assert len(rows) == 1
