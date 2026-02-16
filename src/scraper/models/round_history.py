"""Pydantic v2 validation model for round history records."""

from pydantic import BaseModel, Field, field_validator


class RoundHistoryModel(BaseModel):
    """Validation model for a single round outcome."""

    match_id: int = Field(gt=0)
    map_number: int = Field(ge=1, le=5)
    round_number: int = Field(ge=1)
    winner_side: str
    win_type: str
    winner_team_id: int | None = None
    scraped_at: str = Field(min_length=1)
    updated_at: str = ""
    source_url: str | None = None
    parser_version: str | None = None

    @field_validator("winner_side")
    @classmethod
    def validate_winner_side(cls, v: str) -> str:
        """Winner side must be CT or T."""
        if v not in ("CT", "T"):
            raise ValueError(f"winner_side must be 'CT' or 'T', got '{v}'")
        return v

    @field_validator("win_type")
    @classmethod
    def validate_win_type(cls, v: str) -> str:
        """Win type must be a known round-end condition."""
        valid = {"elimination", "bomb_planted", "defuse", "time"}
        if v not in valid:
            raise ValueError(
                f"win_type must be one of {valid}, got '{v}'"
            )
        return v
