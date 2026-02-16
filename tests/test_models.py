"""Unit tests for all 9 Pydantic validation models.

Tests field constraints, cross-field validators, and soft warnings
for each model class defined in scraper.models.
"""

import warnings

import pytest
from pydantic import ValidationError

from scraper.models import (
    EconomyModel,
    ForfeitMatchModel,
    KillMatrixModel,
    MapModel,
    MatchModel,
    MatchPlayerModel,
    PlayerStatsModel,
    RoundHistoryModel,
    VetoModel,
)

# ---------------------------------------------------------------------------
# Fixtures: minimal valid dicts for each model
# ---------------------------------------------------------------------------

PROVENANCE = {
    "scraped_at": "2026-02-16T00:00:00Z",
    "source_url": "https://www.hltv.org/matches/123/test",
    "parser_version": "1.0",
}


@pytest.fixture
def valid_match() -> dict:
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
def valid_map() -> dict:
    return {
        "match_id": 100,
        "map_number": 1,
        "mapstatsid": 55555,
        "map_name": "de_mirage",
        "team1_rounds": 16,
        "team2_rounds": 12,
        "team1_ct_rounds": 8,
        "team1_t_rounds": 8,
        "team2_ct_rounds": 7,
        "team2_t_rounds": 5,
        **PROVENANCE,
    }


@pytest.fixture
def valid_player_stats() -> dict:
    return {
        "match_id": 100,
        "map_number": 1,
        "player_id": 1001,
        "player_name": "s1mple",
        "team_id": 1,
        "kills": 25,
        "deaths": 15,
        "assists": 5,
        "flash_assists": 2,
        "hs_kills": 12,
        "kd_diff": 10,
        "adr": 95.5,
        "kast": 72.0,
        "fk_diff": 2,
        "rating_2": None,
        "rating_3": 1.35,
        "kpr": 0.85,
        "dpr": 0.55,
        "impact": 1.2,
        "opening_kills": 5,
        "opening_deaths": 3,
        "multi_kills": 3,
        "clutch_wins": 1,
        "traded_deaths": 4,
        "round_swing": -0.5,
        "mk_rating": 1.1,
        **PROVENANCE,
    }


@pytest.fixture
def valid_round() -> dict:
    return {
        "match_id": 100,
        "map_number": 1,
        "round_number": 1,
        "winner_side": "CT",
        "win_type": "elimination",
        "winner_team_id": 1,
        **PROVENANCE,
    }


@pytest.fixture
def valid_economy() -> dict:
    return {
        "match_id": 100,
        "map_number": 1,
        "round_number": 1,
        "team_id": 1,
        "equipment_value": 4750,
        "buy_type": "full_eco",
        **PROVENANCE,
    }


@pytest.fixture
def valid_veto() -> dict:
    return {
        "match_id": 100,
        "step_number": 1,
        "team_name": "Team A",
        "action": "removed",
        "map_name": "de_dust2",
        **PROVENANCE,
    }


@pytest.fixture
def valid_match_player() -> dict:
    return {
        "match_id": 100,
        "player_id": 1001,
        "player_name": "s1mple",
        "team_id": 1,
        "team_num": 1,
        **PROVENANCE,
    }


@pytest.fixture
def valid_kill_matrix() -> dict:
    return {
        "match_id": 100,
        "map_number": 1,
        "matrix_type": "all",
        "player1_id": 1001,
        "player2_id": 1002,
        "player1_kills": 5,
        "player2_kills": 3,
        **PROVENANCE,
    }


# ===================================================================
# MatchModel tests
# ===================================================================


class TestMatchModel:
    def test_valid_match(self, valid_match):
        model = MatchModel.model_validate(valid_match)
        assert model.match_id == 100
        assert model.team1_score == 2

    def test_match_id_zero_rejected(self, valid_match):
        valid_match["match_id"] = 0
        with pytest.raises(ValidationError, match="match_id"):
            MatchModel.model_validate(valid_match)

    def test_same_team_ids_rejected(self, valid_match):
        valid_match["team2_id"] = valid_match["team1_id"]
        with pytest.raises(ValidationError, match="identical"):
            MatchModel.model_validate(valid_match)

    def test_score_exceeds_best_of_rejected(self, valid_match):
        # BO3 max wins = 2, so score 3-0 is invalid
        valid_match["team1_score"] = 3
        valid_match["team2_score"] = 0
        with pytest.raises(ValidationError, match="exceeds max wins"):
            MatchModel.model_validate(valid_match)

    def test_winner_low_score_warns(self, valid_match):
        # BO3 winner should have 2 wins; 1-0 is unusual
        valid_match["team1_score"] = 1
        valid_match["team2_score"] = 0
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            MatchModel.model_validate(valid_match)
        assert len(caught) >= 1
        assert "1 wins in BO3" in str(caught[0].message)

    def test_forfeit_match_model_no_score_check(self, valid_match):
        # ForfeitMatchModel allows irregular scores
        valid_match["team1_score"] = 1
        valid_match["team2_score"] = 0
        # Should NOT raise or warn about score consistency
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            ForfeitMatchModel.model_validate(valid_match)
        # No score-related warnings
        score_warnings = [w for w in caught if "wins" in str(w.message)]
        assert len(score_warnings) == 0


# ===================================================================
# MapModel tests
# ===================================================================


class TestMapModel:
    def test_valid_map(self, valid_map):
        model = MapModel.model_validate(valid_map)
        assert model.map_name == "de_mirage"

    def test_half_scores_exceed_total_rejected(self, valid_map):
        # CT + T = 10 + 10 = 20 > 16 total rounds
        valid_map["team1_ct_rounds"] = 10
        valid_map["team1_t_rounds"] = 10
        valid_map["team1_rounds"] = 16
        with pytest.raises(ValidationError, match="half scores.*exceed"):
            MapModel.model_validate(valid_map)

    def test_overtime_half_scores_allowed(self, valid_map):
        # In OT: ct+t < total is fine (OT rounds not broken into halves)
        valid_map["team1_rounds"] = 19
        valid_map["team1_ct_rounds"] = 7
        valid_map["team1_t_rounds"] = 8
        # 7+8=15 < 19 -- OT rounds make up the difference
        model = MapModel.model_validate(valid_map)
        assert model.team1_rounds == 19

    def test_extreme_ot_warns(self, valid_map):
        valid_map["team1_rounds"] = 30
        valid_map["team2_rounds"] = 28
        valid_map["team1_ct_rounds"] = 7
        valid_map["team1_t_rounds"] = 8
        valid_map["team2_ct_rounds"] = 8
        valid_map["team2_t_rounds"] = 7
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            MapModel.model_validate(valid_map)
        assert len(caught) >= 1
        assert "Extreme round count" in str(caught[0].message)


# ===================================================================
# PlayerStatsModel tests
# ===================================================================


class TestPlayerStatsModel:
    def test_valid_player_stats(self, valid_player_stats):
        model = PlayerStatsModel.model_validate(valid_player_stats)
        assert model.player_id == 1001
        assert model.kd_diff == 10

    def test_negative_kills_rejected(self, valid_player_stats):
        valid_player_stats["kills"] = -1
        # kd_diff will also need adjusting but the ge=0 check fires first
        with pytest.raises(ValidationError, match="kills"):
            PlayerStatsModel.model_validate(valid_player_stats)

    def test_kd_diff_mismatch_rejected(self, valid_player_stats):
        valid_player_stats["kills"] = 20
        valid_player_stats["deaths"] = 10
        valid_player_stats["kd_diff"] = 5  # Should be 10
        with pytest.raises(ValidationError, match="kd_diff"):
            PlayerStatsModel.model_validate(valid_player_stats)

    def test_fk_diff_mismatch_rejected(self, valid_player_stats):
        valid_player_stats["opening_kills"] = 5
        valid_player_stats["opening_deaths"] = 3
        valid_player_stats["fk_diff"] = 3  # Should be 2
        with pytest.raises(ValidationError, match="fk_diff"):
            PlayerStatsModel.model_validate(valid_player_stats)

    def test_hs_kills_exceed_kills_rejected(self, valid_player_stats):
        valid_player_stats["hs_kills"] = 20
        valid_player_stats["kills"] = 15
        # Keep kd_diff consistent so hs_kills check is the one that fires
        valid_player_stats["kd_diff"] = 15 - valid_player_stats["deaths"]
        with pytest.raises(ValidationError, match="hs_kills.*kills"):
            PlayerStatsModel.model_validate(valid_player_stats)

    def test_unusual_rating_warns(self, valid_player_stats):
        valid_player_stats["rating_3"] = 4.5
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            PlayerStatsModel.model_validate(valid_player_stats)
        rating_warns = [w for w in caught if "rating_3" in str(w.message)]
        assert len(rating_warns) >= 1

    def test_unusual_adr_warns(self, valid_player_stats):
        valid_player_stats["adr"] = 250.0
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            PlayerStatsModel.model_validate(valid_player_stats)
        adr_warns = [w for w in caught if "adr" in str(w.message)]
        assert len(adr_warns) >= 1

    def test_nulls_allowed_for_performance(self, valid_player_stats):
        # Phase 7 fields can be None when not yet scraped
        valid_player_stats["kpr"] = None
        valid_player_stats["dpr"] = None
        valid_player_stats["impact"] = None
        valid_player_stats["mk_rating"] = None
        model = PlayerStatsModel.model_validate(valid_player_stats)
        assert model.kpr is None
        assert model.dpr is None
        assert model.impact is None


# ===================================================================
# RoundHistoryModel tests
# ===================================================================


class TestRoundHistoryModel:
    def test_valid_round(self, valid_round):
        model = RoundHistoryModel.model_validate(valid_round)
        assert model.winner_side == "CT"

    def test_invalid_winner_side(self, valid_round):
        valid_round["winner_side"] = "X"
        with pytest.raises(ValidationError, match="winner_side"):
            RoundHistoryModel.model_validate(valid_round)

    def test_invalid_win_type(self, valid_round):
        valid_round["win_type"] = "surrender"
        with pytest.raises(ValidationError, match="win_type"):
            RoundHistoryModel.model_validate(valid_round)


# ===================================================================
# EconomyModel tests
# ===================================================================


class TestEconomyModel:
    def test_valid_economy(self, valid_economy):
        model = EconomyModel.model_validate(valid_economy)
        assert model.equipment_value == 4750

    def test_invalid_buy_type(self, valid_economy):
        valid_economy["buy_type"] = "pistol"
        with pytest.raises(ValidationError, match="buy_type"):
            EconomyModel.model_validate(valid_economy)


# ===================================================================
# VetoModel tests
# ===================================================================


class TestVetoModel:
    def test_valid_veto(self, valid_veto):
        model = VetoModel.model_validate(valid_veto)
        assert model.action == "removed"

    def test_invalid_action(self, valid_veto):
        valid_veto["action"] = "banned"
        with pytest.raises(ValidationError, match="action"):
            VetoModel.model_validate(valid_veto)


# ===================================================================
# MatchPlayerModel tests
# ===================================================================


class TestMatchPlayerModel:
    def test_valid_match_player(self, valid_match_player):
        model = MatchPlayerModel.model_validate(valid_match_player)
        assert model.team_num == 1

    def test_invalid_team_num(self, valid_match_player):
        valid_match_player["team_num"] = 3
        with pytest.raises(ValidationError, match="team_num"):
            MatchPlayerModel.model_validate(valid_match_player)


# ===================================================================
# KillMatrixModel tests
# ===================================================================


class TestKillMatrixModel:
    def test_valid_kill_matrix(self, valid_kill_matrix):
        model = KillMatrixModel.model_validate(valid_kill_matrix)
        assert model.matrix_type == "all"

    def test_invalid_matrix_type(self, valid_kill_matrix):
        valid_kill_matrix["matrix_type"] = "pistol"
        with pytest.raises(ValidationError, match="matrix_type"):
            KillMatrixModel.model_validate(valid_kill_matrix)
