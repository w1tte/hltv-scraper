"""Tests for performance page parser against real HTML samples.

Tests cover: player metrics extraction (KPR, DPR, KAST, ADR, rating),
kill matrix parsing (3 types, 5x5 grid), team overview, and smoke
tests across all 12 recon samples.
All tests use gzipped HTML from data/recon/.
"""

import gzip
from pathlib import Path

import pytest

from scraper.performance_parser import (
    KillMatrixEntry,
    PerformanceData,
    PlayerPerformance,
    TeamOverview,
    parse_performance,
)

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"

# All available performance page samples
ALL_SAMPLES = [
    # performance-162345 excluded: Rating 2.0 (CS:GO) sample, not CS2
    ("performance-164779.html.gz", 164779),
    ("performance-164780.html.gz", 164780),
    ("performance-173424.html.gz", 173424),
    ("performance-174112.html.gz", 174112),
    ("performance-174116.html.gz", 174116),
    ("performance-179210.html.gz", 179210),
    ("performance-188093.html.gz", 188093),
    ("performance-206389.html.gz", 206389),
    ("performance-206393.html.gz", 206393),
    ("performance-219128.html.gz", 219128),
    ("performance-219151.html.gz", 219151),
]


def load_sample(filename: str) -> str:
    """Load and decompress a gzipped HTML sample."""
    path = RECON_DIR / filename
    if not path.exists():
        pytest.skip(f"Sample HTML not found: {path}")
    return gzip.decompress(path.read_bytes()).decode("utf-8")


# ---------------------------------------------------------------------------
# TestPlayerMetricsExtraction -- Rating 3.0 standard (164779)
# ---------------------------------------------------------------------------
class TestPlayerMetricsExtraction:
    """Test per-player metrics extraction against 9 Pandas vs FORZE."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("performance-164779.html.gz")
        self.result = parse_performance(html, 164779)

    def test_ten_players_extracted(self):
        assert len(self.result.players) == 10

    def test_player_ids_non_zero(self):
        for p in self.result.players:
            assert p.player_id > 0

    def test_kpr_range(self):
        for p in self.result.players:
            assert 0.0 <= p.kpr <= 3.0

    def test_dpr_range(self):
        for p in self.result.players:
            assert 0.0 <= p.dpr <= 3.0

    def test_kast_range(self):
        for p in self.result.players:
            assert 0.0 <= p.kast <= 100.0

    def test_adr_range(self):
        for p in self.result.players:
            assert 0.0 <= p.adr <= 300.0

    def test_rating_range(self):
        for p in self.result.players:
            assert 0.0 <= p.rating <= 3.0

    def test_player_names_non_empty(self):
        for p in self.result.players:
            assert isinstance(p.player_name, str)
            assert len(p.player_name) > 0


# ---------------------------------------------------------------------------
# TestModernSampleHandling -- modern sample (219128)
# ---------------------------------------------------------------------------
class TestModernSampleHandling:
    """Test parser against modern sample 219128."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("performance-219128.html.gz")
        self.result = parse_performance(html, 219128)

    def test_mk_rating_present(self):
        for p in self.result.players:
            assert isinstance(p.mk_rating, float)
            assert p.mk_rating is not None

    def test_round_swing_present(self):
        for p in self.result.players:
            assert isinstance(p.round_swing, float)
            assert p.round_swing is not None

    def test_rating_reasonable(self):
        for p in self.result.players:
            assert 0.0 < p.rating < 3.0


# ---------------------------------------------------------------------------
# TestKillMatrixExtraction -- 3 types, 5x5 grid (164779)
# ---------------------------------------------------------------------------
class TestKillMatrixExtraction:
    """Test kill matrix extraction against 9 Pandas vs FORZE."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("performance-164779.html.gz")
        self.result = parse_performance(html, 164779)

    def test_three_matrix_types(self):
        types = {e.matrix_type for e in self.result.kill_matrix}
        assert types == {"all", "first_kill", "awp"}

    def test_matrix_entry_count(self):
        """25 entries per type (5x5 grid), 75 total."""
        assert len(self.result.kill_matrix) == 75

    def test_entries_per_type(self):
        for mtype in ("all", "first_kill", "awp"):
            entries = [e for e in self.result.kill_matrix if e.matrix_type == mtype]
            assert len(entries) == 25, f"Expected 25 entries for {mtype}, got {len(entries)}"

    def test_player_ids_non_zero(self):
        for e in self.result.kill_matrix:
            assert e.player1_id > 0
            assert e.player2_id > 0

    def test_kills_non_negative(self):
        for e in self.result.kill_matrix:
            assert e.player1_kills >= 0
            assert e.player2_kills >= 0

    def test_all_type_present(self):
        all_entries = [e for e in self.result.kill_matrix if e.matrix_type == "all"]
        assert len(all_entries) > 0


# ---------------------------------------------------------------------------
# TestTeamOverview -- team-level stats (164779)
# ---------------------------------------------------------------------------
class TestTeamOverview:
    """Test team overview extraction against 9 Pandas vs FORZE."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("performance-164779.html.gz")
        self.result = parse_performance(html, 164779)

    def test_two_teams(self):
        assert len(self.result.teams) == 2

    def test_team_names_non_empty(self):
        for t in self.result.teams:
            assert isinstance(t.team_name, str)
            assert len(t.team_name) > 0

    def test_kills_positive(self):
        for t in self.result.teams:
            assert t.total_kills > 0

    def test_deaths_positive(self):
        for t in self.result.teams:
            assert t.total_deaths > 0

    def test_assists_non_negative(self):
        for t in self.result.teams:
            assert t.total_assists >= 0


# ---------------------------------------------------------------------------
# TestAllSamplesParseWithoutCrash -- smoke test across all 12 samples
# ---------------------------------------------------------------------------
class TestAllSamplesParseWithoutCrash:
    """Smoke test: all 12 samples parse without exception."""

    @pytest.mark.parametrize("filename,mapstatsid", ALL_SAMPLES)
    def test_parse_succeeds(self, filename, mapstatsid):
        html = load_sample(filename)
        result = parse_performance(html, mapstatsid)
        assert isinstance(result, PerformanceData)
        assert result.mapstatsid == mapstatsid

    @pytest.mark.parametrize("filename,mapstatsid", ALL_SAMPLES)
    def test_has_players(self, filename, mapstatsid):
        html = load_sample(filename)
        result = parse_performance(html, mapstatsid)
        assert len(result.players) == 10

    @pytest.mark.parametrize("filename,mapstatsid", ALL_SAMPLES)
    def test_has_kill_matrix(self, filename, mapstatsid):
        html = load_sample(filename)
        result = parse_performance(html, mapstatsid)
        assert len(result.kill_matrix) > 0
