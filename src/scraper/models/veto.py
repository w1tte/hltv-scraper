"""Pydantic v2 validation model for veto records."""

from pydantic import BaseModel, Field, field_validator


class VetoModel(BaseModel):
    """Validation model for a single veto step."""

    match_id: int = Field(gt=0)
    step_number: int = Field(ge=1)
    team_name: str | None = None
    action: str
    map_name: str
    scraped_at: str = Field(min_length=1)
    updated_at: str = ""
    source_url: str | None = None
    parser_version: str | None = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Action must be a known veto action."""
        valid = {"removed", "picked", "left_over"}
        if v not in valid:
            raise ValueError(
                f"action must be one of {valid}, got '{v}'"
            )
        return v
