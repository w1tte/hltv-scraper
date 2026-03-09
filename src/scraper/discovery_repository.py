"""Data access layer for match discovery queue operations.

Provides DiscoveryRepository with UPSERT semantics for the scrape_queue
table and offset progress tracking for the discovery_progress table.

CRITICAL: The UPSERT on scrape_queue does NOT update ``status``.
Re-discovering an already-scraped match preserves its status.
"""

from datetime import datetime, timezone

import psycopg2.extras

# ---------------------------------------------------------------------------
# UPSERT SQL constants (PostgreSQL syntax)
# ---------------------------------------------------------------------------

UPSERT_QUEUE = """
    INSERT INTO scrape_queue (match_id, url, "offset", discovered_at, is_forfeit, status)
    VALUES (%(match_id)s, %(url)s, %(offset)s, %(discovered_at)s, %(is_forfeit)s, 'pending')
    ON CONFLICT(match_id) DO UPDATE SET
        url           = EXCLUDED.url,
        "offset"      = EXCLUDED."offset",
        discovered_at = EXCLUDED.discovered_at,
        is_forfeit    = EXCLUDED.is_forfeit
"""

MARK_OFFSET = """
    INSERT INTO discovery_progress ("offset", completed_at)
    VALUES (%s, %s)
    ON CONFLICT("offset") DO UPDATE SET completed_at = EXCLUDED.completed_at
"""

UPDATE_STATUS = "UPDATE scrape_queue SET status = %s WHERE match_id = %s"

MARK_IN_PROGRESS = (
    "UPDATE scrape_queue SET status = 'in_progress', "
    "started_at = %s WHERE match_id = %s"
)

RESET_IN_PROGRESS = (
    "UPDATE scrape_queue SET status = 'pending', started_at = NULL "
    "WHERE status = 'in_progress'"
)


# ---------------------------------------------------------------------------
# Repository class
# ---------------------------------------------------------------------------

class DiscoveryRepository:
    """Data access layer for the match discovery scrape queue.

    Wraps all database operations for ``scrape_queue`` and
    ``discovery_progress`` tables. Receives a psycopg2 connection.
    """

    def __init__(self, conn) -> None:
        self.conn = conn

    # ------------------------------------------------------------------
    # Queue UPSERT methods
    # ------------------------------------------------------------------

    def upsert_batch(self, batch: list[dict]) -> None:
        with self.conn:
            with self.conn.cursor() as cur:
                for row in batch:
                    cur.execute(UPSERT_QUEUE, row)

    # ------------------------------------------------------------------
    # Offset progress methods
    # ------------------------------------------------------------------

    def mark_offset_complete(self, offset: int) -> None:
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(
                    MARK_OFFSET,
                    (offset, datetime.now(timezone.utc).isoformat()),
                )

    def get_completed_offsets(self) -> set[int]:
        with self.conn.cursor() as cur:
            cur.execute('SELECT "offset" FROM discovery_progress')
            return {r[0] for r in cur.fetchall()}

    # ------------------------------------------------------------------
    # Combined atomic operation
    # ------------------------------------------------------------------

    def persist_page(self, batch: list[dict], offset: int) -> None:
        with self.conn:
            with self.conn.cursor() as cur:
                for row in batch:
                    cur.execute(UPSERT_QUEUE, row)
                cur.execute(
                    MARK_OFFSET,
                    (offset, datetime.now(timezone.utc).isoformat()),
                )

    # ------------------------------------------------------------------
    # Incremental discovery helpers
    # ------------------------------------------------------------------

    def count_new_matches(self, match_ids: list[int]) -> int:
        if not match_ids:
            return 0
        with self.conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(match_ids))
            cur.execute(
                f"SELECT COUNT(*) FROM scrape_queue WHERE match_id IN ({placeholders})",
                match_ids,
            )
            existing = cur.fetchone()[0]
        return len(match_ids) - existing

    def reset_failed_matches(self, max_attempts: int = 5) -> int:
        """Auto-reset failed matches that haven't exhausted their retries.

        Only resets matches with fewer than *max_attempts* attempts.
        Matches at or above the limit stay 'failed' for manual review.
        """
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE scrape_queue SET status = 'pending' "
                    "WHERE status = 'failed' AND attempts < %s",
                    (max_attempts,),
                )
                return cur.rowcount

    def mark_failed(self, match_id: int, max_attempts: int = 5) -> None:
        """Increment attempt counter and set appropriate failure status.

        - attempts < max_attempts  → 'failed'  (eligible for auto-retry)
        - attempts >= max_attempts → 'failed_permanent'  (manual retry
          already happened and failed again — final verdict)
        """
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE scrape_queue "
                    "SET attempts = attempts + 1, "
                    "    status = CASE WHEN attempts >= %s "
                    "                  THEN 'failed_permanent' "
                    "                  ELSE 'failed' END "
                    "WHERE match_id = %s",
                    (max_attempts, match_id),
                )

    # ------------------------------------------------------------------
    # Count / read methods
    # ------------------------------------------------------------------

    def get_queue_summary(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT status, COUNT(*) FROM scrape_queue GROUP BY status"
            )
            rows = cur.fetchall()
        summary = {"pending": 0, "scraped": 0, "failed": 0}
        for status, count in rows:
            summary[status] = count
        summary["total"] = sum(summary.values())
        return summary

    def count_pending(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM scrape_queue WHERE status IN ('pending', 'retry')")
            return cur.fetchone()[0]

    def count_total(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM scrape_queue")
            return cur.fetchone()[0]

    def get_queue_entry(self, match_id: int) -> dict | None:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM scrape_queue WHERE match_id = %s", (match_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------
    # Queue management methods
    # ------------------------------------------------------------------

    def get_pending_matches(self, limit: int = 10) -> list[dict]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM scrape_queue WHERE status IN ('pending', 'retry') "
                "ORDER BY match_id LIMIT %s",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]

    def update_status(self, match_id: int, status: str) -> None:
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(UPDATE_STATUS, (status, match_id))

    def mark_in_progress(self, match_id: int) -> None:
        """Set status to 'in_progress' with a started_at timestamp."""
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(
                    MARK_IN_PROGRESS,
                    (datetime.now(timezone.utc).isoformat(), match_id),
                )

    def recover_in_progress(self) -> int:
        """Reset all 'in_progress' matches back to 'pending' (crash recovery).

        Returns the number of recovered matches.
        """
        with self.conn:
            with self.conn.cursor() as cur:
                cur.execute(RESET_IN_PROGRESS)
                return cur.rowcount
