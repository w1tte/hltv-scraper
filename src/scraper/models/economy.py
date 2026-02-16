"""Pydantic v2 validation model for economy records."""

from pydantic import BaseModel, Field, field_validator


class EconomyModel(BaseModel):
    """Validation model for per-round per-team economy data."""

    match_id: int = Field(gt=0)
    map_number: int = Field(ge=1, le=5)
    round_number: int = Field(ge=1)
    team_id: int = Field(gt=0)
    equipment_value: int | None = Field(default=None, ge=0)
    buy_type: str | None = None
    scraped_at: str = Field(min_length=1)
    updated_at: str = ""
    source_url: str | None = None
    parser_version: str | None = None

    @field_validator("buy_type")
    @classmethod
    def validate_buy_type(cls, v: str | None) -> str | None:
        """Buy type must be a known category if provided."""
        if v is not None:
            valid = {"full_eco", "semi_eco", "semi_buy", "full_buy"}
            if v not in valid:
                raise ValueError(
                    f"buy_type must be one of {valid}, got '{v}'"
                )
        return v
