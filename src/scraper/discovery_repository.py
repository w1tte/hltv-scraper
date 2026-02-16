"""Data access layer for match discovery queue operations.

Provides DiscoveryRepository with UPSERT semantics for the scrape_queue
table and offset progress tracking for the discovery_progress table.

Follows the same patterns as MatchRepository: receives a raw
``sqlite3.Connection``, uses module-level SQL constants, and wraps
mutations in ``with self.conn:`` for automatic commit/rollback.

CRITICAL: The UPSERT on scrape_queue does NOT update ``status``.
Re-discovering an already-scraped match preserves its status.
"""

import sqlite3
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# UPSERT SQL constants
# ---------------------------------------------------------------------------

UPSERT_QUEUE = """
    INSERT INTO scrape_queue (match_id, url, offset, discovered_at, is_forfeit, status)
    VALUES (:match_id, :url, :offset, :discovered_at, :is_forfeit, 'pending')
    ON CONFLICT(match_id) DO UPDATE SET
        url           = excluded.url,
        offset        = excluded.offset,
        discovered_at = excluded.discovered_at,
        is_forfeit    = excluded.is_forfeit
"""

MARK_OFFSET = """
    INSERT OR REPLACE INTO discovery_progress (offset, completed_at)
    VALUES (?, ?)
"""

UPDATE_STATUS = "UPDATE scrape_queue SET status = ? WHERE match_id = ?"


# ---------------------------------------------------------------------------
# Repository class
# ---------------------------------------------------------------------------

class DiscoveryRepository:
    """Data access layer for the match discovery scrape queue.

    Wraps all database operations for ``scrape_queue`` and
    ``discovery_progress`` tables.  Receives a raw
    ``sqlite3.Connection`` (not a Database instance) so tests can
    pass any connection, including in-memory databases.

    Write methods use ``with self.conn:`` for automatic commit on
    success / rollback on exception.  Exceptions propagate to callers.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ------------------------------------------------------------------
    # Queue UPSERT methods
    # ------------------------------------------------------------------

    def upsert_batch(self, batch: list[dict]) -> None:
        """Atomically upsert a page of discovered matches.

        Each dict in *batch* must contain keys: match_id, url, offset,
        discovered_at, is_forfeit.  The ``status`` field is always set
        to ``'pending'`` on initial insert.  On conflict (re-discovery),
        status is NOT updated -- already-scraped matches keep their
        status.
        """
        with self.conn:
            for row in batch:
                self.conn.execute(UPSERT_QUEUE, row)

    # ------------------------------------------------------------------
    # Offset progress methods
    # ------------------------------------------------------------------

    def mark_offset_complete(self, offset: int) -> None:
        """Record that a results page offset has been fully processed."""
        with self.conn:
            self.conn.execute(
                MARK_OFFSET,
                (offset, datetime.now(timezone.utc).isoformat()),
            )

    def get_completed_offsets(self) -> set[int]:
        """Return all offsets that have been successfully processed."""
        rows = self.conn.execute(
            "SELECT offset FROM discovery_progress"
        ).fetchall()
        return {r[0] for r in rows}

    # ------------------------------------------------------------------
    # Combined atomic operation
    # ------------------------------------------------------------------

    def persist_page(self, batch: list[dict], offset: int) -> None:
        """Atomically upsert a batch of matches AND mark offset complete.

        Both the queue upserts and the progress insert happen inside a
        single ``with self.conn:`` block, ensuring either both succeed
        or both roll back.
        """
        with self.conn:
            for row in batch:
                self.conn.execute(UPSERT_QUEUE, row)
            self.conn.execute(
                MARK_OFFSET,
                (offset, datetime.now(timezone.utc).isoformat()),
            )

    # ------------------------------------------------------------------
    # Incremental discovery helpers
    # ------------------------------------------------------------------

    def count_new_matches(self, match_ids: list[int]) -> int:
        """Count how many of the given match_ids are NOT already in scrape_queue.

        Used by incremental discovery to decide whether to stop early:
        if all matches on a page are already known, there is nothing new
        to discover beyond this point.

        Args:
            match_ids: List of match IDs from a parsed results page.

        Returns:
            Number of match_ids not yet present in scrape_queue.
        """
        if not match_ids:
            return 0
        placeholders = ",".join("?" for _ in match_ids)
        row = self.conn.execute(
            f"SELECT COUNT(*) FROM scrape_queue WHERE match_id IN ({placeholders})",
            match_ids,
        ).fetchone()
        existing = row[0]
        return len(match_ids) - existing

    def reset_failed_matches(self) -> int:
        """Reset all failed matches back to pending status.

        Called at pipeline start so that previously-failed matches get
        another chance on each run.  Returns the number of rows affected.
        """
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE scrape_queue SET status = 'pending' WHERE status = 'failed'"
            )
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Count / read methods
    # ------------------------------------------------------------------

    def count_pending(self) -> int:
        """Return the number of matches with status 'pending'."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM scrape_queue WHERE status = 'pending'"
        ).fetchone()[0]

    def count_total(self) -> int:
        """Return the total number of matches in the scrape queue."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM scrape_queue"
        ).fetchone()[0]

    def get_queue_entry(self, match_id: int) -> dict | None:
        """Return a queue entry as a dict, or None if not found."""
        row = self.conn.execute(
            "SELECT * FROM scrape_queue WHERE match_id = ?", (match_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------
    # Queue management methods (Phase 5 orchestrator)
    # ------------------------------------------------------------------

    def get_pending_matches(self, limit: int = 10) -> list[dict]:
        """Return pending queue entries ordered by match_id.

        The Phase 5 orchestrator calls this to get the next batch of
        matches to scrape.  Returns up to *limit* entries with
        status = 'pending'.
        """
        rows = self.conn.execute(
            "SELECT * FROM scrape_queue WHERE status = 'pending' "
            "ORDER BY match_id LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_status(self, match_id: int, status: str) -> None:
        """Transition a queue entry to 'scraped' or 'failed'.

        Uses ``with self.conn:`` for automatic commit/rollback.
        """
        with self.conn:
            self.conn.execute(UPDATE_STATUS, (status, match_id))
