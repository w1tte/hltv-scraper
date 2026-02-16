"""Pydantic v2 validation model for map records."""

import warnings

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


class MapModel(BaseModel):
    """Validation model for a map record within a match series."""

    match_id: int = Field(gt=0)
    map_number: int = Field(ge=1, le=5)
    mapstatsid: int | None = Field(default=None, gt=0)
    map_name: str
    team1_rounds: int | None = Field(default=None, ge=0)
    team2_rounds: int | None = Field(default=None, ge=0)
    team1_ct_rounds: int | None = Field(default=None, ge=0)
    team1_t_rounds: int | None = Field(default=None, ge=0)
    team2_ct_rounds: int | None = Field(default=None, ge=0)
    team2_t_rounds: int | None = Field(default=None, ge=0)
    scraped_at: str = Field(min_length=1)
    updated_at: str = ""
    source_url: str | None = None
    parser_version: str | None = None

    @model_validator(mode="after")
    def check_half_scores_sum(self) -> Self:
        """CT + T rounds should not exceed total for each team.

        Uses <= (not ==) because overtime rounds are not broken down
        into CT/T halves in the data.
        """
        if (
            self.team1_ct_rounds is not None
            and self.team1_t_rounds is not None
            and self.team1_rounds is not None
        ):
            reg_sum = self.team1_ct_rounds + self.team1_t_rounds
            if reg_sum > self.team1_rounds:
                raise ValueError(
                    f"team1 half scores ({reg_sum}) exceed "
                    f"total ({self.team1_rounds})"
                )

        if (
            self.team2_ct_rounds is not None
            and self.team2_t_rounds is not None
            and self.team2_rounds is not None
        ):
            reg_sum = self.team2_ct_rounds + self.team2_t_rounds
            if reg_sum > self.team2_rounds:
                raise ValueError(
                    f"team2 half scores ({reg_sum}) exceed "
                    f"total ({self.team2_rounds})"
                )

        return self

    @model_validator(mode="after")
    def warn_extreme_rounds(self) -> Self:
        """Warn on extreme overtime (>50 total rounds)."""
        if (
            self.team1_rounds is not None
            and self.team2_rounds is not None
            and self.team1_rounds + self.team2_rounds > 50
        ):
            warnings.warn(
                f"Extreme round count: {self.team1_rounds}+{self.team2_rounds}"
                f"={self.team1_rounds + self.team2_rounds} "
                f"for match {self.match_id} map {self.map_number}",
                stacklevel=2,
            )
        return self
