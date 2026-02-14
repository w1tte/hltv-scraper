# Phase 2: Storage Foundation - Research

**Researched:** 2026-02-14
**Domain:** SQLite schema design, raw HTML archival, UPSERT semantics, migration patterns
**Confidence:** HIGH

## Summary

This research covers the storage foundation for the HLTV scraper: a SQLite database for structured match data and a filesystem layer for raw HTML archival. The entire phase uses Python standard library only -- `sqlite3` for the database, `gzip` for compression, and `pathlib` for filesystem operations. No external dependencies are needed.

The SQLite version bundled with Python 3.12 on this machine is 3.49.1, which supports all modern features: UPSERT via `ON CONFLICT DO UPDATE` (3.24+), `RETURNING` clause (3.35+), STRICT tables (3.37+), and WAL journal mode. The database schema uses HLTV's natural keys (match_id, mapstatsid, player_id) as primary/unique keys, enabling clean UPSERT semantics where re-scraping a match silently overwrites the previous data.

The raw HTML storage uses a match-centric directory structure (`data/raw/matches/{match_id}/`) with gzip compression. HTML pages of 50-200KB compress to approximately 5-20KB, making long-term storage of all raw HTML feasible (estimated 1-2GB for the entire CS2 era).

**Primary recommendation:** Use stdlib `sqlite3` with raw SQL (no ORM), `PRAGMA user_version` for migration tracking, WAL journal mode for performance, and `PRAGMA foreign_keys = ON` for referential integrity. Keep the database access layer as a thin Python class wrapping connection management and parameterized queries.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlite3` | stdlib (SQLite 3.49.1) | Relational database | Zero dependencies, bundled with Python, supports all needed features (UPSERT, STRICT, WAL, foreign keys). Single-file database at `data/hltv.db`. |
| `gzip` | stdlib | HTML compression | Compresses HTML from ~150KB to ~15KB. Simple `gzip.compress()`/`gzip.decompress()` round-trip. |
| `pathlib` | stdlib | Filesystem operations | Type-safe path construction, `mkdir(parents=True, exist_ok=True)`, cross-platform. |
| `datetime` | stdlib | Timestamps | ISO 8601 timestamps for `scraped_at`, `updated_at` provenance fields. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` | stdlib | Metadata storage | Store structured metadata (e.g., page type enum, fetch context) alongside HTML files if needed. |
| `hashlib` | stdlib | Content hashing | Optional integrity check -- hash raw HTML to detect changes on re-scrape. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `sqlite3` | Peewee ORM | Peewee adds schema management and query building, but this project has <10 tables with straightforward queries. Raw SQL is more transparent, has zero dependencies, and is consistent with the project's stdlib-first philosophy (dataclass config, no pydantic yet). |
| Raw `sqlite3` | SQLAlchemy | Massive overkill for a single-user SQLite scraper. 100K+ lines of code for features this project does not need. |
| `PRAGMA user_version` | Alembic/yoyo-migrations | External migration tools add dependencies and complexity. `user_version` is built into SQLite, covers sequential migrations perfectly, and the project has only a handful of migrations. |
| Gzip files on disk | SQLite BLOB storage | Storing HTML as BLOBs in SQLite would simplify the storage layer to one file, but makes HTML inspection harder (can't just open files), bloats the DB file, and mixes mutable structured data with immutable archival data. Filesystem storage is the right choice for raw HTML. |

**Installation:**

```bash
# No installation needed -- all stdlib
# Verify SQLite version:
python -c "import sqlite3; print(sqlite3.sqlite_version)"
# Should print >= 3.24.0 for UPSERT support
```

## Architecture Patterns

### Recommended Project Structure

```
src/
  scraper/
    __init__.py
    config.py            # Existing -- add data_dir, db_path settings
    exceptions.py        # Existing
    http_client.py       # Existing
    rate_limiter.py      # Existing
    db.py                # NEW: Database connection, migrations, PRAGMA setup
    models.py            # NEW: Table creation SQL, schema constants
    storage.py           # NEW: Raw HTML save/load (filesystem layer)
    repository.py        # NEW: CRUD operations, UPSERT logic for each table
data/
  hltv.db               # SQLite database (gitignored)
  raw/                   # Raw HTML archive (gitignored)
    matches/
      {match_id}/
        overview.html.gz
        map-{mapstatsid}-stats.html.gz
        map-{mapstatsid}-performance.html.gz
        map-{mapstatsid}-economy.html.gz
migrations/
  001_initial_schema.sql # First migration
  002_*.sql              # Future migrations as needed
tests/
  test_db.py             # Database layer tests
  test_storage.py        # HTML storage tests
  test_repository.py     # CRUD/UPSERT tests
```

### Pattern 1: Database Connection Manager

**What:** A class that manages the SQLite connection lifecycle, applies PRAGMAs on connect, and runs pending migrations.

**When to use:** Always. Every database interaction goes through this class.

**Example:**

```python
import sqlite3
from pathlib import Path

class Database:
    """SQLite connection manager with migration support."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        """Open connection and configure PRAGMAs."""
        self._conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        # PRAGMAs must be set per-connection
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        return self._conn

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, *args) -> None:
        self.close()
```

### Pattern 2: UPSERT with ON CONFLICT DO UPDATE

**What:** Insert-or-update rows using SQLite's `ON CONFLICT` clause with the `excluded.` pseudo-table to reference incoming values.

**When to use:** Every write operation. Re-scraping a match must silently overwrite existing data.

**Example:**

```python
# Source: https://sqlite.org/lang_upsert.html
def upsert_match(conn: sqlite3.Connection, match: dict) -> None:
    conn.execute("""
        INSERT INTO matches (
            match_id, date, event_id, event_name,
            team1_id, team1_name, team2_id, team2_name,
            team1_score, team2_score, best_of, is_lan,
            match_url, scraped_at, updated_at
        ) VALUES (
            :match_id, :date, :event_id, :event_name,
            :team1_id, :team1_name, :team2_id, :team2_name,
            :team1_score, :team2_score, :best_of, :is_lan,
            :match_url, :scraped_at, :scraped_at
        )
        ON CONFLICT(match_id) DO UPDATE SET
            date = excluded.date,
            event_id = excluded.event_id,
            event_name = excluded.event_name,
            team1_id = excluded.team1_id,
            team1_name = excluded.team1_name,
            team2_id = excluded.team2_id,
            team2_name = excluded.team2_name,
            team1_score = excluded.team1_score,
            team2_score = excluded.team2_score,
            best_of = excluded.best_of,
            is_lan = excluded.is_lan,
            match_url = excluded.match_url,
            updated_at = excluded.scraped_at
    """, match)
    conn.commit()
```

**Key rules for UPSERT:**
- The conflict target (column in `ON CONFLICT(...)`) must have a UNIQUE or PRIMARY KEY constraint
- `excluded.column_name` refers to the value that was attempted to be inserted
- Unqualified `column_name` refers to the existing row's current value
- UPSERT only triggers on uniqueness constraint violations, not CHECK/NOT NULL/FK violations

### Pattern 3: Migration via PRAGMA user_version

**What:** Track schema version in SQLite's built-in `user_version` PRAGMA. Apply numbered SQL migration scripts sequentially.

**When to use:** On every database connection, check version and apply pending migrations.

**Example:**

```python
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"

def get_schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]

def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply all pending migrations. Returns number applied."""
    current = get_schema_version(conn)
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    applied = 0

    for migration_file in migration_files:
        # Extract version number from filename: 001_initial.sql -> 1
        version = int(migration_file.name.split("_")[0])
        if version <= current:
            continue

        sql = migration_file.read_text(encoding="utf-8")
        try:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {version}")
            applied += 1
        except Exception:
            # executescript auto-commits on success, but on failure
            # the partial changes may have been committed too.
            # Log the error and re-raise.
            raise

    return applied
```

**Migration file format:**

```sql
-- migrations/001_initial_schema.sql
-- Phase 2: Initial database schema

CREATE TABLE IF NOT EXISTS matches (
    match_id      INTEGER PRIMARY KEY,
    -- ... columns ...
);

-- Each migration file is self-contained.
-- PRAGMA user_version is set by the migration runner, not in the file.
```

### Pattern 4: Raw HTML Storage Layer

**What:** Save and load gzipped HTML files organized by match ID and page type.

**When to use:** Before any parsing occurs. The fetch step saves HTML, the parse step reads it back.

**Example:**

```python
import gzip
from pathlib import Path
from datetime import datetime, timezone

class HtmlStorage:
    """Filesystem storage for raw HTML pages."""

    # Page type -> filename template
    PAGE_TYPES = {
        "overview": "overview.html.gz",
        "map_stats": "map-{mapstatsid}-stats.html.gz",
        "map_performance": "map-{mapstatsid}-performance.html.gz",
        "map_economy": "map-{mapstatsid}-economy.html.gz",
    }

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def save(
        self,
        html: str,
        match_id: int,
        page_type: str,
        mapstatsid: int | None = None,
    ) -> Path:
        """Save HTML to disk, return the file path."""
        file_path = self._build_path(match_id, page_type, mapstatsid)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(gzip.compress(html.encode("utf-8")))
        return file_path

    def load(
        self,
        match_id: int,
        page_type: str,
        mapstatsid: int | None = None,
    ) -> str:
        """Load HTML from disk."""
        file_path = self._build_path(match_id, page_type, mapstatsid)
        return gzip.decompress(file_path.read_bytes()).decode("utf-8")

    def exists(
        self,
        match_id: int,
        page_type: str,
        mapstatsid: int | None = None,
    ) -> bool:
        return self._build_path(match_id, page_type, mapstatsid).exists()

    def _build_path(
        self,
        match_id: int,
        page_type: str,
        mapstatsid: int | None,
    ) -> Path:
        template = self.PAGE_TYPES[page_type]
        filename = template.format(mapstatsid=mapstatsid)
        return self.base_dir / "matches" / str(match_id) / filename
```

### Pattern 5: Connection as Context Manager for Transactions

**What:** Use `with conn:` to automatically commit on success or rollback on exception.

**When to use:** Every write operation that should be atomic.

**Example:**

```python
# Source: https://docs.python.org/3.12/library/sqlite3.html

# Automatic commit/rollback
with conn:
    conn.execute("INSERT INTO matches (...) VALUES (...)", params)
    conn.execute("INSERT INTO maps (...) VALUES (...)", map_params)
    # Both inserts commit together, or both rollback on error

# For read-only operations, no context manager needed
rows = conn.execute("SELECT * FROM matches WHERE match_id = ?", (123,)).fetchall()
```

**Important:** The `with conn:` context manager handles transactions (commit/rollback) but does NOT close the connection. The connection must be closed separately.

### Anti-Patterns to Avoid

- **String formatting in SQL queries:** Never use f-strings or `.format()` to build SQL. Always use parameterized queries (`?` placeholders or `:name` named parameters). This prevents SQL injection and handles type conversion correctly.
- **Forgetting PRAGMA foreign_keys = ON:** Foreign keys are disabled by default in SQLite. They must be enabled on every new connection. If you forget, foreign key constraints silently do nothing.
- **Using INSERT OR REPLACE instead of ON CONFLICT DO UPDATE:** `INSERT OR REPLACE` deletes the existing row and inserts a new one, which resets any columns not in the INSERT and triggers DELETE + INSERT triggers. `ON CONFLICT DO UPDATE` modifies the existing row in place, preserving columns not listed in the SET clause.
- **Committing inside loops:** Do not call `conn.commit()` after every single row insert. Batch writes within a single transaction (one `with conn:` block) for orders-of-magnitude better performance.
- **Storing timestamps as Unix integers:** Use ISO 8601 text (`2026-02-14T12:30:00Z`) for human readability in ad-hoc SQL queries. SQLite's date/time functions work with ISO 8601 strings natively.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema version tracking | Custom version table with INSERT/UPDATE | `PRAGMA user_version` | Built into SQLite. Atomic, no table to manage, survives schema changes. Always returns an integer version. |
| Connection pooling | Thread-safe connection wrapper | Single connection per process | This is a single-threaded scraper. SQLite's best performance is one writer. Connection pooling adds complexity with no benefit. |
| HTML compression | Custom compression scheme | `gzip.compress()` / `gzip.decompress()` | Stdlib, well-tested, ~90% compression ratio on HTML. The `.gz` extension is universally recognized. |
| File path construction | String concatenation for paths | `pathlib.Path` | Cross-platform, safe against path injection, provides `mkdir(parents=True)`, `.exists()`, `.read_bytes()`, `.write_bytes()`. |
| UPSERT logic | SELECT-then-INSERT-or-UPDATE pattern | `INSERT ... ON CONFLICT DO UPDATE` | The two-step pattern has a race condition and is slower. SQLite's UPSERT is atomic and faster (single statement). |
| Retry on SQLITE_BUSY | Manual retry loop | `PRAGMA busy_timeout = 5000` | SQLite retries internally for up to N milliseconds when the database is locked, before raising OperationalError. |

**Key insight:** This entire phase can be built with zero external dependencies. Python's stdlib provides everything needed for SQLite, gzip, and filesystem operations.

## Common Pitfalls

### Pitfall 1: Foreign Keys Silently Disabled

**What goes wrong:** Developer creates tables with `REFERENCES` constraints, inserts rows with invalid foreign keys, and no error is raised. Data integrity is silently violated.

**Why it happens:** SQLite has foreign keys disabled by default for backward compatibility. The `PRAGMA foreign_keys = ON` statement must be executed on every new connection.

**How to avoid:** Set `PRAGMA foreign_keys = ON` in the database connection setup method, immediately after connecting. Verify with `PRAGMA foreign_keys` (returns 1 if enabled). Add a test that verifies foreign key enforcement.

**Warning signs:** Orphaned rows in child tables (e.g., `player_stats` rows referencing a `match_id` that does not exist in `matches`).

### Pitfall 2: executescript() Auto-Commits

**What goes wrong:** Developer wraps `executescript()` in a `with conn:` block expecting transactional behavior. But `executescript()` issues an implicit COMMIT before running, so previous uncommitted work is committed and the script runs outside the context manager's transaction control.

**Why it happens:** `executescript()` is designed for running multiple SQL statements including DDL (CREATE TABLE). It commits any pending transaction first, then runs statements with implicit commits.

**How to avoid:** Use `executescript()` only for DDL operations (migrations) where auto-commit is acceptable. For DML operations (INSERT/UPDATE/DELETE), use `execute()` or `executemany()` within a `with conn:` transaction block.

**Warning signs:** Partial migration application -- some tables created, others not, with no way to rollback.

### Pitfall 3: INSERT OR REPLACE Deletes Then Re-inserts

**What goes wrong:** Developer uses `INSERT OR REPLACE` expecting it to update existing rows. Instead, it deletes the existing row and inserts a new one. This resets any columns with DEFAULT values, fires DELETE triggers, and changes the rowid.

**Why it happens:** `INSERT OR REPLACE` is syntactic sugar for "delete conflicting row, then insert." This is not the same as UPDATE.

**How to avoid:** Use `INSERT ... ON CONFLICT(key) DO UPDATE SET ...` (true UPSERT). This modifies the existing row in place without deleting it. Columns not listed in the SET clause retain their original values.

**Warning signs:** Timestamps reset unexpectedly, auto-increment IDs change, trigger-based audit logs show DELETE+INSERT instead of UPDATE.

### Pitfall 4: Not Using WAL Mode

**What goes wrong:** Database operations are slower than expected, and concurrent reads during writes fail with "database is locked" errors.

**Why it happens:** SQLite defaults to DELETE journal mode, which locks the entire database for writes. WAL (Write-Ahead Logging) mode allows concurrent reads during writes and is significantly faster for most workloads.

**How to avoid:** Set `PRAGMA journal_mode = WAL` on the first connection. WAL mode is persistent (survives connection close/reopen), so it only needs to be set once, but setting it on every connection is harmless and defensive.

**Warning signs:** Slow write performance, "database is locked" errors during read operations.

### Pitfall 5: Gzip Encoding Issues

**What goes wrong:** HTML saved with `gzip.compress(html)` fails because `html` is a string, not bytes. Or HTML loaded with `gzip.decompress()` returns bytes that are compared against strings.

**Why it happens:** `gzip.compress()` requires `bytes`, but nodriver returns HTML as `str`. The encode/decode step is easy to forget.

**How to avoid:** Always encode before compressing and decode after decompressing:
- Save: `gzip.compress(html.encode("utf-8"))`
- Load: `gzip.decompress(data).decode("utf-8")`

**Warning signs:** `TypeError: memoryview: a bytes-like object is required, not 'str'`

## Code Examples

### Complete Database Schema (Migration 001)

```sql
-- migrations/001_initial_schema.sql
-- Phase 2: Storage Foundation - Initial schema
--
-- Tables: matches, maps, player_stats, round_history, economy
-- All tables support UPSERT via ON CONFLICT on their unique keys.
-- Provenance columns (scraped_at, updated_at, source_url) track data lineage.

CREATE TABLE IF NOT EXISTS matches (
    match_id      INTEGER PRIMARY KEY,  -- HLTV match ID (from URL)
    date          TEXT,                  -- ISO 8601 match date
    event_id      INTEGER,              -- HLTV event ID
    event_name    TEXT,                  -- Event/tournament name
    team1_id      INTEGER,              -- HLTV team ID
    team1_name    TEXT,                  -- Team name at time of match
    team2_id      INTEGER,
    team2_name    TEXT,
    team1_score   INTEGER,              -- Maps won by team 1
    team2_score   INTEGER,              -- Maps won by team 2
    best_of       INTEGER,              -- 1, 3, or 5
    is_lan        INTEGER,              -- 0=online, 1=LAN
    match_url     TEXT,                 -- Full HLTV URL
    -- Provenance
    scraped_at    TEXT NOT NULL,         -- When data was fetched
    updated_at    TEXT NOT NULL,         -- When data was last written
    source_url    TEXT,                  -- URL this data was parsed from
    parser_version TEXT                  -- Version of parser that produced this
);

CREATE TABLE IF NOT EXISTS maps (
    match_id        INTEGER NOT NULL REFERENCES matches(match_id),
    map_number      INTEGER NOT NULL,     -- 1-based position in series
    mapstatsid      INTEGER,              -- HLTV mapstatsid (from stats URL)
    map_name        TEXT,                 -- "Mirage", "Inferno", etc.
    -- Scores
    team1_rounds    INTEGER,              -- Total rounds won by team 1
    team2_rounds    INTEGER,
    team1_ct_rounds INTEGER,              -- Rounds won on CT side
    team1_t_rounds  INTEGER,              -- Rounds won on T side
    team2_ct_rounds INTEGER,
    team2_t_rounds  INTEGER,
    -- Provenance
    scraped_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    source_url      TEXT,
    parser_version  TEXT,
    --
    PRIMARY KEY (match_id, map_number)
);

CREATE TABLE IF NOT EXISTS player_stats (
    match_id      INTEGER NOT NULL,
    map_number    INTEGER NOT NULL,
    player_id     INTEGER NOT NULL,       -- HLTV player ID
    player_name   TEXT,                   -- Name at time of match
    team_id       INTEGER,                -- Which team this player was on
    -- Core stats
    kills         INTEGER,
    deaths        INTEGER,
    assists       INTEGER,
    flash_assists INTEGER,
    hs_kills      INTEGER,                -- Headshot kills
    kd_diff       INTEGER,                -- Kill-death difference
    adr           REAL,                   -- Average damage per round
    kast          REAL,                   -- KAST percentage (0-100)
    fk_diff       INTEGER,                -- First kills difference
    -- Rating (nullable -- old matches may lack Rating 3.0)
    rating_2      REAL,                   -- HLTV Rating 2.0/2.1
    rating_3      REAL,                   -- HLTV Rating 3.0 (Aug 2025+)
    -- Performance page stats (populated in Phase 7)
    kpr           REAL,                   -- Kills per round
    dpr           REAL,                   -- Deaths per round
    impact        REAL,                   -- Impact rating
    -- Provenance
    scraped_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    source_url    TEXT,
    parser_version TEXT,
    --
    PRIMARY KEY (match_id, map_number, player_id),
    FOREIGN KEY (match_id, map_number) REFERENCES maps(match_id, map_number)
);

CREATE TABLE IF NOT EXISTS round_history (
    match_id      INTEGER NOT NULL,
    map_number    INTEGER NOT NULL,
    round_number  INTEGER NOT NULL,       -- 1-based round number
    winner_side   TEXT,                   -- "CT" or "T"
    win_type      TEXT,                   -- "bomb_planted", "elimination", "defuse", "time"
    winner_team_id INTEGER,               -- HLTV team ID of round winner
    -- Provenance
    scraped_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    source_url    TEXT,
    parser_version TEXT,
    --
    PRIMARY KEY (match_id, map_number, round_number),
    FOREIGN KEY (match_id, map_number) REFERENCES maps(match_id, map_number)
);

CREATE TABLE IF NOT EXISTS economy (
    match_id      INTEGER NOT NULL,
    map_number    INTEGER NOT NULL,
    round_number  INTEGER NOT NULL,
    team_id       INTEGER NOT NULL,       -- HLTV team ID
    equipment_value INTEGER,              -- Total team equipment value
    buy_type      TEXT,                   -- "eco", "force", "full", "pistol"
    -- Provenance
    scraped_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    source_url    TEXT,
    parser_version TEXT,
    --
    PRIMARY KEY (match_id, map_number, round_number, team_id),
    FOREIGN KEY (match_id, map_number, round_number)
        REFERENCES round_history(match_id, map_number, round_number)
);

-- Indexes for common query patterns (ad-hoc SQL exploration)
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_event ON matches(event_id);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(team1_id, team2_id);
CREATE INDEX IF NOT EXISTS idx_maps_mapstatsid ON maps(mapstatsid);
CREATE INDEX IF NOT EXISTS idx_player_stats_player ON player_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_team ON player_stats(team_id);
```

### UPSERT for Match Data

```python
# Source: Verified against https://sqlite.org/lang_upsert.html

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
        date          = excluded.date,
        event_id      = excluded.event_id,
        event_name    = excluded.event_name,
        team1_id      = excluded.team1_id,
        team1_name    = excluded.team1_name,
        team2_id      = excluded.team2_id,
        team2_name    = excluded.team2_name,
        team1_score   = excluded.team1_score,
        team2_score   = excluded.team2_score,
        best_of       = excluded.best_of,
        is_lan        = excluded.is_lan,
        match_url     = excluded.match_url,
        updated_at    = excluded.scraped_at,
        source_url    = excluded.source_url,
        parser_version = excluded.parser_version
"""

def upsert_match(conn, match_data: dict) -> None:
    """Insert or update a match record."""
    with conn:
        conn.execute(UPSERT_MATCH, match_data)
```

### UPSERT for Child Tables (Composite Keys)

```python
UPSERT_PLAYER_STATS = """
    INSERT INTO player_stats (
        match_id, map_number, player_id, player_name, team_id,
        kills, deaths, assists, flash_assists, hs_kills, kd_diff,
        adr, kast, fk_diff, rating_2, rating_3,
        scraped_at, updated_at, source_url, parser_version
    ) VALUES (
        :match_id, :map_number, :player_id, :player_name, :team_id,
        :kills, :deaths, :assists, :flash_assists, :hs_kills, :kd_diff,
        :adr, :kast, :fk_diff, :rating_2, :rating_3,
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
        updated_at     = excluded.scraped_at,
        source_url     = excluded.source_url,
        parser_version = excluded.parser_version
"""
```

### Database Initialization with Migration

```python
import sqlite3
from pathlib import Path

def init_database(db_path: str | Path, migrations_dir: str | Path) -> sqlite3.Connection:
    """Create/open database, apply PRAGMAs and pending migrations."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # PRAGMAs -- must be set per-connection
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")

    # Apply pending migrations
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    migrations_dir = Path(migrations_dir)

    for migration_file in sorted(migrations_dir.glob("*.sql")):
        version = int(migration_file.name.split("_")[0])
        if version <= current_version:
            continue
        sql = migration_file.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(f"PRAGMA user_version = {version}")

    return conn
```

### Gzip HTML Storage Round-Trip

```python
import gzip
from pathlib import Path

def save_html(html: str, file_path: Path) -> None:
    """Save HTML string as gzipped file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(gzip.compress(html.encode("utf-8")))

def load_html(file_path: Path) -> str:
    """Load HTML string from gzipped file."""
    return gzip.decompress(file_path.read_bytes()).decode("utf-8")

# Usage:
# path = Path("data/raw/matches/2376513/overview.html.gz")
# save_html(html_string, path)
# html = load_html(path)
```

## Schema Design Decisions

### Why No Separate Team/Player/Event Lookup Tables

The CONTEXT.md gives Claude discretion on whether to use first-class entity tables. The recommendation is to **NOT** create separate `teams`, `players`, or `events` lookup tables in Phase 2. Reasons:

1. **HLTV IDs are stable.** Teams and players have permanent numeric IDs. The `team_id` and `player_id` columns in the data tables are sufficient for joins and grouping.
2. **Display names change.** Team names change (roster moves, org rebrands). Storing the name at-time-of-match in each record is the correct historical representation.
3. **No data source yet.** Phase 2 builds storage before any parsing exists. We do not yet know exactly which entity attributes are available. Creating lookup tables now means guessing at columns.
4. **Easy to add later.** A future migration can create lookup tables and populate them from existing data: `INSERT INTO teams (team_id, name) SELECT DISTINCT team1_id, team1_name FROM matches`.

The schema stores `team_id` + `team_name` and `player_id` + `player_name` inline in every record. This is intentional denormalization that preserves historical accuracy and avoids premature abstraction.

### Why Composite Primary Keys Instead of AUTOINCREMENT

Tables like `maps`, `player_stats`, `round_history`, and `economy` use composite primary keys (e.g., `PRIMARY KEY (match_id, map_number, player_id)`) instead of a surrogate `id INTEGER PRIMARY KEY AUTOINCREMENT`. Reasons:

1. **Natural keys exist.** The combination of match_id + map_number + player_id uniquely identifies a player's stats on a specific map. Using these as the primary key enforces uniqueness at the database level.
2. **UPSERT requires the conflict target.** `ON CONFLICT(match_id, map_number, player_id)` works directly with the composite PK. A surrogate key would require a separate UNIQUE constraint.
3. **No wasted storage.** AUTOINCREMENT IDs consume space and provide no semantic value when natural keys exist.

### Why PRAGMA foreign_keys = ON

Foreign keys are off by default in SQLite. Enabling them ensures:
- Cannot insert a `player_stats` row for a match that does not exist in `matches`
- Cannot insert a `round_history` row for a map that does not exist in `maps`
- Deleting a match cascades correctly (if CASCADE is configured)

This catches data integrity issues immediately rather than discovering orphaned rows during analysis.

### Why WAL Mode

WAL (Write-Ahead Logging) provides:
- Concurrent reads during writes (reads do not block writes, writes do not block reads)
- Significantly faster writes (changes written once to WAL file, vs twice in default rollback journal)
- The scraper is single-writer, so WAL's single-writer limitation is not a concern
- WAL mode is persistent -- it survives connection close/reopen

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT DO UPDATE` | SQLite 3.24 (2018) | True UPSERT that modifies in place instead of delete+insert. Preserves rowid, does not fire DELETE triggers. |
| `isolation_level` parameter | `autocommit` parameter | Python 3.12 (2023) | PEP 249-compliant transaction control. `autocommit=False` recommended for explicit transaction management. However, `isolation_level` still works and is the current default. |
| DELETE journal mode | WAL journal mode | SQLite 3.7 (2010), widely adopted ~2020 | WAL is now the recommended default for most applications. Faster writes, concurrent reads. |
| Manual `CREATE TABLE IF NOT EXISTS` | `PRAGMA user_version` + migration files | Pattern (not a version change) | Structured, repeatable schema evolution instead of ad-hoc table creation. |

**Deprecated/outdated:**
- `INSERT OR REPLACE`: Still works but `ON CONFLICT DO UPDATE` is strictly better. Do not use `INSERT OR REPLACE` in new code.
- `sqlite3.version` attribute: Deprecated in Python 3.12, will be removed in 3.14. Use `sqlite3.sqlite_version` instead.

## Open Questions

1. **Should the economy table reference round_history or maps?**
   - What we know: Economy data is per-round, per-team. Round history is also per-round. The foreign key from economy to round_history ensures every economy row has a corresponding round.
   - What's unclear: Whether HLTV economy pages always have matching round history entries. If economy data exists for a round that is not in round_history (e.g., different parsing phases), the FK constraint would block insertion.
   - Recommendation: Keep the FK from economy to round_history for now. If it causes problems during parsing phases, a migration can relax it to reference maps instead. The FK constraint catches data integrity issues early.

2. **Should the HTML storage API be built in Phase 2 or deferred?**
   - What we know: CONTEXT.md lists this as Claude's discretion. The HTML storage layer is simple (~50 lines) and is needed by Phase 3 (Reconnaissance) to save sample pages.
   - Recommendation: Build it in Phase 2. It is a small, self-contained module that rounds out the storage foundation. Phase 3 should not have to invent its own HTML storage.

3. **How much provenance metadata is too much?**
   - What we know: CONTEXT.md requires `scraped_at`, `parser_version`, `source_url`. Every table has these columns.
   - What's unclear: Whether storing provenance per row in every table is worth the storage overhead, or if a separate `scrape_runs` table would be cleaner.
   - Recommendation: Per-row provenance is correct. Different rows in the same table may come from different scrape runs or parser versions. A `scrape_runs` table would require a join for every provenance query. The storage overhead is negligible (3 TEXT columns per row).

## Sources

### Primary (HIGH confidence)
- [SQLite UPSERT documentation](https://sqlite.org/lang_upsert.html) -- Complete syntax for ON CONFLICT DO UPDATE, excluded. pseudo-table, conflict target requirements
- [Python 3.12 sqlite3 documentation](https://docs.python.org/3.12/library/sqlite3.html) -- Connection API, context manager behavior, row_factory, autocommit attribute
- [SQLite PRAGMA documentation](https://www.sqlite.org/pragma.html) -- journal_mode, foreign_keys, user_version, busy_timeout
- [SQLite WAL documentation](https://sqlite.org/wal.html) -- Write-ahead logging benefits and limitations
- Local verification: SQLite 3.49.1 on Python 3.12.10, all features tested empirically (UPSERT, STRICT, RETURNING, WAL, foreign keys)

### Secondary (MEDIUM confidence)
- [Charles Leifer: Going Fast with SQLite and Python](https://charlesleifer.com/blog/going-fast-with-sqlite-and-python/) -- PRAGMA optimization recommendations (WAL, cache_size, synchronous)
- [Suckless SQLite schema migrations in Python](https://eskerda.com/sqlite-schema-migrations-python/) -- PRAGMA user_version migration pattern
- [SQLite Tutorial: UPSERT](https://www.sqlitetutorial.net/sqlite-upsert/) -- Additional UPSERT examples and edge cases

### Tertiary (LOW confidence)
- None -- all findings verified against official documentation or empirical testing

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All stdlib, all features verified empirically on the target Python/SQLite versions
- Architecture: HIGH -- Patterns are well-established (WAL, UPSERT, user_version migrations, gzip compression)
- Schema design: HIGH -- Based on known HLTV data model from FEATURES.md research and CONTEXT.md decisions
- Pitfalls: HIGH -- All pitfalls verified through empirical testing or official documentation

**Research date:** 2026-02-14
**Valid until:** 2026-06-14 (120 days -- SQLite and Python stdlib are highly stable, no rapid-change risk)
