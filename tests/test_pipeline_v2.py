from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scraper.config import ScraperConfig
from scraper.pipeline_v2 import _scrape_match


class DummyStorage:
    def save(self, *args, **kwargs):
        return None


class DummyClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def fetch(self, *args, **kwargs):
        return self._responses.pop(0)

    class _PinnedTab:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def pinned_tab(self):
        return self._PinnedTab()

    async def fetch_with_tab(self, tab, *args, **kwargs):
        return self._responses.pop(0)


def _parsed_overview():
    return SimpleNamespace(
        date_unix_ms=1_710_000_000_000,
        event_id=1,
        event_name="Event",
        team1_id=10,
        team1_name="Alpha",
        team2_id=20,
        team2_name="Beta",
        team1_score=2,
        team2_score=1,
        best_of=3,
        is_lan=False,
        is_forfeit=False,
        vetoes=[],
        maps=[
            SimpleNamespace(
                map_number=1,
                mapstatsid=101,
                map_name="Inferno",
                team1_rounds=13,
                team2_rounds=10,
                team1_ct_rounds=7,
                team1_t_rounds=6,
                team2_ct_rounds=5,
                team2_t_rounds=5,
            ),
            SimpleNamespace(
                map_number=2,
                mapstatsid=202,
                map_name="Nuke",
                team1_rounds=13,
                team2_rounds=11,
                team1_ct_rounds=8,
                team1_t_rounds=5,
                team2_ct_rounds=6,
                team2_t_rounds=5,
            ),
        ],
    )


def _map_parsed(player_id):
    player = SimpleNamespace(
        player_id=player_id,
        player_name=f"p{player_id}",
        team_id=10,
        kills=20,
        deaths=15,
        assists=5,
        flash_assists=1,
        hs_kills=10,
        kd_diff=5,
        adr=80.0,
        kast=70.0,
        fk_diff=1,
        rating=1.1,
        opening_kills=2,
        opening_deaths=1,
        multi_kills=3,
        clutch_wins=0,
        traded_deaths=1,
        round_swing=0,
        e_kills=0,
        e_deaths=0,
        e_hs_kills=0,
        e_kd_diff=0,
        e_adr=0.0,
        e_kast=0.0,
        e_opening_kills=0,
        e_opening_deaths=0,
        e_fk_diff=0,
        e_traded_deaths=0,
    )
    round_row = SimpleNamespace(
        round_number=1,
        winner_side="ct",
        win_type="elimination",
        winner_team_id=10,
    )
    return SimpleNamespace(players=[player], rounds=[round_row])


def _perf_parsed(player_id):
    return SimpleNamespace(
        players=[SimpleNamespace(
            player_id=player_id,
            player_name=f"p{player_id}",
            kpr=0.8,
            dpr=0.6,
            mk_rating=1.05,
        )],
        kill_matrix=[SimpleNamespace(
            matrix_type="duels",
            player1_id=player_id,
            player2_id=player_id + 1,
            player1_kills=1,
            player2_kills=0,
        )],
    )


def _econ_parsed():
    return SimpleNamespace(
        team1_name="Alpha",
        rounds=[SimpleNamespace(
            round_number=1,
            team_name="Alpha",
            equipment_value=20000,
            buy_type="full buy",
        )],
    )


@pytest.mark.asyncio
async def test_scrape_match_persists_partial_maps(monkeypatch):
    client = DummyClient([
        "<overview>",
        "<map1 stats>",
        "<map2 stats>",
        "<map1 perf>",
        "<map1 econ>",
    ])
    match_repo = MagicMock()

    monkeypatch.setattr(
        "scraper.pipeline_v2.parse_match_overview",
        lambda html, match_id: _parsed_overview(),
    )

    def fake_parse_map_stats(html, mapstatsid):
        if mapstatsid == 202:
            raise ValueError("missing data")
        return _map_parsed(player_id=111)

    monkeypatch.setattr("scraper.pipeline_v2.parse_map_stats", fake_parse_map_stats)
    monkeypatch.setattr(
        "scraper.pipeline_v2.parse_performance",
        lambda html, mapstatsid: _perf_parsed(111),
    )
    monkeypatch.setattr(
        "scraper.pipeline_v2.parse_economy",
        lambda html, mapstatsid: _econ_parsed(),
    )
    monkeypatch.setattr(
        "scraper.pipeline_v2.validate_and_quarantine",
        lambda data, model, ctx, repo: data,
    )
    monkeypatch.setattr(
        "scraper.pipeline_v2.validate_batch",
        lambda data, model, ctx, repo: (data, 0),
    )

    result = await _scrape_match(
        match_id=123,
        url="/matches/123/test",
        client=client,
        match_repo=match_repo,
        discovery_repo=MagicMock(),
        storage=DummyStorage(),
        config=ScraperConfig(save_html=False, page_load_wait=0.0),
    )

    assert result["ok"] is True
    assert result["maps_done"] == 1

    kwargs = match_repo.persist_complete_match.call_args.kwargs
    assert [m["mapstatsid"] for m in kwargs["maps_data"]] == [101]
    assert len(kwargs["all_stats"]) == 1
    assert len(kwargs["all_rounds"]) == 1
    assert len(kwargs["all_economy"]) == 1
    assert len(kwargs["all_kill_matrix"]) == 1


@pytest.mark.asyncio
async def test_scrape_match_fails_when_all_maps_fail(monkeypatch):
    client = DummyClient([
        "<overview>",
        "<map1 stats>",
        "<map2 stats>",
    ])
    match_repo = MagicMock()

    monkeypatch.setattr(
        "scraper.pipeline_v2.parse_match_overview",
        lambda html, match_id: _parsed_overview(),
    )
    monkeypatch.setattr(
        "scraper.pipeline_v2.parse_map_stats",
        lambda html, mapstatsid: (_ for _ in ()).throw(ValueError("missing data")),
    )
    monkeypatch.setattr(
        "scraper.pipeline_v2.validate_and_quarantine",
        lambda data, model, ctx, repo: data,
    )
    monkeypatch.setattr(
        "scraper.pipeline_v2.validate_batch",
        lambda data, model, ctx, repo: (data, 0),
    )

    result = await _scrape_match(
        match_id=123,
        url="/matches/123/test",
        client=client,
        match_repo=match_repo,
        discovery_repo=MagicMock(),
        storage=DummyStorage(),
        config=ScraperConfig(save_html=False, page_load_wait=0.0),
    )

    assert result["ok"] is False
    assert result["maps_done"] == 0
    match_repo.persist_complete_match.assert_not_called()
