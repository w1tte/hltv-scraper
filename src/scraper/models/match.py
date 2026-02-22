"""Pydantic v2 validation models for match records.

MatchModel validates normal matches with score consistency checks.
ForfeitMatchModel validates forfeit matches with relaxed score rules.
"""

import warnings

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


class MatchModel(BaseModel):
    """Validation model for a normal (non-forfeit) match record."""

    match_id: int = Field(gt=0)
    date: str
    date_unix_ms: int | None = None  # epoch ms — exact start time
    event_id: int = Field(gt=0)
    event_name: str = Field(min_length=1)
    team1_id: int = Field(gt=0)
    team1_name: str = Field(min_length=1)
    team2_id: int = Field(gt=0)
    team2_name: str = Field(min_length=1)
    team1_score: int | None = None
    team2_score: int | None = None
    best_of: int = Field(ge=1, le=5)
    is_lan: int = Field(ge=0, le=1)
    match_url: str | None = None
    scraped_at: str = Field(min_length=1)
    updated_at: str = ""
    source_url: str | None = None
    parser_version: str | None = None

    @model_validator(mode="after")
    def check_scores_consistency(self) -> Self:
        """Scores must be consistent with best_of format.

        For BO1 the displayed score is the round score (e.g. 13-4), not a
        series score, so we only validate series scores for BO2+.
        """
        if self.team1_score is not None and self.team2_score is not None:
            if self.best_of >= 2:
                max_maps = (self.best_of + 1) // 2  # e.g., BO3 -> max 2 wins
                if self.team1_score > max_maps or self.team2_score > max_maps:
                    raise ValueError(
                        f"Score {self.team1_score}-{self.team2_score} exceeds "
                        f"max wins ({max_maps}) for BO{self.best_of}"
                    )
                # Winner should have exactly max_maps wins (except forfeit)
                winner_score = max(self.team1_score, self.team2_score)
                if winner_score < max_maps:
                    warnings.warn(
                        f"Winner has {winner_score} wins in BO{self.best_of} "
                        f"(expected {max_maps}) for match {self.match_id}",
                        stacklevel=2,
                    )
        return self

    @model_validator(mode="after")
    def check_teams_different(self) -> Self:
        """Teams should have different IDs."""
        if self.team1_id == self.team2_id:
            raise ValueError(
                f"team1_id and team2_id are identical ({self.team1_id})"
            )
        return self


class ForfeitMatchModel(BaseModel):
    """Lighter validation for forfeit matches -- no score consistency checks."""

    match_id: int = Field(gt=0)
    date: str
    date_unix_ms: int | None = None  # epoch ms — exact start time
    event_id: int = Field(gt=0)
    event_name: str = Field(min_length=1)
    team1_id: int = Field(gt=0)
    team1_name: str = Field(min_length=1)
    team2_id: int = Field(gt=0)
    team2_name: str = Field(min_length=1)
    team1_score: int | None = None
    team2_score: int | None = None
    best_of: int = Field(ge=1, le=5)
    is_lan: int = Field(ge=0, le=1)
    match_url: str | None = None
    scraped_at: str = Field(min_length=1)
    updated_at: str = ""
    source_url: str | None = None
    parser_version: str | None = None

    @model_validator(mode="after")
    def check_teams_different(self) -> Self:
        """Teams should have different IDs."""
        if self.team1_id == self.team2_id:
            raise ValueError(
                f"team1_id and team2_id are identical ({self.team1_id})"
            )
        return self
