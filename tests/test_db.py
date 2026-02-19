"""Unit tests for the Database connection manager and migration system."""

import sqlite3

import pytest

from scraper.db import Database


class TestDatabaseCreation:
    """Tests for database file creation and basic lifecycle."""

    def test_database_creates_file(self, tmp_path):
        """Database.initialize() creates the .db file on disk."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.initialize()
        assert db_path.exists()
        db.close()

    def test_database_creates_parent_directories(self, tmp_path):
        """Database creates missing parent directories."""
        db_path = tmp_path / "nested" / "dir" / "test.db"
        db = Database(db_path)
        db.initialize()
        assert db_path.exists()
        db.close()


class TestDatabasePragmas:
    """Tests for PRAGMA configuration on connect."""

    def test_database_wal_mode(self, tmp_path):
        """After connect, journal_mode is WAL."""
        db = Database(tmp_path / "test.db")
        db.connect()
        mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        db.close()

    def test_database_foreign_keys_enabled(self, tmp_path):
        """After connect, foreign_keys PRAGMA is ON (1)."""
        db = Database(tmp_path / "test.db")
        db.connect()
        fk = db.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
        db.close()

    def test_database_busy_timeout(self, tmp_path):
        """After connect, busy_timeout is set to 5000ms."""
        db = Database(tmp_path / "test.db")
        db.connect()
        timeout = db.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert timeout == 5000
        db.close()


class TestDatabaseMigrations:
    """Tests for schema version tracking and migration application."""

    def test_database_schema_version(self, tmp_path):
        """After initialize(), get_schema_version() returns latest migration version."""
        db = Database(tmp_path / "test.db")
        db.initialize()
        assert db.get_schema_version() == 8
        db.close()

    def test_database_connect_without_initialize(self, tmp_path):
        """connect() without apply_migrations() gives schema version 0."""
        db = Database(tmp_path / "test.db")
        db.connect()
        assert db.get_schema_version() == 0
        tables = [
            r[0]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert tables == []
        db.close()

    def test_database_migration_idempotent(self, tmp_path):
        """Running apply_migrations() twice returns 0 on second call."""
        db = Database(tmp_path / "test.db")
        db.connect()
        first = db.apply_migrations()
        assert first == 8  # 001-007 + 008_perf_attempts
        second = db.apply_migrations()
        assert second == 0
        db.close()

    def test_database_all_tables_created(self, tmp_path):
        """After initialize(), all 5 tables exist."""
        db = Database(tmp_path / "test.db")
        db.initialize()
        tables = {
            r[0]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {"matches", "maps", "player_stats", "round_history", "economy"}
        assert tables >= expected
        db.close()

    def test_database_all_indexes_created(self, tmp_path):
        """After initialize(), all 12 custom indexes exist (6 from v1 + 2 from v2 + 1 from v4 + 3 from v5; v3 match_players indexes dropped in v6; v7 recreates player_stats indexes)."""
        db = Database(tmp_path / "test.db")
        db.initialize()
        indexes = {
            r[0]
            for r in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            ).fetchall()
        }
        expected = {
            "idx_matches_date",
            "idx_matches_event",
            "idx_matches_teams",
            "idx_maps_mapstatsid",
            "idx_player_stats_player",
            "idx_player_stats_team",
            "idx_scrape_queue_status",
            "idx_scrape_queue_offset",
            "idx_kill_matrix_players",
            "idx_quarantine_match",
            "idx_quarantine_type",
            "idx_quarantine_resolved",
        }
        assert indexes == expected
        db.close()


class TestDatabaseContextManager:
    """Tests for the context manager protocol."""

    def test_database_context_manager(self, tmp_path):
        """with Database(path) as db: connects and closes properly."""
        db_path = tmp_path / "test.db"
        with Database(db_path) as db:
            assert db.conn is not None
            db.apply_migrations()
            assert db.get_schema_version() == 8
        # After exiting context, connection should be closed
        assert db._conn is None

    def test_database_conn_property_raises_without_connect(self, tmp_path):
        """Accessing .conn before connect() raises RuntimeError."""
        db = Database(tmp_path / "test.db")
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.conn


class TestDatabaseForeignKeys:
    """Tests for foreign key constraint enforcement."""

    def test_database_foreign_key_enforcement(self, tmp_path):
        """Insert player_stats referencing non-existent match raises IntegrityError."""
        db = Database(tmp_path / "test.db")
        db.initialize()
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                """
                INSERT INTO player_stats (
                    match_id, map_number, player_id,
                    scraped_at, updated_at
                ) VALUES (99999, 1, 1, '2026-01-01', '2026-01-01')
                """
            )
        db.close()
