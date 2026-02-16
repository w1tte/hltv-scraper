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
        "rating": 1.30,
        "kpr": 0.85,
        "dpr": 0.58,
        "opening_kills": 3,
        "opening_deaths": 1,
        "multi_kills": 2,
        "clutch_wins": 1,
        "traded_deaths": 4,
        "round_swing": 1.5,
        "mk_rating": 1.10,
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


def make_veto_data(match_id=1, step_number=1, **overrides):
    """Return a complete vetoes dict with sensible defaults."""
    data = {
        "match_id": match_id,
        "step_number": step_number,
        "team_name": "TeamA",
        "action": "removed",
        "map_name": "Nuke",
        "scraped_at": "2025-06-16T10:00:00Z",
        "source_url": f"https://www.hltv.org/matches/{match_id}/navi-vs-g2",
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
    def test_upsert_player_stats_nullable_rating(self, repo):
        """rating can be None."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        repo.upsert_player_stats(make_player_stats_data(
            match_id=1, map_number=1, player_id=10,
            rating=None,
        ))
        stats = repo.get_player_stats(1, 1)
        assert len(stats) == 1
        assert stats[0]["rating"] is None

    def test_upsert_player_stats_partial_performance(self, repo):
        """kpr, dpr can be None (populated later in Phase 7)."""
        repo.upsert_match(make_match_data(match_id=1))
        repo.upsert_map(make_map_data(match_id=1, map_number=1))
        repo.upsert_player_stats(make_player_stats_data(
            match_id=1, map_number=1, player_id=10,
            kpr=None, dpr=None,
        ))
        stats = repo.get_player_stats(1, 1)
        assert len(stats) == 1
        assert stats[0]["kpr"] is None
        assert stats[0]["dpr"] is None


# ---------------------------------------------------------------------------
# UPSERT - upsert_match_overview (atomic match + maps + vetoes)
# ---------------------------------------------------------------------------

class TestUpsertMatchOverview:
    def test_upsert_match_overview_inserts_all_data(self, repo):
        """Insert match + 3 maps + 7 vetoes in one call."""
        match = make_match_data(match_id=1)
        maps = [
            make_map_data(match_id=1, map_number=i, map_name=name)
            for i, name in enumerate(["Inferno", "Mirage", "Dust2"], 1)
        ]
        vetoes = [
            make_veto_data(match_id=1, step_number=s, action=action, map_name=m)
            for s, (action, m) in enumerate([
                ("removed", "Nuke"),
                ("removed", "Overpass"),
                ("picked", "Inferno"),
                ("picked", "Mirage"),
                ("removed", "Vertigo"),
                ("removed", "Ancient"),
                ("left_over", "Dust2"),
            ], 1)
        ]
        # Set team_name=None for "left_over" step
        vetoes[-1]["team_name"] = None

        repo.upsert_match_overview(match, maps, vetoes)

        assert repo.get_match(1) is not None
        assert len(repo.get_maps(1)) == 3
        assert len(repo.get_vetoes(1)) == 7

    def test_upsert_match_overview_is_atomic(self, repo):
        """If a veto insert fails, nothing is written (transaction rollback)."""
        match = make_match_data(match_id=1)
        maps = [make_map_data(match_id=1, map_number=1)]
        # Bad veto data: missing required scraped_at field -> triggers error
        bad_veto = {
            "match_id": 1,
            "step_number": 1,
            "team_name": "test",
            "action": "removed",
            "map_name": "Nuke",
            # scraped_at intentionally missing -> KeyError on named param
        }
        with pytest.raises(Exception):
            repo.upsert_match_overview(match, maps, [bad_veto])

        # Nothing should have been persisted
        assert repo.get_match(1) is None
        assert repo.get_maps(1) == []
        assert repo.get_vetoes(1) == []

    def test_upsert_match_overview_updates_on_conflict(self, repo):
        """Upsert twice with modified data, verify update and updated_at."""
        match = make_match_data(match_id=1)
        maps = [make_map_data(match_id=1, map_number=1)]
        vetoes = [make_veto_data(match_id=1, step_number=1, map_name="Nuke")]

        repo.upsert_match_overview(match, maps, vetoes)

        # Second upsert with updated data
        match2 = make_match_data(match_id=1, scraped_at="2025-07-01T00:00:00Z")
        maps2 = [make_map_data(match_id=1, map_number=1, map_name="Dust2",
                               scraped_at="2025-07-01T00:00:00Z")]
        vetoes2 = [make_veto_data(match_id=1, step_number=1, map_name="Ancient",
                                  scraped_at="2025-07-01T00:00:00Z")]

        repo.upsert_match_overview(match2, maps2, vetoes2)

        v = repo.get_vetoes(1)
        assert len(v) == 1
        assert v[0]["map_name"] == "Ancient"
        assert v[0]["updated_at"] == "2025-07-01T00:00:00Z"

        m = repo.get_maps(1)
        assert m[0]["map_name"] == "Dust2"


# ---------------------------------------------------------------------------
# Vetoes read methods
# ---------------------------------------------------------------------------

class TestVetoes:
    def test_get_vetoes_returns_ordered_steps(self, repo):
        """Insert 7 vetoes out of order, get_vetoes returns them by step_number."""
        repo.upsert_match(make_match_data(match_id=1))
        # Insert in shuffled order
        for step in [5, 2, 7, 1, 4, 6, 3]:
            with repo.conn:
                repo.conn.execute(
                    "INSERT INTO vetoes (match_id, step_number, team_name, action, map_name, "
                    "scraped_at, updated_at, source_url, parser_version) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (1, step, "TeamA", "removed", f"Map{step}",
                     "2025-06-16T10:00:00Z", "2025-06-16T10:00:00Z", None, "0.1.0"),
                )

        vetoes = repo.get_vetoes(1)
        assert len(vetoes) == 7
        assert [v["step_number"] for v in vetoes] == [1, 2, 3, 4, 5, 6, 7]

    def test_get_vetoes_empty_match(self, repo):
        """get_vetoes returns empty list for nonexistent match."""
        assert repo.get_vetoes(9999) == []

    def test_veto_with_null_team_name(self, repo):
        """A 'left_over' veto with team_name=None persists correctly."""
        repo.upsert_match(make_match_data(match_id=1))
        veto = make_veto_data(match_id=1, step_number=7, team_name=None, action="left_over")
        with repo.conn:
            repo.conn.execute(
                "INSERT INTO vetoes (match_id, step_number, team_name, action, map_name, "
                "scraped_at, updated_at, source_url, parser_version) "
                "VALUES (:match_id, :step_number, :team_name, :action, :map_name, "
                ":scraped_at, :scraped_at, :source_url, :parser_version)",
                veto,
            )

        vetoes = repo.get_vetoes(1)
        assert len(vetoes) == 1
        assert vetoes[0]["team_name"] is None
        assert vetoes[0]["action"] == "left_over"


# ---------------------------------------------------------------------------
# get_pending_map_stats
# ---------------------------------------------------------------------------

class TestGetPendingMapStats:
    """Tests for the get_pending_map_stats query method."""

    def _seed_match_and_maps(self, repo):
        """Seed a match with 3 maps: two with mapstatsid, one without."""
        repo.upsert_match(make_match_data(match_id=99999))
        repo.upsert_map(make_map_data(
            match_id=99999, map_number=1, mapstatsid=111111, map_name="Inferno",
        ))
        repo.upsert_map(make_map_data(
            match_id=99999, map_number=2, mapstatsid=222222, map_name="Mirage",
        ))
        # Unplayed/forfeit map with mapstatsid=None
        repo.upsert_map(make_map_data(
            match_id=99999, map_number=3, mapstatsid=None, map_name="Default",
        ))

    def test_returns_maps_without_player_stats(self, repo):
        """Maps with mapstatsid but no player_stats appear as pending."""
        self._seed_match_and_maps(repo)
        pending = repo.get_pending_map_stats(limit=100)
        assert len(pending) == 2
        assert pending[0]["match_id"] == 99999
        assert pending[0]["map_number"] == 1
        assert pending[0]["mapstatsid"] == 111111
        assert pending[1]["map_number"] == 2
        assert pending[1]["mapstatsid"] == 222222

    def test_excludes_maps_with_player_stats(self, repo):
        """After inserting player_stats for map 1, only map 2 is pending."""
        self._seed_match_and_maps(repo)
        repo.upsert_player_stats(make_player_stats_data(
            match_id=99999, map_number=1, player_id=1001,
        ))
        pending = repo.get_pending_map_stats(limit=100)
        assert len(pending) == 1
        assert pending[0]["map_number"] == 2

    def test_excludes_null_mapstatsid(self, repo):
        """Maps with mapstatsid=None (forfeit/unplayed) never appear."""
        self._seed_match_and_maps(repo)
        pending = repo.get_pending_map_stats(limit=100)
        mapstatsids = [p["mapstatsid"] for p in pending]
        assert None not in mapstatsids
        # Only the 2 maps with mapstatsid should be returned
        assert len(pending) == 2

    def test_respects_limit(self, repo):
        """With 2 pending maps, limit=1 returns only 1."""
        self._seed_match_and_maps(repo)
        pending = repo.get_pending_map_stats(limit=1)
        assert len(pending) == 1
        assert pending[0]["map_number"] == 1  # ordered by match_id, map_number

    def test_returns_empty_when_all_processed(self, repo):
        """After inserting player_stats for all maps, returns empty list."""
        self._seed_match_and_maps(repo)
        for map_num in [1, 2]:
            repo.upsert_player_stats(make_player_stats_data(
                match_id=99999, map_number=map_num, player_id=1001,
            ))
        pending = repo.get_pending_map_stats(limit=100)
        assert pending == []

    def test_ordered_by_match_and_map(self, repo):
        """Maps from multiple matches are ordered by match_id ASC then map_number ASC."""
        # Create two matches with maps
        repo.upsert_match(make_match_data(match_id=50000))
        repo.upsert_map(make_map_data(match_id=50000, map_number=2, mapstatsid=500002))
        repo.upsert_map(make_map_data(match_id=50000, map_number=1, mapstatsid=500001))

        repo.upsert_match(make_match_data(match_id=40000))
        repo.upsert_map(make_map_data(match_id=40000, map_number=1, mapstatsid=400001))

        pending = repo.get_pending_map_stats(limit=100)
        result = [(p["match_id"], p["map_number"]) for p in pending]
        assert result == [
            (40000, 1),
            (50000, 1),
            (50000, 2),
        ]


# ---------------------------------------------------------------------------
# upsert_map_stats_complete
# ---------------------------------------------------------------------------

class TestUpsertMapStatsComplete:
    """Tests for the upsert_map_stats_complete atomic write method."""

    def _seed_match_and_map(self, repo):
        """Seed a match with one map for player_stats/round_history inserts."""
        repo.upsert_match(make_match_data(match_id=99999))
        repo.upsert_map(make_map_data(
            match_id=99999, map_number=1, mapstatsid=111111,
        ))

    def test_upserts_player_stats_and_rounds_atomically(self, repo):
        """All player_stats and round_history rows are written in one transaction."""
        self._seed_match_and_map(repo)
        stats = [
            make_player_stats_data(
                match_id=99999, map_number=1, player_id=1000 + i,
                player_name=f"Player{i}", team_id=4608 if i <= 3 else 5995,
            )
            for i in range(1, 6)
        ]
        rounds = [
            make_round_data(match_id=99999, map_number=1, round_number=r)
            for r in range(1, 25)
        ]

        repo.upsert_map_stats_complete(stats, rounds)

        # Verify player_stats
        ps = repo.get_player_stats(99999, 1)
        assert len(ps) == 5

        # Verify round_history
        rh_count = repo.conn.execute(
            "SELECT COUNT(*) FROM round_history WHERE match_id = 99999 AND map_number = 1"
        ).fetchone()[0]
        assert rh_count == 24

    def test_rollback_on_round_error(self, repo):
        """If a round insert fails, player_stats are also rolled back."""
        self._seed_match_and_map(repo)
        stats = [
            make_player_stats_data(
                match_id=99999, map_number=1, player_id=1001,
            )
        ]
        # Bad round data: missing required fields -> error during execute
        bad_rounds = [{"match_id": 99999, "map_number": 1}]  # missing round_number etc.

        with pytest.raises(Exception):
            repo.upsert_map_stats_complete(stats, bad_rounds)

        # Neither player_stats nor rounds should have been persisted
        ps = repo.get_player_stats(99999, 1)
        assert ps == []
        rh_count = repo.conn.execute(
            "SELECT COUNT(*) FROM round_history WHERE match_id = 99999 AND map_number = 1"
        ).fetchone()[0]
        assert rh_count == 0

    def test_map_no_longer_pending_after_upsert(self, repo):
        """After upsert_map_stats_complete, get_pending_map_stats excludes the map."""
        self._seed_match_and_map(repo)
        # Verify it's initially pending
        pending_before = repo.get_pending_map_stats(limit=100)
        assert len(pending_before) == 1

        stats = [
            make_player_stats_data(
                match_id=99999, map_number=1, player_id=1001,
            )
        ]
        rounds = [
            make_round_data(match_id=99999, map_number=1, round_number=1)
        ]
        repo.upsert_map_stats_complete(stats, rounds)

        # Now it should not be pending
        pending_after = repo.get_pending_map_stats(limit=100)
        assert pending_after == []
