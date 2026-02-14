"""Data access layer with UPSERT operations for all database tables.

Provides MatchRepository with insert-or-update semantics for matches,
maps, player_stats, round_history, and economy tables.  Each UPSERT
uses INSERT ... ON CONFLICT DO UPDATE SET (not INSERT OR REPLACE) to
modify rows in place without deleting them.

Batch methods wrap multiple upserts in a single atomic transaction.
Read methods return dicts (via sqlite3.Row) for easy consumption.
"""

import sqlite3

# ---------------------------------------------------------------------------
# UPSERT SQL constants
# ---------------------------------------------------------------------------

UPSERT_MATCH = """
    INSERT INTO matches (
        match_id, date, event_id, event_name,
        team1_id, team1_name, team2_id, team2_name,
        team1_score, team2_score, best_of, is_lan,
        match_url, scraped_at, updated_at, source_url, parser_version
    ) VALUES (
        :match_id, :date, :event_id, :event_name,
        :team1_id, :team1_name, :team2_id, :team2_name,
        :team1_score, :team2_score, :best_of, :is_lan,
        :match_url, :scraped_at, :scraped_at, :source_url, :parser_version
    )
    ON CONFLICT(match_id) DO UPDATE SET
        date           = excluded.date,
        event_id       = excluded.event_id,
        event_name     = excluded.event_name,
        team1_id       = excluded.team1_id,
        team1_name     = excluded.team1_name,
        team2_id       = excluded.team2_id,
        team2_name     = excluded.team2_name,
        team1_score    = excluded.team1_score,
        team2_score    = excluded.team2_score,
        best_of        = excluded.best_of,
        is_lan         = excluded.is_lan,
        match_url      = excluded.match_url,
        updated_at     = excluded.scraped_at,
        source_url     = excluded.source_url,
        parser_version = excluded.parser_version
"""

UPSERT_MAP = """
    INSERT INTO maps (
        match_id, map_number, mapstatsid, map_name,
        team1_rounds, team2_rounds,
        team1_ct_rounds, team1_t_rounds,
        team2_ct_rounds, team2_t_rounds,
        scraped_at, updated_at, source_url, parser_version
    ) VALUES (
        :match_id, :map_number, :mapstatsid, :map_name,
        :team1_rounds, :team2_rounds,
        :team1_ct_rounds, :team1_t_rounds,
        :team2_ct_rounds, :team2_t_rounds,
        :scraped_at, :scraped_at, :source_url, :parser_version
    )
    ON CONFLICT(match_id, map_number) DO UPDATE SET
        mapstatsid      = excluded.mapstatsid,
        map_name        = excluded.map_name,
        team1_rounds    = excluded.team1_rounds,
        team2_rounds    = excluded.team2_rounds,
        team1_ct_rounds = excluded.team1_ct_rounds,
        team1_t_rounds  = excluded.team1_t_rounds,
        team2_ct_rounds = excluded.team2_ct_rounds,
        team2_t_rounds  = excluded.team2_t_rounds,
        updated_at      = excluded.scraped_at,
        source_url      = excluded.source_url,
        parser_version  = excluded.parser_version
"""

UPSERT_PLAYER_STATS = """
    INSERT INTO player_stats (
        match_id, map_number, player_id, player_name, team_id,
        kills, deaths, assists, flash_assists, hs_kills, kd_diff,
        adr, kast, fk_diff, rating_2, rating_3,
        kpr, dpr, impact,
        scraped_at, updated_at, source_url, parser_version
    ) VALUES (
        :match_id, :map_number, :player_id, :player_name, :team_id,
        :kills, :deaths, :assists, :flash_assists, :hs_kills, :kd_diff,
        :adr, :kast, :fk_diff, :rating_2, :rating_3,
        :kpr, :dpr, :impact,
        :scraped_at, :scraped_at, :source_url, :parser_version
    )
    ON CONFLICT(match_id, map_number, player_id) DO UPDATE SET
        player_name    = excluded.player_name,
        team_id        = excluded.team_id,
        kills          = excluded.kills,
        deaths         = excluded.deaths,
        assists        = excluded.assists,
        flash_assists  = excluded.flash_assists,
        hs_kills       = excluded.hs_kills,
        kd_diff        = excluded.kd_diff,
        adr            = excluded.adr,
        kast           = excluded.kast,
        fk_diff        = excluded.fk_diff,
        rating_2       = excluded.rating_2,
        rating_3       = excluded.rating_3,
        kpr            = excluded.kpr,
        dpr            = excluded.dpr,
        impact         = excluded.impact,
        updated_at     = excluded.scraped_at,
        source_url     = excluded.source_url,
        parser_version = excluded.parser_version
"""

UPSERT_ROUND = """
    INSERT INTO round_history (
        match_id, map_number, round_number,
        winner_side, win_type, winner_team_id,
        scraped_at, updated_at, source_url, parser_version
    ) VALUES (
        :match_id, :map_number, :round_number,
        :winner_side, :win_type, :winner_team_id,
        :scraped_at, :scraped_at, :source_url, :parser_version
    )
    ON CONFLICT(match_id, map_number, round_number) DO UPDATE SET
        winner_side    = excluded.winner_side,
        win_type       = excluded.win_type,
        winner_team_id = excluded.winner_team_id,
        updated_at     = excluded.scraped_at,
        source_url     = excluded.source_url,
        parser_version = excluded.parser_version
"""

UPSERT_ECONOMY = """
    INSERT INTO economy (
        match_id, map_number, round_number, team_id,
        equipment_value, buy_type,
        scraped_at, updated_at, source_url, parser_version
    ) VALUES (
        :match_id, :map_number, :round_number, :team_id,
        :equipment_value, :buy_type,
        :scraped_at, :scraped_at, :source_url, :parser_version
    )
    ON CONFLICT(match_id, map_number, round_number, team_id) DO UPDATE SET
        equipment_value = excluded.equipment_value,
        buy_type        = excluded.buy_type,
        updated_at      = excluded.scraped_at,
        source_url      = excluded.source_url,
        parser_version  = excluded.parser_version
"""


# ---------------------------------------------------------------------------
# Repository class
# ---------------------------------------------------------------------------

class MatchRepository:
    """Data access layer for HLTV match data.

    Wraps all database write and read operations.  Receives a raw
    ``sqlite3.Connection`` (not a Database instance) so tests can pass
    any connection, including in-memory databases.

    Write methods use ``with self.conn:`` for automatic commit on
    success / rollback on exception.  Exceptions (IntegrityError,
    OperationalError) are NOT caught -- they propagate to callers.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ------------------------------------------------------------------
    # Single-row UPSERT methods
    # ------------------------------------------------------------------

    def upsert_match(self, data: dict) -> None:
        """Insert or update a match record."""
        with self.conn:
            self.conn.execute(UPSERT_MATCH, data)

    def upsert_map(self, data: dict) -> None:
        """Insert or update a map record."""
        with self.conn:
            self.conn.execute(UPSERT_MAP, data)

    def upsert_player_stats(self, data: dict) -> None:
        """Insert or update a player stats record."""
        with self.conn:
            self.conn.execute(UPSERT_PLAYER_STATS, data)

    def upsert_round(self, data: dict) -> None:
        """Insert or update a round history record."""
        with self.conn:
            self.conn.execute(UPSERT_ROUND, data)

    def upsert_economy(self, data: dict) -> None:
        """Insert or update an economy record."""
        with self.conn:
            self.conn.execute(UPSERT_ECONOMY, data)

    # ------------------------------------------------------------------
    # Batch UPSERT methods (atomic transactions)
    # ------------------------------------------------------------------

    def upsert_match_maps(self, match_data: dict, maps_data: list[dict]) -> None:
        """Atomically upsert a match and all its maps.

        This is what Phase 5 will call after parsing an overview page.
        """
        with self.conn:
            self.conn.execute(UPSERT_MATCH, match_data)
            for map_data in maps_data:
                self.conn.execute(UPSERT_MAP, map_data)

    def upsert_map_player_stats(self, stats_data: list[dict]) -> None:
        """Atomically upsert multiple player stats rows."""
        with self.conn:
            for row in stats_data:
                self.conn.execute(UPSERT_PLAYER_STATS, row)

    def upsert_map_rounds(self, rounds_data: list[dict]) -> None:
        """Atomically upsert multiple round history rows."""
        with self.conn:
            for row in rounds_data:
                self.conn.execute(UPSERT_ROUND, row)

    def upsert_map_economy(self, economy_data: list[dict]) -> None:
        """Atomically upsert multiple economy rows."""
        with self.conn:
            for row in economy_data:
                self.conn.execute(UPSERT_ECONOMY, row)

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def get_match(self, match_id: int) -> dict | None:
        """Return a match as a dict, or None if not found."""
        row = self.conn.execute(
            "SELECT * FROM matches WHERE match_id = ?", (match_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def get_maps(self, match_id: int) -> list[dict]:
        """Return all maps for a match, ordered by map_number."""
        rows = self.conn.execute(
            "SELECT * FROM maps WHERE match_id = ? ORDER BY map_number",
            (match_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_player_stats(self, match_id: int, map_number: int) -> list[dict]:
        """Return player stats for a specific map, ordered by player_id."""
        rows = self.conn.execute(
            "SELECT * FROM player_stats "
            "WHERE match_id = ? AND map_number = ? "
            "ORDER BY player_id",
            (match_id, map_number),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_matches(self) -> int:
        """Return the total number of match records."""
        return self.conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
