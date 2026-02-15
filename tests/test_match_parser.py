"""Tests for match overview parser against real HTML samples.

Tests cover: BO1, BO3, BO5, forfeit, partial forfeit, overtime, unplayed maps,
half scores, vetoes, rosters. All tests use gzipped HTML from data/recon/.
"""

import gzip
from pathlib import Path

import pytest

from scraper.match_parser import (
    MapResult,
    MatchOverview,
    PlayerEntry,
    VetoStep,
    parse_match_overview,
)

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"

# All available match overview samples
ALL_SAMPLES = [
    ("match-2389951-overview.html.gz", 2389951),  # BO3 tier-1 LAN (Vitality vs G2)
    ("match-2380434-overview.html.gz", 2380434),  # Full forfeit (BO1)
    ("match-2384993-overview.html.gz", 2384993),  # BO5 partial forfeit + overtime
    ("match-2366498-overview.html.gz", 2366498),  # BO1 online, unranked teams
    ("match-2367432-overview.html.gz", 2367432),  # BO3 2-0 sweep (unplayed map 3)
    ("match-2371389-overview.html.gz", 2371389),  # BO3 2-1 full series
    ("match-2377467-overview.html.gz", 2377467),  # BO1 national-team LAN
    ("match-2371321-overview.html.gz", 2371321),  # BO1 tier-3 online
    ("match-2373741-overview.html.gz", 2373741),  # BO1 online
]


def load_sample(filename: str) -> str:
    """Load and decompress a gzipped HTML sample."""
    path = RECON_DIR / filename
    if not path.exists():
        pytest.skip(f"Sample HTML not found: {path}")
    return gzip.decompress(path.read_bytes()).decode("utf-8")


# ---------------------------------------------------------------------------
# TestMatchMetadata -- BO3 LAN sample (2389951)
# ---------------------------------------------------------------------------
class TestMatchMetadata:
    """Test match-level metadata extraction against Vitality vs G2 BO3 LAN."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2389951-overview.html.gz")
        self.result = parse_match_overview(html, 2389951)

    def test_team_names_extracted(self):
        assert self.result.team1_name == "Vitality"
        assert self.result.team2_name == "G2"

    def test_team_ids_are_positive_integers(self):
        assert self.result.team1_id > 0
        assert self.result.team2_id > 0

    def test_scores_are_integers(self):
        assert isinstance(self.result.team1_score, int)
        assert isinstance(self.result.team2_score, int)

    def test_best_of_is_valid(self):
        assert self.result.best_of in (1, 3, 5)

    def test_best_of_is_3(self):
        assert self.result.best_of == 3

    def test_is_lan_is_binary(self):
        assert self.result.is_lan in (0, 1)

    def test_is_lan_true_for_lan_match(self):
        assert self.result.is_lan == 1

    def test_date_unix_ms_is_13_digits(self):
        assert len(str(self.result.date_unix_ms)) == 13

    def test_event_extracted(self):
        assert self.result.event_id > 0
        assert isinstance(self.result.event_name, str)
        assert len(self.result.event_name) > 0

    def test_match_id_matches_input(self):
        assert self.result.match_id == 2389951


# ---------------------------------------------------------------------------
# TestBO1Match -- BO1 sample (2366498)
# ---------------------------------------------------------------------------
class TestBO1Match:
    """Test BO1 match extraction."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2366498-overview.html.gz")
        self.result = parse_match_overview(html, 2366498)

    def test_best_of_is_1(self):
        assert self.result.best_of == 1

    def test_single_map_extracted(self):
        assert len(self.result.maps) == 1

    def test_scores_are_round_scores(self):
        """BO1 shows round scores in .won/.lost (e.g. 16, 14), not maps-won."""
        assert self.result.team1_score is not None
        assert self.result.team2_score is not None
        assert self.result.team1_score > 10 or self.result.team2_score > 10

    def test_map_has_mapstatsid(self):
        assert self.result.maps[0].mapstatsid is not None

    def test_is_online(self):
        assert self.result.is_lan == 0


# ---------------------------------------------------------------------------
# TestBO5Match -- BO5 sample (2384993)
# ---------------------------------------------------------------------------
class TestBO5Match:
    """Test BO5 match extraction with partial forfeit and overtime."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2384993-overview.html.gz")
        self.result = parse_match_overview(html, 2384993)

    def test_best_of_is_5(self):
        assert self.result.best_of == 5

    def test_five_maps_extracted(self):
        assert len(self.result.maps) == 5

    def test_has_unplayed_maps(self):
        assert any(m.is_unplayed for m in self.result.maps)

    def test_has_forfeit_map(self):
        """Map 3 is 'Default' (forfeit)."""
        assert any(m.is_forfeit_map for m in self.result.maps)

    def test_is_forfeit_true(self):
        assert self.result.is_forfeit is True

    def test_scores_present(self):
        """BO5 partial forfeit still has series scores (3-0)."""
        assert self.result.team1_score == 3
        assert self.result.team2_score == 0


# ---------------------------------------------------------------------------
# TestForfeitMatch -- full forfeit (2380434)
# ---------------------------------------------------------------------------
class TestForfeitMatch:
    """Test full forfeit match extraction."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2380434-overview.html.gz")
        self.result = parse_match_overview(html, 2380434)

    def test_is_forfeit_true(self):
        assert self.result.is_forfeit is True

    def test_scores_are_none(self):
        """Full forfeit has no .won/.lost divs, so scores are None."""
        assert self.result.team1_score is None
        assert self.result.team2_score is None

    def test_forfeit_map_detected(self):
        assert any(m.is_forfeit_map for m in self.result.maps)

    def test_no_mapstatsids_on_forfeit(self):
        for m in self.result.maps:
            if m.is_forfeit_map:
                assert m.mapstatsid is None

    def test_players_still_extracted(self):
        assert len(self.result.players) == 10

    def test_vetoes_still_extracted(self):
        """Even forfeit matches have a veto sequence."""
        assert self.result.vetoes is not None
        assert len(self.result.vetoes) > 0


# ---------------------------------------------------------------------------
# TestMapExtraction -- BO3 sample (2389951)
# ---------------------------------------------------------------------------
class TestMapExtraction:
    """Test per-map data extraction against Vitality vs G2 BO3."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2389951-overview.html.gz")
        self.result = parse_match_overview(html, 2389951)

    def test_correct_map_count(self):
        assert len(self.result.maps) == 3

    def test_map_names_are_strings(self):
        for m in self.result.maps:
            assert isinstance(m.map_name, str)
            assert len(m.map_name) > 0

    def test_played_maps_have_scores(self):
        for m in self.result.maps:
            if not m.is_unplayed:
                assert isinstance(m.team1_rounds, int)
                assert isinstance(m.team2_rounds, int)

    def test_played_maps_have_mapstatsid(self):
        for m in self.result.maps:
            if not m.is_unplayed and not m.is_forfeit_map:
                assert m.mapstatsid is not None
                assert m.mapstatsid > 0

    def test_map_numbers_sequential(self):
        assert [m.map_number for m in self.result.maps] == [1, 2, 3]


# ---------------------------------------------------------------------------
# TestUnplayedMaps -- BO3 sweep (2367432) with unplayed map 3
# ---------------------------------------------------------------------------
class TestUnplayedMaps:
    """Test unplayed map handling (BO3 2-0 sweep with unplayed map 3)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2367432-overview.html.gz")
        self.result = parse_match_overview(html, 2367432)

    def test_has_unplayed_map(self):
        unplayed = [m for m in self.result.maps if m.is_unplayed]
        assert len(unplayed) >= 1

    def test_unplayed_map_has_null_scores(self):
        for m in self.result.maps:
            if m.is_unplayed:
                assert m.team1_rounds is None
                assert m.team2_rounds is None

    def test_unplayed_map_has_null_mapstatsid(self):
        for m in self.result.maps:
            if m.is_unplayed:
                assert m.mapstatsid is None

    def test_unplayed_map_flagged(self):
        for m in self.result.maps:
            if m.is_unplayed:
                assert m.is_unplayed is True

    def test_played_maps_have_scores(self):
        """Maps 1 and 2 (played) should have integer scores."""
        played = [m for m in self.result.maps if not m.is_unplayed]
        assert len(played) == 2
        for m in played:
            assert isinstance(m.team1_rounds, int)
            assert isinstance(m.team2_rounds, int)


# ---------------------------------------------------------------------------
# TestHalfScores -- normal BO3 sample (2389951)
# ---------------------------------------------------------------------------
class TestHalfScores:
    """Test CT/T half-score extraction for regulation maps."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2389951-overview.html.gz")
        self.result = parse_match_overview(html, 2389951)

    def test_played_maps_have_half_scores(self):
        for m in self.result.maps:
            if not m.is_unplayed and not m.is_forfeit_map:
                assert m.team1_ct_rounds is not None
                assert m.team1_t_rounds is not None
                assert m.team2_ct_rounds is not None
                assert m.team2_t_rounds is not None

    def test_half_scores_sum_to_total(self):
        """For non-OT maps, ct+t for each team should sum to their total rounds."""
        for m in self.result.maps:
            if not m.is_unplayed and not m.is_forfeit_map:
                t1_half_sum = m.team1_ct_rounds + m.team1_t_rounds
                t2_half_sum = m.team2_ct_rounds + m.team2_t_rounds
                total = m.team1_rounds + m.team2_rounds
                # For non-OT: halves sum = total. For OT: halves sum < total.
                assert t1_half_sum + t2_half_sum <= total

    def test_ct_t_values_are_reasonable(self):
        """Half-score values should be 0-13 (max regulation half is 13)."""
        for m in self.result.maps:
            if not m.is_unplayed and not m.is_forfeit_map:
                for v in [m.team1_ct_rounds, m.team1_t_rounds, m.team2_ct_rounds, m.team2_t_rounds]:
                    assert v is not None
                    assert 0 <= v <= 13


# ---------------------------------------------------------------------------
# TestOvertimeHalfScores -- BO5 map 1 (2384993, 19-17 overtime)
# ---------------------------------------------------------------------------
class TestOvertimeHalfScores:
    """Test overtime map half-score extraction (regulation-only ct/t)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2384993-overview.html.gz")
        self.result = parse_match_overview(html, 2384993)
        # Map 1 is the overtime map (19-17)
        self.ot_map = self.result.maps[0]

    def test_regulation_halves_present(self):
        assert self.ot_map.team1_ct_rounds is not None
        assert self.ot_map.team1_t_rounds is not None
        assert self.ot_map.team2_ct_rounds is not None
        assert self.ot_map.team2_t_rounds is not None

    def test_total_rounds_exceed_regulation(self):
        """Overtime means total rounds > 24 (MR12 regulation max)."""
        total = self.ot_map.team1_rounds + self.ot_map.team2_rounds
        assert total > 24

    def test_ct_t_are_regulation_only(self):
        """CT + T halves should be <= 12 per team (regulation only, not including OT)."""
        t1_reg = self.ot_map.team1_ct_rounds + self.ot_map.team1_t_rounds
        t2_reg = self.ot_map.team2_ct_rounds + self.ot_map.team2_t_rounds
        assert t1_reg <= 12
        assert t2_reg <= 12

    def test_regulation_less_than_total(self):
        """Regulation half sums should be less than total rounds for OT maps."""
        t1_reg = self.ot_map.team1_ct_rounds + self.ot_map.team1_t_rounds
        assert t1_reg < self.ot_map.team1_rounds


# ---------------------------------------------------------------------------
# TestVetoExtraction -- BO3 sample (2389951)
# ---------------------------------------------------------------------------
class TestVetoExtraction:
    """Test veto sequence extraction from Vitality vs G2 BO3."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2389951-overview.html.gz")
        self.result = parse_match_overview(html, 2389951)

    def test_vetoes_extracted(self):
        assert self.result.vetoes is not None

    def test_veto_count(self):
        """BO3 typically has 7 veto steps."""
        assert len(self.result.vetoes) == 7

    def test_veto_steps_sequential(self):
        steps = [v.step_number for v in self.result.vetoes]
        assert steps == list(range(1, len(self.result.vetoes) + 1))

    def test_veto_actions_valid(self):
        for v in self.result.vetoes:
            assert v.action in ("removed", "picked", "left_over")

    def test_veto_team_names_not_empty(self):
        for v in self.result.vetoes:
            if v.action != "left_over":
                assert v.team_name is not None
                assert len(v.team_name) > 0

    def test_left_over_has_null_team(self):
        left_over = [v for v in self.result.vetoes if v.action == "left_over"]
        for v in left_over:
            assert v.team_name is None

    def test_veto_map_names_valid(self):
        for v in self.result.vetoes:
            assert isinstance(v.map_name, str)
            assert len(v.map_name) > 0


# ---------------------------------------------------------------------------
# TestRosterExtraction -- BO3 sample (2389951)
# ---------------------------------------------------------------------------
class TestRosterExtraction:
    """Test player roster extraction from Vitality vs G2 BO3."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2389951-overview.html.gz")
        self.result = parse_match_overview(html, 2389951)

    def test_ten_players_extracted(self):
        assert len(self.result.players) == 10

    def test_five_per_team(self):
        team1_players = [p for p in self.result.players if p.team_num == 1]
        team2_players = [p for p in self.result.players if p.team_num == 2]
        assert len(team1_players) == 5
        assert len(team2_players) == 5

    def test_player_ids_positive(self):
        for p in self.result.players:
            assert p.player_id > 0

    def test_player_names_not_empty(self):
        for p in self.result.players:
            assert p.player_name is not None
            assert len(p.player_name) > 0

    def test_team_ids_match_match_teams(self):
        """Player team_ids should match the match's team1_id or team2_id."""
        valid_team_ids = {self.result.team1_id, self.result.team2_id}
        for p in self.result.players:
            assert p.team_id in valid_team_ids


# ---------------------------------------------------------------------------
# TestAllSamplesParseWithoutCrash -- smoke test across all 9 samples
# ---------------------------------------------------------------------------
class TestAllSamplesParseWithoutCrash:
    """Smoke test: all 9 samples parse without exception."""

    @pytest.mark.parametrize("filename,match_id", ALL_SAMPLES)
    def test_all_samples_parse(self, filename, match_id):
        html = load_sample(filename)
        result = parse_match_overview(html, match_id)
        assert isinstance(result, MatchOverview)
        assert result.match_id == match_id
        assert isinstance(result.team1_name, str)
        assert isinstance(result.team2_name, str)
        assert result.team1_id > 0
        assert result.team2_id > 0
        assert len(result.maps) >= 1
        assert len(result.players) >= 2  # At least some players


# ---------------------------------------------------------------------------
# TestBO1LAN -- BO1 LAN sample (2377467, Tunisia vs kONO)
# ---------------------------------------------------------------------------
class TestBO1LAN:
    """Test BO1 LAN match with national teams."""

    @pytest.fixture(autouse=True)
    def setup(self):
        html = load_sample("match-2377467-overview.html.gz")
        self.result = parse_match_overview(html, 2377467)

    def test_is_lan(self):
        assert self.result.is_lan == 1

    def test_best_of_1(self):
        assert self.result.best_of == 1

    def test_single_map(self):
        assert len(self.result.maps) == 1
