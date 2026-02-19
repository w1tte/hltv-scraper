"""Tests for performance + economy extraction orchestrator.

Uses mocked HLTVClient with real HTML samples from data/recon/ and real
in-memory database instances for repository/storage.  Tests the full
fetch-store-parse-persist pipeline for both performance and economy pages
without needing Chrome.
"""

import gzip
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.config import ScraperConfig
from scraper.db import Database
from scraper.map_stats import run_map_stats
from scraper.map_stats_parser import parse_map_stats
from scraper.performance_economy import run_performance_economy
from scraper.repository import MatchRepository
from scraper.storage import HtmlStorage

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"

# All samples use mapstatsid 164779 (Rating 3.0 standard match)
SAMPLE_MAPSTATSID = 164779
SAMPLE_MATCH_ID = 2371389
MAP_STATS_SAMPLE = "mapstats-164779-stats.html.gz"
PERF_SAMPLE = "performance-164779.html.gz"
ECON_SAMPLE = "economy-164779.html.gz"


def load_sample(filename: str) -> str:
    """Load and decompress a gzipped HTML sample."""
    path = RECON_DIR / filename
    if not path.exists():
        pytest.skip(f"Sample not found: {path}")
    return gzip.decompress(path.read_bytes()).decode("utf-8")


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
        perf_economy_batch_size=5,
    )


@pytest.fixture
def mock_client():
    """Mock HLTVClient with async fetch that returns correct HTML by URL."""
    perf_html = load_sample(PERF_SAMPLE)
    econ_html = load_sample(ECON_SAMPLE)

    client = MagicMock()

    def fetch_side_effect(url):
        if "/performance/" in url:
            return perf_html
        elif "/economy/" in url:
            return econ_html
        else:
            raise ValueError(f"Unexpected URL: {url}")

    client.fetch = AsyncMock(side_effect=fetch_side_effect)

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


# ---------------------------------------------------------------------------
# Seed helper
# ---------------------------------------------------------------------------


def seed_match_with_map_stats(
    match_repo, match_id, mapstatsid, map_number=1
):
    """Seed a match + map + player_stats + round_history (simulates Phase 6).

    Parses the real map stats sample to get accurate player_stats and
    round_history rows, then inserts them via the repository.
    """
    conn = match_repo.conn
    ts = "2026-01-15T00:00:00"
    url = f"https://www.hltv.org/matches/{match_id}"

    # Insert match record with team names matching the sample
    conn.execute(
        "INSERT INTO matches ("
        "  match_id, date, team1_id, team1_name, team2_id, team2_name,"
        "  scraped_at, updated_at, source_url, parser_version"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (match_id, "2026-01-15", 4608, "Natus Vincere", 5995, "G2",
         ts, ts, url, "test_seed"),
    )

    # Insert map record
    conn.execute(
        "INSERT INTO maps ("
        "  match_id, map_number, mapstatsid,"
        "  scraped_at, updated_at, source_url, parser_version"
        ") VALUES (?, ?, ?, ?, ?, ?, ?)",
        (match_id, map_number, mapstatsid, ts, ts, url, "test_seed"),
    )

    # Parse real map stats sample to get player_stats and round_history
    map_stats_html = load_sample(MAP_STATS_SAMPLE)
    result = parse_map_stats(map_stats_html, mapstatsid)

    # Insert player_stats rows (Phase 6 style -- kpr=None)
    for ps in result.players:
        conn.execute(
            "INSERT INTO player_stats ("
            "  match_id, map_number, player_id, player_name, team_id,"
            "  kills, deaths, assists, flash_assists, hs_kills, kd_diff,"
            "  adr, kast, fk_diff, rating,"
            "  kpr, dpr,"
            "  opening_kills, opening_deaths, multi_kills, clutch_wins,"
            "  traded_deaths, round_swing, mk_rating,"
            "  scraped_at, updated_at, source_url, parser_version"
            ") VALUES ("
            "  ?, ?, ?, ?, ?,"
            "  ?, ?, ?, ?, ?, ?,"
            "  ?, ?, ?, ?,"
            "  ?, ?,"
            "  ?, ?, ?, ?,"
            "  ?, ?, ?,"
            "  ?, ?, ?, ?"
            ")",
            (
                match_id, map_number, ps.player_id, ps.player_name, ps.team_id,
                ps.kills, ps.deaths, ps.assists, ps.flash_assists,
                ps.hs_kills, ps.kd_diff,
                ps.adr, ps.kast, ps.fk_diff, ps.rating,
                None, None,  # kpr, dpr -- Phase 7
                ps.opening_kills, ps.opening_deaths, ps.multi_kills,
                ps.clutch_wins, ps.traded_deaths, ps.round_swing,
                None,  # mk_rating -- Phase 7
                ts, ts, url, "test_seed",
            ),
        )

    # Insert round_history rows
    for ro in result.rounds:
        conn.execute(
            "INSERT INTO round_history ("
            "  match_id, map_number, round_number,"
            "  winner_side, win_type, winner_team_id,"
            "  scraped_at, updated_at, source_url, parser_version"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                match_id, map_number, ro.round_number,
                ro.winner_side, ro.win_type, ro.winner_team_id,
                ts, ts, url, "test_seed",
            ),
        )

    conn.commit()

    # Return the parsed result for test assertions
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Test the full orchestrator pipeline with valid data."""

    @pytest.mark.asyncio
    async def test_processes_pending_map(
        self, mock_client, match_repo, storage, config
    ):
        """Seed one pending map, run orchestrator, verify stats."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)

        stats = await run_performance_economy(
            [mock_client], match_repo, storage, config
        )

        assert stats["batch_size"] == 1
        assert stats["fetched"] == 1
        assert stats["parsed"] == 1
        assert stats["failed"] == 0
        assert stats["fetch_errors"] == 0

    @pytest.mark.asyncio
    async def test_kpr_populated(
        self, mock_client, match_repo, storage, config
    ):
        """After run, player_stats rows have non-None kpr."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)
        await run_performance_economy([mock_client], match_repo, storage, config)

        rows = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        assert len(rows) == 10
        for row in rows:
            assert row["kpr"] is not None, (
                f"kpr still NULL for player {row['player_id']}"
            )

    @pytest.mark.asyncio
    async def test_dpr_populated(
        self, mock_client, match_repo, storage, config
    ):
        """After run, player_stats rows have non-None dpr."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)
        await run_performance_economy([mock_client], match_repo, storage, config)

        rows = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        for row in rows:
            assert row["dpr"] is not None, (
                f"dpr still NULL for player {row['player_id']}"
            )

    @pytest.mark.asyncio
    async def test_mk_rating_populated(
        self, mock_client, match_repo, storage, config
    ):
        """After run, rows have mk_rating non-None."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)
        await run_performance_economy([mock_client], match_repo, storage, config)

        rows = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        for row in rows:
            assert row["mk_rating"] is not None, (
                f"mk_rating still NULL for player {row['player_id']}"
            )

    @pytest.mark.asyncio
    async def test_economy_rows_created(
        self, mock_client, match_repo, storage, config
    ):
        """After run, economy table has rows for this match/map."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)
        await run_performance_economy([mock_client], match_repo, storage, config)

        rows = match_repo.conn.execute(
            "SELECT * FROM economy WHERE match_id = ? AND map_number = ?",
            (SAMPLE_MATCH_ID, 1),
        ).fetchall()
        assert len(rows) > 0

    @pytest.mark.asyncio
    async def test_economy_has_both_teams(
        self, mock_client, match_repo, storage, config
    ):
        """Economy rows contain entries for 2 different team_ids."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)
        await run_performance_economy([mock_client], match_repo, storage, config)

        rows = match_repo.conn.execute(
            "SELECT DISTINCT team_id FROM economy "
            "WHERE match_id = ? AND map_number = ?",
            (SAMPLE_MATCH_ID, 1),
        ).fetchall()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_kill_matrix_created(
        self, mock_client, match_repo, storage, config
    ):
        """After run, kill_matrix table has rows for this match/map."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)
        await run_performance_economy([mock_client], match_repo, storage, config)

        rows = match_repo.conn.execute(
            "SELECT * FROM kill_matrix WHERE match_id = ? AND map_number = ?",
            (SAMPLE_MATCH_ID, 1),
        ).fetchall()
        assert len(rows) > 0

    @pytest.mark.asyncio
    async def test_kill_matrix_three_types(
        self, mock_client, match_repo, storage, config
    ):
        """Kill matrix has entries for 'all', 'first_kill', and 'awp' types."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)
        await run_performance_economy([mock_client], match_repo, storage, config)

        rows = match_repo.conn.execute(
            "SELECT DISTINCT matrix_type FROM kill_matrix "
            "WHERE match_id = ? AND map_number = ?",
            (SAMPLE_MATCH_ID, 1),
        ).fetchall()
        types = {r[0] for r in rows}
        assert types == {"all", "first_kill", "awp"}

    @pytest.mark.asyncio
    async def test_existing_stats_preserved(
        self, mock_client, match_repo, storage, config
    ):
        """CRITICAL: Phase 6 values are NOT overwritten by Phase 7 update."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)

        # Snapshot before Phase 7
        before = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        before_by_pid = {s["player_id"]: s for s in before}

        # Run Phase 7
        await run_performance_economy([mock_client], match_repo, storage, config)

        # Verify after Phase 7
        after = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        for row in after:
            pid = row["player_id"]
            prev = before_by_pid[pid]

            # Phase 6 fields must be preserved exactly
            assert row["kills"] == prev["kills"], f"kills overwritten for {pid}"
            assert row["deaths"] == prev["deaths"], f"deaths overwritten for {pid}"
            assert row["assists"] == prev["assists"], f"assists overwritten for {pid}"
            assert row["flash_assists"] == prev["flash_assists"], (
                f"flash_assists overwritten for {pid}"
            )
            assert row["hs_kills"] == prev["hs_kills"], (
                f"hs_kills overwritten for {pid}"
            )
            assert row["kd_diff"] == prev["kd_diff"], (
                f"kd_diff overwritten for {pid}"
            )
            assert row["adr"] == prev["adr"], f"adr overwritten for {pid}"
            assert row["kast"] == prev["kast"], f"kast overwritten for {pid}"
            assert row["fk_diff"] == prev["fk_diff"], (
                f"fk_diff overwritten for {pid}"
            )
            assert row["team_id"] == prev["team_id"], (
                f"team_id overwritten for {pid}"
            )
            assert row["opening_kills"] == prev["opening_kills"], (
                f"opening_kills overwritten for {pid}"
            )
            assert row["opening_deaths"] == prev["opening_deaths"], (
                f"opening_deaths overwritten for {pid}"
            )
            assert row["multi_kills"] == prev["multi_kills"], (
                f"multi_kills overwritten for {pid}"
            )
            assert row["clutch_wins"] == prev["clutch_wins"], (
                f"clutch_wins overwritten for {pid}"
            )
            assert row["traded_deaths"] == prev["traded_deaths"], (
                f"traded_deaths overwritten for {pid}"
            )

            # Phase 7 fields must NOW be populated
            assert row["kpr"] is not None, f"kpr still NULL for {pid}"
            assert row["dpr"] is not None, f"dpr still NULL for {pid}"


class TestEconomyFKFiltering:
    """Test that economy rows respect round_history FK constraint."""

    @pytest.mark.asyncio
    async def test_economy_rounds_match_round_history(
        self, mock_client, match_repo, storage, config
    ):
        """Every economy round_number exists in round_history."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)
        await run_performance_economy([mock_client], match_repo, storage, config)

        econ_rounds = match_repo.conn.execute(
            "SELECT DISTINCT round_number FROM economy "
            "WHERE match_id = ? AND map_number = ?",
            (SAMPLE_MATCH_ID, 1),
        ).fetchall()
        econ_round_set = {r[0] for r in econ_rounds}

        valid_rounds = match_repo.get_valid_round_numbers(
            SAMPLE_MATCH_ID, map_number=1
        )
        assert econ_round_set.issubset(valid_rounds)

    @pytest.mark.asyncio
    async def test_economy_skips_invalid_rounds(
        self, mock_client, match_repo, storage, config
    ):
        """Economy rows skip round numbers not in round_history (no FK error)."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)

        # Delete some round_history rows to simulate fewer valid rounds
        match_repo.conn.execute(
            "DELETE FROM round_history "
            "WHERE match_id = ? AND map_number = ? AND round_number > 20",
            (SAMPLE_MATCH_ID, 1),
        )
        match_repo.conn.commit()

        # Run -- should NOT raise FK errors
        stats = await run_performance_economy(
            [mock_client], match_repo, storage, config
        )
        assert stats["parsed"] == 1

        # Verify economy rounds are subset of remaining round_history
        econ_rounds = match_repo.conn.execute(
            "SELECT DISTINCT round_number FROM economy "
            "WHERE match_id = ? AND map_number = ?",
            (SAMPLE_MATCH_ID, 1),
        ).fetchall()
        econ_round_set = {r[0] for r in econ_rounds}

        valid_rounds = match_repo.get_valid_round_numbers(
            SAMPLE_MATCH_ID, map_number=1
        )
        assert econ_round_set.issubset(valid_rounds)
        # Rounds > 20 should NOT be in economy
        assert all(r <= 20 for r in econ_round_set)


class TestFetchFailure:
    """Test batch discard on fetch failure."""

    @pytest.mark.asyncio
    async def test_fetch_error_discards_batch(
        self, match_repo, storage, config
    ):
        """Fetch failure returns fetch_errors>=1, parsed=0."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)

        client = MagicMock()
        client.fetch = AsyncMock(side_effect=Exception("Connection timeout"))

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

        stats = await run_performance_economy(
            [client], match_repo, storage, config
        )

        assert stats["fetch_errors"] >= 1
        assert stats["parsed"] == 0

    @pytest.mark.asyncio
    async def test_no_data_persisted_on_fetch_error(
        self, match_repo, storage, config
    ):
        """kpr remains NULL, no economy rows after fetch failure."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)

        client = MagicMock()
        client.fetch = AsyncMock(side_effect=Exception("Connection timeout"))

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

        await run_performance_economy([client], match_repo, storage, config)

        # kpr still NULL
        rows = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        for row in rows:
            assert row["kpr"] is None

        # No economy rows
        econ = match_repo.conn.execute(
            "SELECT COUNT(*) FROM economy WHERE match_id = ?",
            (SAMPLE_MATCH_ID,),
        ).fetchone()[0]
        assert econ == 0


class TestParseFailure:
    """Test per-map parse failure handling."""

    @pytest.mark.asyncio
    async def test_parse_error_continues(
        self, match_repo, storage, config
    ):
        """Parse failure on one map, valid data for another: failed=1, parsed=1."""
        # Seed two maps
        seed_match_with_map_stats(
            match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID, map_number=1
        )
        # Seed second map (different mapstatsid) using same data structure
        conn = match_repo.conn
        ts = "2026-01-15T00:00:00"
        url = f"https://www.hltv.org/matches/{SAMPLE_MATCH_ID}"
        conn.execute(
            "INSERT INTO maps ("
            "  match_id, map_number, mapstatsid,"
            "  scraped_at, updated_at, source_url, parser_version"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (SAMPLE_MATCH_ID, 2, 999999, ts, ts, url, "test_seed"),
        )
        # Seed player_stats for map 2 from same parsed data
        map_stats_html = load_sample(MAP_STATS_SAMPLE)
        result = parse_map_stats(map_stats_html, 999999)
        for ps in result.players:
            conn.execute(
                "INSERT INTO player_stats ("
                "  match_id, map_number, player_id, player_name, team_id,"
                "  kills, deaths, assists, flash_assists, hs_kills, kd_diff,"
                "  adr, kast, fk_diff, rating,"
                "  kpr, dpr,"
                "  opening_kills, opening_deaths, multi_kills, clutch_wins,"
                "  traded_deaths, round_swing, mk_rating,"
                "  scraped_at, updated_at, source_url, parser_version"
                ") VALUES ("
                "  ?, ?, ?, ?, ?,"
                "  ?, ?, ?, ?, ?, ?,"
                "  ?, ?, ?, ?,"
                "  ?, ?,"
                "  ?, ?, ?, ?,"
                "  ?, ?, ?,"
                "  ?, ?, ?, ?"
                ")",
                (
                    SAMPLE_MATCH_ID, 2, ps.player_id, ps.player_name,
                    ps.team_id,
                    ps.kills, ps.deaths, ps.assists, ps.flash_assists,
                    ps.hs_kills, ps.kd_diff,
                    ps.adr, ps.kast, ps.fk_diff, ps.rating,
                    None, None,
                    ps.opening_kills, ps.opening_deaths, ps.multi_kills,
                    ps.clutch_wins, ps.traded_deaths, ps.round_swing,
                    None,
                    ts, ts, url, "test_seed",
                ),
            )
        for ro in result.rounds:
            conn.execute(
                "INSERT INTO round_history ("
                "  match_id, map_number, round_number,"
                "  winner_side, win_type, winner_team_id,"
                "  scraped_at, updated_at, source_url, parser_version"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    SAMPLE_MATCH_ID, 2, ro.round_number,
                    ro.winner_side, ro.win_type, ro.winner_team_id,
                    ts, ts, url, "test_seed",
                ),
            )
        conn.commit()

        perf_html = load_sample(PERF_SAMPLE)
        econ_html = load_sample(ECON_SAMPLE)
        bad_html = "<html><body>garbage</body></html>"

        # Map 1 (mapstatsid 164779) gets valid HTML
        # Map 2 (mapstatsid 999999) gets garbage HTML
        call_count = 0

        def fetch_side_effect(url):
            nonlocal call_count
            call_count += 1
            if "/999999/" in url:
                return bad_html
            if "/performance/" in url:
                return perf_html
            if "/economy/" in url:
                return econ_html
            return bad_html

        client = MagicMock()
        client.fetch = AsyncMock(side_effect=fetch_side_effect)

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

        stats = await run_performance_economy(
            [client], match_repo, storage, config
        )

        assert stats["fetched"] == 2
        assert stats["parsed"] == 1
        assert stats["failed"] == 1


class TestNoPendingMaps:
    """Test behavior when no maps are pending."""

    @pytest.mark.asyncio
    async def test_empty_batch(
        self, mock_client, match_repo, storage, config
    ):
        """No seeded data => batch_size=0, no fetches."""
        stats = await run_performance_economy(
            [mock_client], match_repo, storage, config
        )

        assert stats["batch_size"] == 0
        assert stats["fetched"] == 0
        assert stats["parsed"] == 0
        assert stats["failed"] == 0
        mock_client.fetch.assert_not_called()


class TestAlreadyProcessed:
    """Test that maps already processed by Phase 7 are skipped."""

    @pytest.mark.asyncio
    async def test_skips_already_processed(
        self, mock_client, match_repo, storage, config
    ):
        """Map with non-NULL kpr is not returned by get_pending_perf_economy."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)

        # Manually update kpr to non-None (simulate Phase 7 already ran)
        match_repo.conn.execute(
            "UPDATE player_stats SET kpr = 0.5 "
            "WHERE match_id = ? AND map_number = ?",
            (SAMPLE_MATCH_ID, 1),
        )
        match_repo.conn.commit()

        # Verify get_pending returns empty
        pending = match_repo.get_pending_perf_economy()
        assert len(pending) == 0

        # Orchestrator returns batch_size=0
        stats = await run_performance_economy(
            [mock_client], match_repo, storage, config
        )
        assert stats["batch_size"] == 0


class TestQuarantine:
    """Test that invalid records are quarantined without halting the pipeline."""

    @pytest.mark.asyncio
    async def test_perf_economy_quarantines_invalid_economy(
        self, mock_client, match_repo, storage, config
    ):
        """Economy with invalid buy_type is quarantined; perf stats and kill matrix still persist."""
        seed_match_with_map_stats(match_repo, SAMPLE_MATCH_ID, SAMPLE_MAPSTATSID)

        # Patch economy parser to inject an invalid buy_type on first round
        from scraper.economy_parser import parse_economy as real_parse_econ

        def patched_parse_econ(html_str, mapstatsid):
            result = real_parse_econ(html_str, mapstatsid)
            # Corrupt first round's buy_type to an invalid value
            if result.rounds:
                object.__setattr__(result.rounds[0], "buy_type", "pistol")
            return result

        with patch(
            "scraper.performance_economy.parse_economy",
            side_effect=patched_parse_econ,
        ):
            stats = await run_performance_economy(
                [mock_client], match_repo, storage, config
            )

        # Map should still parse successfully (partial economy data)
        assert stats["parsed"] == 1
        assert stats["failed"] == 0

        # Player stats still populated (kpr non-null)
        rows = match_repo.get_player_stats(SAMPLE_MATCH_ID, map_number=1)
        assert len(rows) == 10
        for row in rows:
            assert row["kpr"] is not None

        # Kill matrix still persisted
        km_rows = match_repo.conn.execute(
            "SELECT COUNT(*) FROM kill_matrix WHERE match_id = ? AND map_number = ?",
            (SAMPLE_MATCH_ID, 1),
        ).fetchone()[0]
        assert km_rows > 0

        # Quarantine table has the invalid economy record
        q_rows = match_repo.conn.execute(
            "SELECT * FROM quarantine WHERE match_id = ? AND entity_type = ?",
            (SAMPLE_MATCH_ID, "EconomyModel"),
        ).fetchall()
        assert len(q_rows) >= 1

        # Economy table still has rows (the valid ones)
        econ_count = match_repo.conn.execute(
            "SELECT COUNT(*) FROM economy WHERE match_id = ? AND map_number = ?",
            (SAMPLE_MATCH_ID, 1),
        ).fetchone()[0]
        assert econ_count > 0
