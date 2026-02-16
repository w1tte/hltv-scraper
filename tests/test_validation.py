"""Unit tests for the validation wrapper layer (scraper.validation).

Tests validate_and_quarantine, validate_batch, check_player_count,
and check_economy_alignment.
"""

from unittest.mock import MagicMock

import pytest

from scraper.models import MatchModel, PlayerStatsModel
from scraper.validation import (
    check_economy_alignment,
    check_player_count,
    validate_and_quarantine,
    validate_batch,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROVENANCE = {
    "scraped_at": "2026-02-16T00:00:00Z",
    "source_url": "https://www.hltv.org/matches/100/test",
    "parser_version": "1.0",
}

CTX = {"match_id": 100, "map_number": 1}


@pytest.fixture
def valid_match_data() -> dict:
    return {
        "match_id": 100,
        "date": "2026-01-15",
        "event_id": 10,
        "event_name": "Test Event",
        "team1_id": 1,
        "team1_name": "Team A",
        "team2_id": 2,
        "team2_name": "Team B",
        "team1_score": 2,
        "team2_score": 1,
        "best_of": 3,
        "is_lan": 1,
        **PROVENANCE,
    }


@pytest.fixture
def invalid_match_data(valid_match_data) -> dict:
    """Match with match_id=0 (triggers ValidationError)."""
    valid_match_data["match_id"] = 0
    return valid_match_data


@pytest.fixture
def valid_player_stats_data() -> dict:
    return {
        "match_id": 100,
        "map_number": 1,
        "player_id": 1001,
        "player_name": "s1mple",
        "team_id": 1,
        "kills": 20,
        "deaths": 10,
        "assists": 3,
        "flash_assists": 1,
        "hs_kills": 10,
        "kd_diff": 10,
        "adr": 90.0,
        "kast": 70.0,
        "fk_diff": 2,
        "rating": 1.2,
        "kpr": 0.8,
        "dpr": 0.5,
        "opening_kills": 4,
        "opening_deaths": 2,
        "multi_kills": 2,
        "clutch_wins": 1,
        "traded_deaths": 3,
        "round_swing": -0.3,
        "mk_rating": 1.0,
        **PROVENANCE,
    }


# ===================================================================
# validate_and_quarantine tests
# ===================================================================


class TestValidateAndQuarantine:
    def test_valid_returns_dict(self, valid_match_data):
        result = validate_and_quarantine(valid_match_data, MatchModel, CTX)
        assert result is not None
        assert isinstance(result, dict)
        assert result["match_id"] == 100

    def test_invalid_returns_none_and_quarantines(self, invalid_match_data):
        repo = MagicMock()
        result = validate_and_quarantine(
            invalid_match_data, MatchModel, CTX, repo
        )
        assert result is None
        repo.insert_quarantine.assert_called_once()
        q_data = repo.insert_quarantine.call_args[0][0]
        assert q_data["entity_type"] == "MatchModel"
        assert q_data["match_id"] == 100
        assert q_data["resolved"] == 0
        assert "match_id" in q_data["error_details"]

    def test_no_repo_does_not_crash(self, invalid_match_data):
        # repo=None should not raise even on validation failure
        result = validate_and_quarantine(
            invalid_match_data, MatchModel, CTX, repo=None
        )
        assert result is None

    def test_adds_updated_at(self, valid_match_data):
        # Remove updated_at -- should be auto-filled from scraped_at
        valid_match_data.pop("updated_at", None)
        result = validate_and_quarantine(valid_match_data, MatchModel, CTX)
        assert result is not None
        assert result["updated_at"] == valid_match_data["scraped_at"]


# ===================================================================
# validate_batch tests
# ===================================================================


class TestValidateBatch:
    def test_mixed_batch(self, valid_match_data):
        invalid = valid_match_data.copy()
        invalid["match_id"] = 0  # Will fail validation

        items = [valid_match_data, invalid]
        repo = MagicMock()
        valid, quarantine_count = validate_batch(
            items, MatchModel, CTX, repo
        )
        assert len(valid) == 1
        assert quarantine_count == 1
        assert valid[0]["match_id"] == 100

    def test_all_valid(self, valid_match_data):
        items = [valid_match_data.copy(), valid_match_data.copy()]
        # Give second item a different match_id to avoid duplicate key issues
        items[1]["match_id"] = 200
        valid, quarantine_count = validate_batch(items, MatchModel, CTX)
        assert len(valid) == 2
        assert quarantine_count == 0

    def test_all_invalid(self, valid_match_data):
        invalid1 = valid_match_data.copy()
        invalid1["match_id"] = 0
        invalid2 = valid_match_data.copy()
        invalid2["match_id"] = -5
        valid, quarantine_count = validate_batch(
            [invalid1, invalid2], MatchModel, CTX
        )
        assert len(valid) == 0
        assert quarantine_count == 2


# ===================================================================
# check_player_count tests
# ===================================================================


class TestCheckPlayerCount:
    def test_exactly_10(self, valid_player_stats_data):
        stats = []
        for i in range(10):
            row = valid_player_stats_data.copy()
            row["player_id"] = 1000 + i
            row["team_id"] = 1 if i < 5 else 2
            row["kd_diff"] = row["kills"] - row["deaths"]
            stats.append(row)

        warnings = check_player_count(stats, 100, 1)
        assert warnings == []

    def test_not_10(self, valid_player_stats_data):
        stats = [valid_player_stats_data.copy() for _ in range(8)]
        warnings = check_player_count(stats, 100, 1)
        assert len(warnings) == 1
        assert "Expected 10" in warnings[0]
        assert "got 8" in warnings[0]

    def test_zero_players(self):
        warnings = check_player_count([], 100, 1)
        assert len(warnings) == 1
        assert "got 0" in warnings[0]


# ===================================================================
# check_economy_alignment tests
# ===================================================================


class TestCheckEconomyAlignment:
    def test_clean_alignment(self):
        valid_rounds = {1, 2, 3, 4, 5}
        economy_dicts = [
            {"round_number": 1, "team_id": 1},
            {"round_number": 2, "team_id": 1},
            {"round_number": 3, "team_id": 2},
        ]
        warnings = check_economy_alignment(
            economy_dicts, valid_rounds, 100, 1
        )
        assert warnings == []

    def test_extra_round(self):
        valid_rounds = {1, 2, 3}
        economy_dicts = [
            {"round_number": 1, "team_id": 1},
            {"round_number": 5, "team_id": 1},  # Round 5 not in round_history
        ]
        warnings = check_economy_alignment(
            economy_dicts, valid_rounds, 100, 1
        )
        assert len(warnings) == 1
        assert "round 5" in warnings[0]
        assert "not in round_history" in warnings[0]

    def test_multiple_misaligned(self):
        valid_rounds = {1, 2}
        economy_dicts = [
            {"round_number": 3, "team_id": 1},
            {"round_number": 4, "team_id": 2},
        ]
        warnings = check_economy_alignment(
            economy_dicts, valid_rounds, 100, 1
        )
        assert len(warnings) == 2
