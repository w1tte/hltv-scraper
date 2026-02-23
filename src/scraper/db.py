"""SQLite database connection manager with migration support.

Manages the connection lifecycle, applies PRAGMAs (WAL, foreign keys,
busy_timeout) on every connect, and runs pending SQL migrations from
the migrations/ directory using PRAGMA user_version for tracking.
"""

import sqlite3
from pathlib import Path


class Database:
    """SQLite connection manager with migration support.

    Usage::

        db = Database("data/hltv.db")
        db.initialize()  # connect + apply migrations
        # ... use db.conn ...
        db.close()

    Or as a context manager::

        with Database("data/hltv.db") as db:
            db.apply_migrations()
            # ... use db.conn ...
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        """Open connection and configure PRAGMAs.

        Sets WAL journal mode, enables foreign keys, and configures
        a 5-second busy timeout for lock contention.
        """
        self._conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        # PRAGMAs must be set per-connection
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        # NORMAL is safe with WAL and avoids the full fsync on every commit
        self._conn.execute("PRAGMA synchronous = NORMAL")
        # 32 MB page cache — reduces I/O for repeated UPSERT lookups
        self._conn.execute("PRAGMA cache_size = -32000")
        # Store temp tables/indices in memory
        self._conn.execute("PRAGMA temp_store = MEMORY")
        # 30s busy timeout — enough for 8 workers to queue up without errors
        self._conn.execute("PRAGMA busy_timeout = 30000")
        return self._conn

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the active connection or raise if not connected."""
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_schema_version(self) -> int:
        """Return the current schema version (PRAGMA user_version)."""
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def apply_migrations(self, migrations_dir: Path | None = None) -> int:
        """Apply pending SQL migration files.

        Migration files are named ``NNN_description.sql`` where NNN is
        the version number.  Files with version <= current user_version
        are skipped.  After each file is applied, user_version is set
        to the file's version number.

        Args:
            migrations_dir: Directory containing .sql files.
                Defaults to ``<project_root>/migrations``.

        Returns:
            Number of migrations applied.
        """
        if migrations_dir is None:
            migrations_dir = Path(__file__).resolve().parent.parent.parent / "migrations"
        else:
            migrations_dir = Path(migrations_dir)

        current = self.get_schema_version()
        migration_files = sorted(migrations_dir.glob("*.sql"))
        applied = 0

        for migration_file in migration_files:
            # Extract version number from filename: 001_initial.sql -> 1
            version = int(migration_file.name.split("_")[0])
            if version <= current:
                continue

            sql = migration_file.read_text(encoding="utf-8")
            self.conn.executescript(sql)
            self.conn.execute(f"PRAGMA user_version = {version}")
            applied += 1

        return applied

    def initialize(self) -> sqlite3.Connection:
        """Connect and apply all pending migrations.

        This is the standard entry point for application code.

        Returns:
            The active sqlite3.Connection.
        """
        self.connect()
        self.apply_migrations()
        return self.conn
