"""Pydantic v2 validation model for kill matrix records."""

from pydantic import BaseModel, Field, field_validator


class KillMatrixModel(BaseModel):
    """Validation model for a head-to-head kill matrix entry."""

    match_id: int = Field(gt=0)
    map_number: int = Field(ge=1, le=5)
    matrix_type: str
    player1_id: int = Field(gt=0)
    player2_id: int = Field(gt=0)
    player1_kills: int = Field(ge=0)
    player2_kills: int = Field(ge=0)
    scraped_at: str = Field(min_length=1)
    updated_at: str = ""
    source_url: str | None = None
    parser_version: str | None = None

    @field_validator("matrix_type")
    @classmethod
    def validate_matrix_type(cls, v: str) -> str:
        """Matrix type must be a known kill matrix category."""
        valid = {"all", "first_kill", "awp"}
        if v not in valid:
            raise ValueError(
                f"matrix_type must be one of {valid}, got '{v}'"
            )
        return v
