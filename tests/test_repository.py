"""Tests for the MatchRepository UPSERT and read operations.

Exercises every repository method and verifies UPSERT semantics,
foreign key enforcement, batch atomicity, and read methods.
"""

import sqlite3

import pytest

from scraper.db import Database
from scraper.repository import MatchRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def repo(db):
    return MatchRepository(db.conn)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def make_match_data(match_id=1, **overrides):
    """Return a complete match dict with sensible defaults."""
    data = {
        "match_id": match_id,
        "date": "2025-06-15",
        "event_id": 7148,
        "event_name": "BLAST Premier Spring Final 2025",
        "team1_id": 4608,
        "team1_name": "Natus Vincere",
        "team2_id": 5995,
        "team2_name": "G2 Esports",
        "team1_score": 2,
        "team2_score": 1,
        "best_of": 3,
        "is_lan": 1,
        "match_url": f"https://www.hltv.org/matches/{match_id}/navi-vs-g2",
        "scraped_at": "2025-06-16T10:00:00Z",
        "source_url": f"https://www.hltv.org/matches/{match_id}/navi-vs-g2",
        "parser_version": "0.1.0",
    }
    data.update(overrides)
    return data


def make_map_data(match_id=1, map_number=1, **overrides):
    """Return a complete map dict with sensible defaults."""
    data = {
        "match_id": match_id,
        "map_number": map_number,
        "mapstatsid": 178000 + map_number,
        "map_name": "Inferno",
        "team1_rounds": 16,
        "team2_rounds": 12,
        "team1_ct_rounds": 9,
        "team1_t_rounds": 7,
        "team2_ct_rounds": 7,
        "team2_t_rounds": 5,
        "scraped_at": "2025-06-16T10:00:00Z",
        "source_url": f"https://www.hltv.org/stats/matches/mapstatsid/{178000 + map_number}/navi-vs-g2",
        "parser_version": "0.1.0",
    }
    data.update(overrides)
    return data


def make_player_stats_data(match_id=1, map_number=1, player_id=1, **overrides):
    """Return a complete player_stats dict with sensible defaults."""
    data = {
        "match_id": match_id,
        "map_number": map_number,
        "player_id": player_id,
        "player_name": f"Player{player_id}",
        "team_id": 4608,
        "kills": 22,
        "deaths": 15,
        "assists": 4,
        "flash_assists": 2,
        "hs_kills": 10,
        "kd_diff": 7,
        "adr": 85.3,
        "kast": 72.0,
        "fk_diff": 2,
        "rating_2": 1.25,
        "rating_3": 1.30,
        "kpr": 0.85,
        "dpr": 0.58,
        "impact": 1.15,
        "scraped_at": "2025-06-16T10:00:00Z",
        "source_url": f"https://www.hltv.org/stats/matches/mapstatsid/178001/navi-vs-g2",
        "parser_version": "0.1.0",
    }
    data.update(overrides)
    return data


def make_round_data(match_id=1, map_number=1, round_number=1, **overrides):
    """Return a complete round_history dict with sensible defaults."""
    data = {
        "match_id": match_id,
        "map_number": map_number,
        "round_number": round_number,
        "winner_side": "CT",
        "win_type": "elimination",
        "winner_team_id": 4608,
        "scraped_at": "2025-06-16T10:00:00Z",
        "source_url": f"https://www.hltv.org/stats/matches/mapstatsid/178001/navi-vs-g2",
        "parser_version": "0.1.0",
    }
    data.update(overrides)
    return data


def make_economy_data(match_id=1, map_number=1, round_number=1, team_id=100, **overrides):
    """Return a complete economy dict with sensible defaults."""
    data = {
        "match_id": match_id,
        "map_number": map_number,
        "round_number": round_number,
        "team_id": team_id,
        "equipment_value": 26500,
        "buy_type": "full",
        "scraped_at": "2025-06-16T10:00:00Z",
        "source_url": f"https://www.hltv.org/stats/matches/mapstatsid/178001/navi-vs-g2",
        "parser_version": "0.1.0",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# UPSERT - Single row: matches
# ---------------------------------------------------------------------------

class TestUpsertMatch:
    def test_upsert_match_insert(self, repo):
        """Insert new match, get_match returns it."""
        repo.upsert_match(make_match_data(match_id=1))
        m = repo.get_match(1)
        assert m is not None
        assert m["match_id"] == 1
        assert m["team1_name"] == "Natus Vincere"
        assert m["team2_name"] == "G2 Esports"
        assert m["best_of"] == 3

    def test_upsert_match_update(self, repo):
        """Upsert same match_id with different data, verify updated and only 1 row."""
        repo.upsert_match(make_match_data(match_id=1, team1_score=2))
        repo.upsert_match(make_match_data(match_id=1, team1_score=0))
        assert repo.count_matches() == 1
        m = repo.get_match(1)
        assert m["team1_score"] == 0

    def test_upsert_match_updated_at(self, repo):
        """Upsert twice with different scraped_at, verify updated_at reflects second."""
        repo.upsert_match(make_match_data(match_id=1, scraped_at="2025-01-01T00:00:00Z"))
        repo.upsert_match(make_match_data(match_id=1, scraped_at="2025-06-01T12:00:00Z"))
        m = repo.get_match(1)
        assert m["updated_at"] == "2025-06-01T12:00:00Z"


# ---------------------------------------------------------------------------
# UPSERT - Single row: maps
# ---------------------------------------------------------------------------

class TestUpsertMap:
    def test_upsert_map_insert(self, repo):
        """Insert map (after parent match), get_maps returns it."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1, map_name="Inferno"))
        maps = repo.get_maps(1)
        assert len(maps) == 1
        assert maps[0]["map_name"] == "Inferno"
        assert maps[0]["map_number"] == 1

    def test_upsert_map_update(self, repo):
        """Upsert same (match_id, map_number) with changed map_name, verify updated."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1, map_name="Mirage"))
        repo.upsert_map(make_map_data(match_id=1, map_number=1, map_name="Dust2"))
        maps = repo.get_maps(1)
        assert len(maps) == 1
        assert maps[0]["map_name"] == "Dust2"


# ---------------------------------------------------------------------------
# UPSERT - Single row: player_stats
# ---------------------------------------------------------------------------

class TestUpsertPlayerStats:
    def test_upsert_player_stats_insert(self, repo):
        """Insert player stats (after match + map), get_player_stats returns it."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        repo.upsert_player_stats(make_player_stats_data(match_id=1, map_number=1, player_id=10))
        stats = repo.get_player_stats(1, 1)
        assert len(stats) == 1
        assert stats[0]["player_id"] == 10
        assert stats[0]["kills"] == 22

    def test_upsert_player_stats_update(self, repo):
        """Upsert with changed kills/deaths, verify updated."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        repo.upsert_player_stats(make_player_stats_data(
            match_id=1, map_number=1, player_id=10, kills=22, deaths=15,
        ))
        repo.upsert_player_stats(make_player_stats_data(
            match_id=1, map_number=1, player_id=10, kills=30, deaths=10,
        ))
        stats = repo.get_player_stats(1, 1)
        assert len(stats) == 1
        assert stats[0]["kills"] == 30
        assert stats[0]["deaths"] == 10


# ---------------------------------------------------------------------------
# UPSERT - Single row: round_history
# ---------------------------------------------------------------------------

class TestUpsertRound:
    def test_upsert_round_insert(self, repo):
        """Insert round (after match + map)."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        repo.upsert_round(make_round_data(match_id=1, map_number=1, round_number=1))
        # Verify by reading directly -- no dedicated read method for rounds
        row = repo.conn.execute(
            "SELECT * FROM round_history WHERE match_id = 1 AND map_number = 1 AND round_number = 1"
        ).fetchone()
        assert row is not None
        assert dict(row)["winner_side"] == "CT"


# ---------------------------------------------------------------------------
# UPSERT - Single row: economy
# ---------------------------------------------------------------------------

class TestUpsertEconomy:
    def test_upsert_economy_insert(self, repo):
        """Insert economy row (after match + map + round)."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        repo.upsert_round(make_round_data(match_id=1, map_number=1, round_number=1))
        repo.upsert_economy(make_economy_data(
            match_id=1, map_number=1, round_number=1, team_id=100,
        ))
        row = repo.conn.execute(
            "SELECT * FROM economy WHERE match_id = 1 AND map_number = 1 "
            "AND round_number = 1 AND team_id = 100"
        ).fetchone()
        assert row is not None
        assert dict(row)["equipment_value"] == 26500
        assert dict(row)["buy_type"] == "full"


# ---------------------------------------------------------------------------
# UPSERT - Batch methods
# ---------------------------------------------------------------------------

class TestBatchUpsert:
    def test_upsert_match_maps_atomic(self, repo):
        """upsert_match_maps inserts 1 match + 3 maps in one call."""
        match = make_match_data(match_id=1)
        maps = [
            make_map_data(match_id=1, map_number=1, map_name="Inferno"),
            make_map_data(match_id=1, map_number=2, map_name="Mirage"),
            make_map_data(match_id=1, map_number=3, map_name="Dust2"),
        ]
        repo.upsert_match_maps(match, maps)
        assert repo.count_matches() == 1
        result_maps = repo.get_maps(1)
        assert len(result_maps) == 3
        assert [m["map_name"] for m in result_maps] == ["Inferno", "Mirage", "Dust2"]

    def test_upsert_map_player_stats_batch(self, repo):
        """upsert_map_player_stats inserts 10 player rows (2 teams x 5 players)."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        stats = []
        for i in range(1, 6):
            stats.append(make_player_stats_data(match_id=1, map_number=1, player_id=i, team_id=100))
        for i in range(6, 11):
            stats.append(make_player_stats_data(match_id=1, map_number=1, player_id=i, team_id=200))
        repo.upsert_map_player_stats(stats)
        result = repo.get_player_stats(1, 1)
        assert len(result) == 10

    def test_upsert_map_rounds_batch(self, repo):
        """upsert_map_rounds inserts 24 rounds."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        rounds = [
            make_round_data(match_id=1, map_number=1, round_number=r)
            for r in range(1, 25)
        ]
        repo.upsert_map_rounds(rounds)
        count = repo.conn.execute(
            "SELECT COUNT(*) FROM round_history WHERE match_id = 1 AND map_number = 1"
        ).fetchone()[0]
        assert count == 24


# ---------------------------------------------------------------------------
# Foreign key enforcement
# ---------------------------------------------------------------------------

class TestForeignKeys:
    def test_fk_map_without_match_raises(self, repo):
        """upsert_map for non-existent match_id raises IntegrityError."""
        with pytest.raises(sqlite3.IntegrityError):
            repo.upsert_map(make_map_data(match_id=999, map_number=1))

    def test_fk_player_stats_without_map_raises(self, repo):
        """upsert_player_stats for non-existent (match_id, map_number) raises IntegrityError."""
        repo.upsert_match(make_match_data(match_id=1))
        # Map not inserted -- player_stats should fail
        with pytest.raises(sqlite3.IntegrityError):
            repo.upsert_player_stats(make_player_stats_data(
                match_id=1, map_number=1, player_id=10,
            ))

    def test_fk_round_without_map_raises(self, repo):
        """upsert_round for non-existent (match_id, map_number) raises IntegrityError."""
        repo.upsert_match(make_match_data(match_id=1))
        with pytest.raises(sqlite3.IntegrityError):
            repo.upsert_round(make_round_data(match_id=1, map_number=1, round_number=1))

    def test_fk_economy_without_round_raises(self, repo):
        """upsert_economy for non-existent round raises IntegrityError."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        # Round not inserted -- economy should fail
        with pytest.raises(sqlite3.IntegrityError):
            repo.upsert_economy(make_economy_data(
                match_id=1, map_number=1, round_number=1, team_id=100,
            ))


# ---------------------------------------------------------------------------
# Read methods
# ---------------------------------------------------------------------------

class TestReadMethods:
    def test_get_match_not_found(self, repo):
        """get_match for non-existent ID returns None."""
        assert repo.get_match(9999) is None

    def test_get_maps_empty(self, repo):
        """get_maps for match with no maps returns empty list."""
        repo.upsert_match(make_match_data(match_id=1))
        assert repo.get_maps(1) == []

    def test_get_maps_ordered(self, repo):
        """Insert maps out of order, get_maps returns them ordered by map_number."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=3, map_name="Dust2"))
        repo.upsert_map(make_map_data(match_id=1, map_number=1, map_name="Inferno"))
        repo.upsert_map(make_map_data(match_id=1, map_number=2, map_name="Mirage"))
        maps = repo.get_maps(1)
        assert [m["map_number"] for m in maps] == [1, 2, 3]

    def test_count_matches_zero(self, repo):
        """count_matches on empty db returns 0."""
        assert repo.count_matches() == 0

    def test_count_matches_after_inserts(self, repo):
        """Insert 3 matches, count returns 3."""
        for mid in [1, 2, 3]:
            repo.upsert_match(make_match_data(match_id=mid))
        assert repo.count_matches() == 3


# ---------------------------------------------------------------------------
# Nullable fields
# ---------------------------------------------------------------------------

class TestNullableFields:
    def test_upsert_player_stats_nullable_ratings(self, repo):
        """rating_2 and rating_3 can both be None."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        repo.upsert_player_stats(make_player_stats_data(
            match_id=1, map_number=1, player_id=10,
            rating_2=None, rating_3=None,
        ))
        stats = repo.get_player_stats(1, 1)
        assert len(stats) == 1
        assert stats[0]["rating_2"] is None
        assert stats[0]["rating_3"] is None

    def test_upsert_player_stats_partial_performance(self, repo):
        """kpr, dpr, impact can be None (populated later in Phase 7)."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        repo.upsert_player_stats(make_player_stats_data(
            match_id=1, map_number=1, player_id=10,
            kpr=None, dpr=None, impact=None,
        ))
        stats = repo.get_player_stats(1, 1)
        assert len(stats) == 1
        assert stats[0]["kpr"] is None
        assert stats[0]["dpr"] is None
        assert stats[0]["impact"] is None
