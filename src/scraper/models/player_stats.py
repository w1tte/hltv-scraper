"""Pydantic v2 validation model for player stats records."""

import warnings

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


class PlayerStatsModel(BaseModel):
    """Validation model for per-player per-map statistics."""

    match_id: int = Field(gt=0)
    map_number: int = Field(ge=1, le=5)
    player_id: int = Field(gt=0)
    player_name: str | None = None
    team_id: int | None = Field(default=None, gt=0)
    # Core stats (from map stats page)
    kills: int | None = Field(default=None, ge=0)
    deaths: int | None = Field(default=None, ge=0)
    assists: int | None = Field(default=None, ge=0)
    flash_assists: int | None = Field(default=None, ge=0)
    hs_kills: int | None = Field(default=None, ge=0)
    kd_diff: int | None = None  # Can be negative
    adr: float | None = Field(default=None, ge=0.0)
    kast: float | None = Field(default=None, ge=0.0, le=100.0)
    fk_diff: int | None = None  # Can be negative
    rating: float | None = Field(default=None, ge=0.0)
    # Performance page stats (Phase 7, may be None until perf page scraped)
    kpr: float | None = Field(default=None, ge=0.0)
    dpr: float | None = Field(default=None, ge=0.0)
    # Phase 6 extended fields
    opening_kills: int | None = Field(default=None, ge=0)
    opening_deaths: int | None = Field(default=None, ge=0)
    multi_kills: int | None = Field(default=None, ge=0)
    clutch_wins: int | None = Field(default=None, ge=0)
    traded_deaths: int | None = Field(default=None, ge=0)
    round_swing: float | None = None  # Signed percentage, can be negative
    mk_rating: float | None = Field(default=None, ge=0.0)
    # Eco-adjusted stats (None for Rating 2.0 matches)
    e_kills: int | None = Field(default=None, ge=0)
    e_deaths: int | None = Field(default=None, ge=0)
    e_hs_kills: int | None = Field(default=None, ge=0)
    e_kd_diff: int | None = None  # Can be negative
    e_adr: float | None = Field(default=None, ge=0.0)
    e_kast: float | None = Field(default=None, ge=0.0)  # Can exceed 100% due to eco weighting
    e_opening_kills: int | None = Field(default=None, ge=0)
    e_opening_deaths: int | None = Field(default=None, ge=0)
    e_fk_diff: int | None = None  # Can be negative
    e_traded_deaths: int | None = Field(default=None, ge=0)
    # Provenance
    scraped_at: str = Field(min_length=1)
    updated_at: str = ""
    source_url: str | None = None
    parser_version: str | None = None

    @model_validator(mode="after")
    def check_kd_diff_consistency(self) -> Self:
        """kd_diff should equal kills - deaths when all three are present."""
        if (
            self.kills is not None
            and self.deaths is not None
            and self.kd_diff is not None
        ):
            expected = self.kills - self.deaths
            if self.kd_diff != expected:
                raise ValueError(
                    f"kd_diff ({self.kd_diff}) != kills ({self.kills}) - "
                    f"deaths ({self.deaths}) = {expected}"
                )
        return self

    @model_validator(mode="after")
    def check_fk_diff_consistency(self) -> Self:
        """fk_diff should equal opening_kills - opening_deaths when all present."""
        if (
            self.opening_kills is not None
            and self.opening_deaths is not None
            and self.fk_diff is not None
        ):
            expected = self.opening_kills - self.opening_deaths
            if self.fk_diff != expected:
                raise ValueError(
                    f"fk_diff ({self.fk_diff}) != opening_kills "
                    f"({self.opening_kills}) - opening_deaths "
                    f"({self.opening_deaths}) = {expected}"
                )
        return self

    @model_validator(mode="after")
    def check_e_kd_diff_consistency(self) -> Self:
        """e_kd_diff should equal e_kills - e_deaths when all three are present."""
        if (
            self.e_kills is not None
            and self.e_deaths is not None
            and self.e_kd_diff is not None
        ):
            expected = self.e_kills - self.e_deaths
            if self.e_kd_diff != expected:
                raise ValueError(
                    f"e_kd_diff ({self.e_kd_diff}) != e_kills ({self.e_kills}) - "
                    f"e_deaths ({self.e_deaths}) = {expected}"
                )
        return self

    @model_validator(mode="after")
    def check_e_fk_diff_consistency(self) -> Self:
        """e_fk_diff should equal e_opening_kills - e_opening_deaths when all present."""
        if (
            self.e_opening_kills is not None
            and self.e_opening_deaths is not None
            and self.e_fk_diff is not None
        ):
            expected = self.e_opening_kills - self.e_opening_deaths
            if self.e_fk_diff != expected:
                raise ValueError(
                    f"e_fk_diff ({self.e_fk_diff}) != e_opening_kills "
                    f"({self.e_opening_kills}) - e_opening_deaths "
                    f"({self.e_opening_deaths}) = {expected}"
                )
        return self

    @model_validator(mode="after")
    def check_hs_kills_le_kills(self) -> Self:
        """Headshot kills cannot exceed total kills."""
        if self.hs_kills is not None and self.kills is not None:
            if self.hs_kills > self.kills:
                raise ValueError(
                    f"hs_kills ({self.hs_kills}) > kills ({self.kills})"
                )
        return self

    @model_validator(mode="after")
    def warn_unusual_values(self) -> Self:
        """Warn on unusual but valid values."""
        if self.rating is not None and (
            self.rating < 0.1 or self.rating > 3.0
        ):
            warnings.warn(
                f"Unusual rating={self.rating} for player "
                f"{self.player_id} (match {self.match_id}, "
                f"map {self.map_number})",
                stacklevel=2,
            )
        if self.adr is not None and self.adr > 200.0:
            warnings.warn(
                f"Unusual adr={self.adr} for player "
                f"{self.player_id} (match {self.match_id}, "
                f"map {self.map_number})",
                stacklevel=2,
            )
        return self
