"""Pydantic v2 validation model for match player records."""

from pydantic import BaseModel, Field


class MatchPlayerModel(BaseModel):
    """Validation model for a player roster entry on a match."""

    match_id: int = Field(gt=0)
    player_id: int = Field(gt=0)
    player_name: str | None = None
    team_id: int | None = Field(default=None, gt=0)
    team_num: int = Field(ge=1, le=2)
    scraped_at: str = Field(min_length=1)
    updated_at: str = ""
    source_url: str | None = None
    parser_version: str | None = None
