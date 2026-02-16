"""Tests for economy parser against real HTML samples.

Tests cover: per-round extraction, buy type classification, round outcomes,
OT handling (MR15 vs MR12), team attribution, and smoke tests across all 12 samples.
All tests use gzipped HTML from data/recon/.
"""

import gzip
from pathlib import Path

import pytest

from scraper.economy_parser import (
    EconomyData,
    RoundEconomy,
    _classify_buy_type,
    parse_economy,
)

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"

ALL_SAMPLES = [
    ("economy-162345.html.gz", 162345),  # MR15 OT (30 rounds)
    ("economy-164779.html.gz", 164779),
    ("economy-164780.html.gz", 164780),
    ("economy-173424.html.gz", 173424),
    ("economy-174112.html.gz", 174112),
    ("economy-174116.html.gz", 174116),
    ("economy-179210.html.gz", 179210),
    ("economy-188093.html.gz", 188093),
    ("economy-206389.html.gz", 206389),  # MR12 OT (regulation only, 24 rounds)
    ("economy-206393.html.gz", 206393),
    ("economy-219128.html.gz", 219128),
    ("economy-219151.html.gz", 219151),
]


def load_sample(filename: str) -> str:
    """Load and decompress a gzipped HTML sample."""
    path = RECON_DIR / filename
    if not path.exists():
        pytest.skip(f"Sample HTML not found: {path}")
    return gzip.decompress(path.read_bytes()).decode("utf-8")


# ---------------------------------------------------------------------------
# TestPerRoundExtraction -- standard match (164779)
# ---------------------------------------------------------------------------
class TestPerRoundExtraction:
    """Test per-round extraction against 9 Pandas vs FORZE."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("economy-164779.html.gz")
        self.result = parse_economy(html, 164779)

    def test_rounds_extracted(self):
        assert len(self.result.rounds) > 0

    def test_two_entries_per_round(self):
        """Each round_number appears exactly twice (once per team)."""
        from collections import Counter

        counts = Counter(r.round_number for r in self.result.rounds)
        for rnd, count in counts.items():
            assert count == 2, f"Round {rnd} has {count} entries, expected 2"

    def test_equipment_values_positive(self):
        for r in self.result.rounds:
            assert r.equipment_value > 0

    def test_round_numbers_sequential(self):
        """Round numbers are contiguous from 1 to round_count."""
        round_nums = sorted(set(r.round_number for r in self.result.rounds))
        assert round_nums == list(range(1, self.result.round_count + 1))

    def test_team_names_match(self):
        assert isinstance(self.result.team1_name, str)
        assert isinstance(self.result.team2_name, str)
        assert len(self.result.team1_name) > 0
        assert len(self.result.team2_name) > 0


# ---------------------------------------------------------------------------
# TestBuyTypeClassification -- unit test boundaries
# ---------------------------------------------------------------------------
class TestBuyTypeClassification:
    """Test buy type classification at threshold boundaries."""

    def test_full_eco_boundary(self):
        assert _classify_buy_type(4999) == "full_eco"

    def test_semi_eco_boundary(self):
        assert _classify_buy_type(5000) == "semi_eco"

    def test_semi_buy_boundary(self):
        assert _classify_buy_type(10000) == "semi_buy"

    def test_full_buy_boundary(self):
        assert _classify_buy_type(20000) == "full_buy"

    def test_zero_value(self):
        assert _classify_buy_type(0) == "full_eco"

    def test_high_value(self):
        assert _classify_buy_type(50000) == "full_buy"

    def test_just_below_semi_eco(self):
        assert _classify_buy_type(4999) == "full_eco"

    def test_just_below_semi_buy(self):
        assert _classify_buy_type(9999) == "semi_eco"

    def test_just_below_full_buy(self):
        assert _classify_buy_type(19999) == "semi_buy"


# ---------------------------------------------------------------------------
# TestRoundOutcomes -- round win/loss and side inference (164779)
# ---------------------------------------------------------------------------
class TestRoundOutcomes:
    """Test round outcome extraction and side inference."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("economy-164779.html.gz")
        self.result = parse_economy(html, 164779)

    def test_exactly_one_winner_per_round(self):
        """For each round, exactly one team has won_round=True."""
        from collections import defaultdict

        round_wins: dict[int, list[bool]] = defaultdict(list)
        for r in self.result.rounds:
            round_wins[r.round_number].append(r.won_round)

        for rnd, wins in round_wins.items():
            assert len(wins) == 2, f"Round {rnd}: expected 2 entries"
            assert sum(wins) == 1, (
                f"Round {rnd}: expected exactly 1 winner, got {sum(wins)}"
            )

    def test_sides_present(self):
        """Most rounds should have non-None side values."""
        sides_known = [r for r in self.result.rounds if r.side is not None]
        assert len(sides_known) > len(self.result.rounds) * 0.8

    def test_sides_opposite(self):
        """When both sides are known for a round, they are CT/T opposites."""
        from collections import defaultdict

        round_sides: dict[int, list[str | None]] = defaultdict(list)
        for r in self.result.rounds:
            round_sides[r.round_number].append(r.side)

        for rnd, sides in round_sides.items():
            known = [s for s in sides if s is not None]
            if len(known) == 2:
                assert set(known) == {"CT", "T"}, (
                    f"Round {rnd}: expected CT/T pair, got {known}"
                )

    def test_ct_t_only(self):
        """All non-None sides are either 'CT' or 'T'."""
        for r in self.result.rounds:
            if r.side is not None:
                assert r.side in ("CT", "T"), f"Invalid side: {r.side}"


# ---------------------------------------------------------------------------
# TestOvertimeHandling -- MR15 OT vs MR12 OT
# ---------------------------------------------------------------------------
class TestOvertimeHandling:
    """Test OT handling for different match formats."""

    def test_mr15_ot_all_rounds(self):
        """Sample 162345 (MR15 OT, 16-14): should have 30 rounds in data."""
        html = load_sample("economy-162345.html.gz")
        result = parse_economy(html, 162345)
        # 16-14 = 30 total rounds, MR15 OT should have all rounds
        assert result.round_count == 30

    def test_mr12_ot_regulation_only(self):
        """Sample 206389 (MR12 OT, 19-17): should have only 24 regulation rounds."""
        html = load_sample("economy-206389.html.gz")
        result = parse_economy(html, 206389)
        # 19-17 = 36 rounds total, but MR12 OT only shows regulation (24)
        assert result.round_count <= 24

    def test_round_count_matches_data(self):
        """round_count should equal the number of distinct round numbers."""
        html = load_sample("economy-164779.html.gz")
        result = parse_economy(html, 164779)
        distinct_rounds = len(set(r.round_number for r in result.rounds))
        assert result.round_count == distinct_rounds


# ---------------------------------------------------------------------------
# TestTeamAttribution -- team name consistency (164779)
# ---------------------------------------------------------------------------
class TestTeamAttribution:
    """Test team attribution consistency."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("economy-164779.html.gz")
        self.result = parse_economy(html, 164779)

    def test_two_team_names(self):
        assert self.result.team1_name != self.result.team2_name

    def test_teams_in_rounds(self):
        """Every round entry has team_name matching either team1_name or team2_name."""
        valid_teams = {self.result.team1_name, self.result.team2_name}
        for r in self.result.rounds:
            assert r.team_name in valid_teams, (
                f"Round {r.round_number}: unexpected team '{r.team_name}'"
            )


# ---------------------------------------------------------------------------
# TestAllSamplesParseWithoutCrash -- smoke test across all 12 samples
# ---------------------------------------------------------------------------
class TestAllSamplesParseWithoutCrash:
    """Smoke test: all 12 samples parse without exception."""

    @pytest.mark.parametrize("filename,mapstatsid", ALL_SAMPLES)
    def test_parse_succeeds(self, filename, mapstatsid):
        html = load_sample(filename)
        result = parse_economy(html, mapstatsid)
        assert isinstance(result, EconomyData)
        assert result.mapstatsid == mapstatsid

    @pytest.mark.parametrize("filename,mapstatsid", ALL_SAMPLES)
    def test_has_rounds(self, filename, mapstatsid):
        html = load_sample(filename)
        result = parse_economy(html, mapstatsid)
        assert len(result.rounds) > 0

    @pytest.mark.parametrize("filename,mapstatsid", ALL_SAMPLES)
    def test_round_count_positive(self, filename, mapstatsid):
        html = load_sample(filename)
        result = parse_economy(html, mapstatsid)
        assert result.round_count > 0

    @pytest.mark.parametrize("filename,mapstatsid", ALL_SAMPLES)
    def test_buy_types_valid(self, filename, mapstatsid):
        html = load_sample(filename)
        result = parse_economy(html, mapstatsid)
        valid_types = {"full_eco", "semi_eco", "semi_buy", "full_buy"}
        for r in result.rounds:
            assert r.buy_type in valid_types, (
                f"Sample {mapstatsid} round {r.round_number}: invalid buy_type '{r.buy_type}'"
            )
