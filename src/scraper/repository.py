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
        adr, kast, fk_diff, rating,
        kpr, dpr,
        opening_kills, opening_deaths, multi_kills, clutch_wins,
        traded_deaths, round_swing, mk_rating,
        e_kills, e_deaths, e_hs_kills, e_kd_diff, e_adr, e_kast,
        e_opening_kills, e_opening_deaths, e_fk_diff, e_traded_deaths,
        scraped_at, updated_at, source_url, parser_version
    ) VALUES (
        :match_id, :map_number, :player_id, :player_name, :team_id,
        :kills, :deaths, :assists, :flash_assists, :hs_kills, :kd_diff,
        :adr, :kast, :fk_diff, :rating,
        :kpr, :dpr,
        :opening_kills, :opening_deaths, :multi_kills, :clutch_wins,
        :traded_deaths, :round_swing, :mk_rating,
        :e_kills, :e_deaths, :e_hs_kills, :e_kd_diff, :e_adr, :e_kast,
        :e_opening_kills, :e_opening_deaths, :e_fk_diff, :e_traded_deaths,
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
        rating         = excluded.rating,
        kpr            = excluded.kpr,
        dpr            = excluded.dpr,
        opening_kills  = excluded.opening_kills,
        opening_deaths = excluded.opening_deaths,
        multi_kills    = excluded.multi_kills,
        clutch_wins    = excluded.clutch_wins,
        traded_deaths  = excluded.traded_deaths,
        round_swing    = excluded.round_swing,
        mk_rating      = excluded.mk_rating,
        e_kills        = excluded.e_kills,
        e_deaths       = excluded.e_deaths,
        e_hs_kills     = excluded.e_hs_kills,
        e_kd_diff      = excluded.e_kd_diff,
        e_adr          = excluded.e_adr,
        e_kast         = excluded.e_kast,
        e_opening_kills  = excluded.e_opening_kills,
        e_opening_deaths = excluded.e_opening_deaths,
        e_fk_diff      = excluded.e_fk_diff,
        e_traded_deaths  = excluded.e_traded_deaths,
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

UPSERT_VETO = """
    INSERT INTO vetoes (
        match_id, step_number, team_name, action, map_name,
        scraped_at, updated_at, source_url, parser_version
    ) VALUES (
        :match_id, :step_number, :team_name, :action, :map_name,
        :scraped_at, :scraped_at, :source_url, :parser_version
    )
    ON CONFLICT(match_id, step_number) DO UPDATE SET
        team_name      = excluded.team_name,
        action         = excluded.action,
        map_name       = excluded.map_name,
        updated_at     = excluded.scraped_at,
        source_url     = excluded.source_url,
        parser_version = excluded.parser_version
"""

GET_PENDING_MAP_STATS = """
    SELECT m.match_id, m.map_number, m.mapstatsid
    FROM maps m
    WHERE m.mapstatsid IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM player_stats ps
        WHERE ps.match_id = m.match_id AND ps.map_number = m.map_number
      )
    ORDER BY m.match_id, m.map_number
    LIMIT ?
"""

UPSERT_KILL_MATRIX = """
    INSERT INTO kill_matrix (
        match_id, map_number, matrix_type, player1_id, player2_id,
        player1_kills, player2_kills,
        scraped_at, updated_at, source_url, parser_version
    ) VALUES (
        :match_id, :map_number, :matrix_type, :player1_id, :player2_id,
        :player1_kills, :player2_kills,
        :scraped_at, :scraped_at, :source_url, :parser_version
    )
    ON CONFLICT(match_id, map_number, matrix_type, player1_id, player2_id) DO UPDATE SET
        player1_kills  = excluded.player1_kills,
        player2_kills  = excluded.player2_kills,
        updated_at     = excluded.scraped_at,
        source_url     = excluded.source_url,
        parser_version = excluded.parser_version
"""

GET_PENDING_PERF_ECONOMY = """
    SELECT m.match_id, m.map_number, m.mapstatsid
    FROM maps m
    WHERE m.mapstatsid IS NOT NULL
      AND m.perf_attempts < ?
      AND EXISTS (
        SELECT 1 FROM player_stats ps
        WHERE ps.match_id = m.match_id AND ps.map_number = m.map_number
      )
      AND EXISTS (
        SELECT 1 FROM player_stats ps
        WHERE ps.match_id = m.match_id AND ps.map_number = m.map_number
          AND ps.kpr IS NULL
      )
    ORDER BY m.match_id, m.map_number
    LIMIT ?
"""

INSERT_QUARANTINE = """
    INSERT INTO quarantine (
        entity_type, match_id, map_number,
        raw_data, error_details, quarantined_at, resolved
    ) VALUES (
        :entity_type, :match_id, :map_number,
        :raw_data, :error_details, :quarantined_at, :resolved
    )
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

        Legacy method kept for backward compatibility.
        Prefer ``upsert_match_overview`` for Phase 5+ usage.
        """
        with self.conn:
            self.conn.execute(UPSERT_MATCH, match_data)
            for map_data in maps_data:
                self.conn.execute(UPSERT_MAP, map_data)

    def upsert_match_overview(
        self,
        match_data: dict,
        maps_data: list[dict],
        vetoes_data: list[dict],
    ) -> None:
        """Atomically upsert a match with ALL related overview data.

        Writes the match record, map records, and veto sequence in a
        single transaction.  This is the primary method the Phase 5
        orchestrator calls after parsing a match overview page.
        """
        with self.conn:
            self.conn.execute(UPSERT_MATCH, match_data)
            for map_data in maps_data:
                self.conn.execute(UPSERT_MAP, map_data)
            for veto in vetoes_data:
                self.conn.execute(UPSERT_VETO, veto)

    def upsert_map_stats_complete(
        self, stats_data: list[dict], rounds_data: list[dict]
    ) -> None:
        """Atomically upsert player stats AND round history for a map.

        Writes all ``stats_data`` rows into ``player_stats`` and all
        ``rounds_data`` rows into ``round_history`` inside a single
        transaction.  Either everything is committed or nothing is
        (rollback on any error).
        """
        with self.conn:
            for row in stats_data:
                self.conn.execute(UPSERT_PLAYER_STATS, row)
            for row in rounds_data:
                self.conn.execute(UPSERT_ROUND, row)

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

    def upsert_kill_matrix(self, data: dict) -> None:
        """Insert or update a single kill matrix record."""
        with self.conn:
            self.conn.execute(UPSERT_KILL_MATRIX, data)

    def upsert_perf_economy_complete(
        self,
        perf_stats: list[dict],
        economy_data: list[dict],
        kill_matrix_data: list[dict],
    ) -> None:
        """Atomically upsert performance stats, economy data, and kill matrix.

        Updates existing player_stats rows with performance page fields
        (kpr, dpr, impact, mk_rating), inserts economy rows, and inserts
        kill matrix rows -- all in a single transaction.
        """
        with self.conn:
            for row in perf_stats:
                self.conn.execute(UPSERT_PLAYER_STATS, row)
            for row in economy_data:
                self.conn.execute(UPSERT_ECONOMY, row)
            for row in kill_matrix_data:
                self.conn.execute(UPSERT_KILL_MATRIX, row)

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def get_pending_map_stats(self, limit: int = 10) -> list[dict]:
        """Return maps that have a mapstatsid but no player_stats rows yet.

        These are maps whose map-stats page has not been scraped, or
        whose scrape failed to produce any player stats.  Results are
        ordered by (match_id, map_number) for deterministic processing.
        """
        rows = self.conn.execute(GET_PENDING_MAP_STATS, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_pending_perf_economy(
        self, limit: int = 10, max_attempts: int = 3,
    ) -> list[dict]:
        """Return maps that have player_stats but no performance data yet.

        Finds maps where Phase 6 has run (player_stats rows exist) but
        Phase 7 hasn't (kpr is still NULL on at least one player row).
        Maps that have already been attempted ``max_attempts`` times are
        skipped to prevent infinite retry loops on persistent parse failures.
        Results are ordered by (match_id, map_number).
        """
        rows = self.conn.execute(
            GET_PENDING_PERF_ECONOMY, (max_attempts, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def increment_perf_attempts(self, match_id: int, map_number: int) -> None:
        """Increment the perf_attempts counter for a map after a parse failure."""
        with self.conn:
            self.conn.execute(
                "UPDATE maps SET perf_attempts = perf_attempts + 1 "
                "WHERE match_id = ? AND map_number = ?",
                (match_id, map_number),
            )

    def get_valid_round_numbers(self, match_id: int, map_number: int) -> set[int]:
        """Return set of round numbers that exist in round_history for this map."""
        rows = self.conn.execute(
            "SELECT round_number FROM round_history "
            "WHERE match_id = ? AND map_number = ?",
            (match_id, map_number),
        ).fetchall()
        return {r[0] for r in rows}

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

    def get_vetoes(self, match_id: int) -> list[dict]:
        """Return all vetoes for a match, ordered by step_number."""
        rows = self.conn.execute(
            "SELECT * FROM vetoes WHERE match_id = ? ORDER BY step_number",
            (match_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count_matches(self) -> int:
        """Return the total number of match records."""
        return self.conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]

    # ------------------------------------------------------------------
    # Quarantine methods
    # ------------------------------------------------------------------

    def insert_quarantine(self, data: dict) -> None:
        """Insert a quarantine record for a failed validation.

        Args:
            data: Dict with keys: entity_type, match_id, map_number,
                  raw_data, error_details, quarantined_at, resolved.
        """
        with self.conn:
            self.conn.execute(INSERT_QUARANTINE, data)

    def get_quarantine_count(self) -> int:
        """Return the total number of quarantine records."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM quarantine"
        ).fetchone()[0]
