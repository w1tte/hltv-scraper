"""Tests for map stats parser against real HTML samples.

Tests cover: scoreboard extraction, round history (standard, single OT,
extended OT), map metadata, half breakdown.
All tests use gzipped HTML from data/recon/.
"""

import gzip
from pathlib import Path

import pytest

from scraper.map_stats_parser import (
    MapStats,
    PlayerStats,
    RoundOutcome,
    parse_map_stats,
)

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"

# All available map stats samples
ALL_SAMPLES = [
    ("mapstats-162345-stats.html.gz", 162345),  # single OT (30 rounds)
    ("mapstats-164779-stats.html.gz", 164779),  # standard
    ("mapstats-164780-stats.html.gz", 164780),
    ("mapstats-173424-stats.html.gz", 173424),
    ("mapstats-174112-stats.html.gz", 174112),
    ("mapstats-174116-stats.html.gz", 174116),
    ("mapstats-179210-stats.html.gz", 179210),
    ("mapstats-188093-stats.html.gz", 188093),
    ("mapstats-206389-stats.html.gz", 206389),  # Extended OT (36 rounds, 2 containers)
    ("mapstats-206393-stats.html.gz", 206393),
    ("mapstats-219128-stats.html.gz", 219128),
    ("mapstats-219151-stats.html.gz", 219151),
]


def load_sample(filename: str) -> str:
    """Load and decompress a gzipped HTML sample."""
    path = RECON_DIR / filename
    if not path.exists():
        pytest.skip(f"Sample HTML not found: {path}")
    return gzip.decompress(path.read_bytes()).decode("utf-8")


# ---------------------------------------------------------------------------
# TestScoreboardExtraction -- Rating 3.0 standard (164779)
# ---------------------------------------------------------------------------
class TestScoreboardExtraction:
    """Test per-player scoreboard extraction against 9 Pandas vs FORZE."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("mapstats-164779-stats.html.gz")
        self.result = parse_map_stats(html, 164779)

    def test_ten_players_extracted(self):
        assert len(self.result.players) == 10

    def test_five_per_team(self):
        left_players = [p for p in self.result.players if p.team_id == self.result.team_left_id]
        right_players = [p for p in self.result.players if p.team_id == self.result.team_right_id]
        assert len(left_players) == 5
        assert len(right_players) == 5

    def test_player_ids_positive(self):
        for p in self.result.players:
            assert p.player_id > 0

    def test_player_names_not_empty(self):
        for p in self.result.players:
            assert isinstance(p.player_name, str)
            assert len(p.player_name) > 0

    def test_kills_deaths_assists_are_nonnegative(self):
        for p in self.result.players:
            assert p.kills >= 0
            assert p.deaths >= 0
            assert p.assists >= 0

    def test_hs_kills_lte_kills(self):
        for p in self.result.players:
            assert p.hs_kills <= p.kills

    def test_adr_is_positive(self):
        for p in self.result.players:
            assert 0 < p.adr < 200

    def test_kast_is_percentage(self):
        for p in self.result.players:
            assert 0 <= p.kast <= 100

    def test_rating_is_reasonable(self):
        for p in self.result.players:
            assert 0.0 < p.rating < 3.0

    def test_kd_diff_computed_correctly(self):
        for p in self.result.players:
            assert p.kd_diff == p.kills - p.deaths

    def test_fk_diff_computed_correctly(self):
        for p in self.result.players:
            assert p.fk_diff == p.opening_kills - p.opening_deaths


# ---------------------------------------------------------------------------
# TestOlderSampleHandling -- older sample (162345)
# ---------------------------------------------------------------------------
class TestOlderSampleHandling:
    """Test parser against older sample 162345."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("mapstats-162345-stats.html.gz")
        self.result = parse_map_stats(html, 162345)

    def test_round_swing_is_float(self):
        for p in self.result.players:
            assert isinstance(p.round_swing, float)

    def test_scoreboard_extracted_completely(self):
        assert len(self.result.players) == 10
        # At least some players should have non-zero kills
        players_with_kills = [p for p in self.result.players if p.kills > 0]
        assert len(players_with_kills) >= 5

    def test_rating_value_reasonable(self):
        for p in self.result.players:
            assert 0.0 < p.rating < 3.0


# ---------------------------------------------------------------------------
# TestModernSampleHandling -- modern sample (219128)
# ---------------------------------------------------------------------------
class TestModernSampleHandling:
    """Test parser against modern sample 219128."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("mapstats-219128-stats.html.gz")
        self.result = parse_map_stats(html, 219128)

    def test_round_swing_extracted(self):
        for p in self.result.players:
            assert isinstance(p.round_swing, float)


# ---------------------------------------------------------------------------
# TestRoundHistoryStandard -- standard match (164779)
# ---------------------------------------------------------------------------
class TestRoundHistoryStandard:
    """Test round history extraction against a standard (no OT) match."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("mapstats-164779-stats.html.gz")
        self.result = parse_map_stats(html, 164779)

    def test_rounds_extracted(self):
        assert len(self.result.rounds) > 0

    def test_round_numbers_sequential(self):
        numbers = [r.round_number for r in self.result.rounds]
        assert numbers == list(range(1, len(self.result.rounds) + 1))

    def test_round_count_matches_score(self):
        total_score = self.result.team_left_score + self.result.team_right_score
        assert len(self.result.rounds) == total_score

    def test_winner_sides_valid(self):
        for r in self.result.rounds:
            assert r.winner_side in ("CT", "T")

    def test_win_types_valid(self):
        for r in self.result.rounds:
            assert r.win_type in ("elimination", "bomb_planted", "defuse", "time")

    def test_winner_team_ids_valid(self):
        valid_ids = {self.result.team_left_id, self.result.team_right_id}
        for r in self.result.rounds:
            assert r.winner_team_id in valid_ids


# ---------------------------------------------------------------------------
# TestSingleOvertimeRounds -- single OT (162345, 30 rounds)
# ---------------------------------------------------------------------------
class TestSingleOvertimeRounds:
    """Test round history for single OT (16-14, 30 total rounds)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("mapstats-162345-stats.html.gz")
        self.result = parse_map_stats(html, 162345)

    def test_round_count_exceeds_24(self):
        assert len(self.result.rounds) > 24

    def test_round_count_matches_score(self):
        total_score = self.result.team_left_score + self.result.team_right_score
        assert len(self.result.rounds) == total_score

    def test_rounds_sequential_through_ot(self):
        numbers = [r.round_number for r in self.result.rounds]
        assert numbers == list(range(1, len(self.result.rounds) + 1))


# ---------------------------------------------------------------------------
# TestExtendedOvertimeRounds -- extended OT (206389, 36 rounds, 2 containers)
# ---------------------------------------------------------------------------
class TestExtendedOvertimeRounds:
    """Test round history for extended OT (19-17, 36 total rounds)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("mapstats-206389-stats.html.gz")
        self.result = parse_map_stats(html, 206389)

    def test_round_count_exceeds_30(self):
        assert len(self.result.rounds) > 30

    def test_round_count_matches_score(self):
        total_score = self.result.team_left_score + self.result.team_right_score
        assert len(self.result.rounds) == total_score

    def test_rounds_sequential_through_extended_ot(self):
        numbers = [r.round_number for r in self.result.rounds]
        assert numbers == list(range(1, len(self.result.rounds) + 1))


# ---------------------------------------------------------------------------
# TestMapMetadata -- standard sample (164779)
# ---------------------------------------------------------------------------
class TestMapMetadata:
    """Test map-level metadata extraction."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("mapstats-164779-stats.html.gz")
        self.result = parse_map_stats(html, 164779)

    def test_map_name_extracted(self):
        known_maps = {
            "Nuke", "Anubis", "Mirage", "Inferno", "Overpass", "Vertigo",
            "Ancient", "Dust2", "Train", "Cache",
        }
        assert isinstance(self.result.map_name, str)
        assert self.result.map_name in known_maps

    def test_team_names_extracted(self):
        assert isinstance(self.result.team_left_name, str)
        assert len(self.result.team_left_name) > 0
        assert isinstance(self.result.team_right_name, str)
        assert len(self.result.team_right_name) > 0

    def test_team_ids_positive(self):
        assert self.result.team_left_id > 0
        assert self.result.team_right_id > 0

    def test_scores_are_nonneg_integers(self):
        assert isinstance(self.result.team_left_score, int)
        assert isinstance(self.result.team_right_score, int)
        assert self.result.team_left_score >= 0
        assert self.result.team_right_score >= 0

    def test_mapstatsid_matches(self):
        assert self.result.mapstatsid == 164779


# ---------------------------------------------------------------------------
# TestHalfBreakdown -- standard sample (164779)
# ---------------------------------------------------------------------------
class TestHalfBreakdown:
    """Test CT/T half breakdown extraction."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("mapstats-164779-stats.html.gz")
        self.result = parse_map_stats(html, 164779)

    def test_half_values_nonnegative(self):
        assert self.result.team_left_ct_rounds >= 0
        assert self.result.team_left_t_rounds >= 0
        assert self.result.team_right_ct_rounds >= 0
        assert self.result.team_right_t_rounds >= 0

    def test_starting_side_valid(self):
        assert self.result.team_left_starting_side in ("CT", "T")

    def test_halves_sum_to_regulation(self):
        """CT + T rounds for both teams should sum to regulation rounds (max 24)."""
        total = (
            self.result.team_left_ct_rounds
            + self.result.team_left_t_rounds
            + self.result.team_right_ct_rounds
            + self.result.team_right_t_rounds
        )
        total_score = self.result.team_left_score + self.result.team_right_score
        # For non-OT matches, halves == total. For OT, halves <= 24.
        assert total <= min(total_score, 24)


# ---------------------------------------------------------------------------
# TestAllSamplesParseWithoutCrash -- smoke test across all 12 samples
# ---------------------------------------------------------------------------
class TestAllSamplesParseWithoutCrash:
    """Smoke test: all 12 samples parse without exception."""

    @pytest.mark.parametrize("filename,mapstatsid", ALL_SAMPLES)
    def test_all_samples_parse(self, filename, mapstatsid):
        html = load_sample(filename)
        result = parse_map_stats(html, mapstatsid)
        assert isinstance(result, MapStats)
        assert result.mapstatsid == mapstatsid
        assert len(result.players) == 10
        assert len(result.rounds) > 0
        assert result.team_left_id > 0
        assert result.team_right_id > 0
        assert isinstance(result.team_left_name, str)
        assert isinstance(result.team_right_name, str)
        assert len(result.team_left_name) > 0
        assert len(result.team_right_name) > 0
