"""Pydantic v2 validation models for all HLTV database entity types.

Re-exports all model classes for convenient import::

    from scraper.models import MatchModel, PlayerStatsModel, ...
"""

from .economy import EconomyModel
from .kill_matrix import KillMatrixModel
from .map import MapModel
from .match import ForfeitMatchModel, MatchModel
from .player_stats import PlayerStatsModel
from .round_history import RoundHistoryModel
from .veto import VetoModel

__all__ = [
    "MatchModel",
    "ForfeitMatchModel",
    "MapModel",
    "PlayerStatsModel",
    "RoundHistoryModel",
    "EconomyModel",
    "VetoModel",
    "KillMatrixModel",
]
