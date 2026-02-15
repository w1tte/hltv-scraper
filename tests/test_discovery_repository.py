"""Tests for the DiscoveryRepository UPSERT and read operations.

Exercises queue upsert, offset progress tracking, persist_page atomicity,
count methods, and verifies the critical UPSERT semantic: re-discovery
does NOT clobber an already-scraped status.
"""

import pytest

from scraper.db import Database
from scraper.discovery_repository import DiscoveryRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    yield database
    database.close()


@pytest.fixture
def repo(db):
    return DiscoveryRepository(db.conn)


# ---------------------------------------------------------------------------
# Data helper
# ---------------------------------------------------------------------------

def make_queue_entry(match_id=1, **overrides):
    """Return a complete scrape_queue dict with sensible defaults."""
    data = {
        "match_id": match_id,
        "url": f"/matches/{match_id}/team-a-vs-team-b-event",
        "offset": 0,
        "discovered_at": "2026-02-15T12:00:00+00:00",
        "is_forfeit": 0,
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# UPSERT batch
# ---------------------------------------------------------------------------

class TestUpsertBatch:
    def test_upsert_batch_inserts(self, repo):
        """Insert batch of 3 entries, count_total returns 3."""
        batch = [
            make_queue_entry(match_id=1),
            make_queue_entry(match_id=2),
            make_queue_entry(match_id=3),
        ]
        repo.upsert_batch(batch)
        assert repo.count_total() == 3

    def test_upsert_batch_with_forfeit(self, repo):
        """Insert entry with is_forfeit=1, verify via get_queue_entry."""
        repo.upsert_batch([make_queue_entry(match_id=10, is_forfeit=1)])
        entry = repo.get_queue_entry(10)
        assert entry is not None
        assert entry["is_forfeit"] == 1

    def test_upsert_batch_preserves_status(self, repo):
        """Re-upsert a scraped match: status stays 'scraped', url is updated.

        This is the CRITICAL UPSERT semantic test.  On re-discovery,
        the UPSERT refreshes metadata (url, offset, etc.) but does NOT
        reset status from 'scraped' back to 'pending'.
        """
        # First insert
        repo.upsert_batch([make_queue_entry(match_id=1, url="/matches/1/old-slug")])

        # Manually mark as scraped (simulating Phase 5 completing)
        repo.conn.execute(
            "UPDATE scrape_queue SET status = 'scraped' WHERE match_id = 1"
        )
        repo.conn.commit()

        # Re-discover same match with a different URL
        repo.upsert_batch([make_queue_entry(match_id=1, url="/matches/1/new-slug")])

        entry = repo.get_queue_entry(1)
        assert entry["status"] == "scraped"  # NOT reset to 'pending'
        assert entry["url"] == "/matches/1/new-slug"  # url IS updated

    def test_upsert_batch_updates_on_conflict(self, repo):
        """Upsert entry twice with different offset, only 1 row exists."""
        repo.upsert_batch([make_queue_entry(match_id=1, offset=0)])
        repo.upsert_batch([make_queue_entry(match_id=1, offset=100)])

        assert repo.count_total() == 1
        entry = repo.get_queue_entry(1)
        assert entry["offset"] == 100


# ---------------------------------------------------------------------------
# Offset progress
# ---------------------------------------------------------------------------

class TestOffsetProgress:
    def test_mark_offset_complete(self, repo):
        """Mark offset 0 complete, get_completed_offsets returns {0}."""
        repo.mark_offset_complete(0)
        assert repo.get_completed_offsets() == {0}

    def test_mark_multiple_offsets(self, repo):
        """Mark 0, 100, 200 complete, get_completed_offsets returns all three."""
        repo.mark_offset_complete(0)
        repo.mark_offset_complete(100)
        repo.mark_offset_complete(200)
        assert repo.get_completed_offsets() == {0, 100, 200}

    def test_get_completed_offsets_empty(self, repo):
        """Initially returns empty set."""
        assert repo.get_completed_offsets() == set()


# ---------------------------------------------------------------------------
# Persist page (atomic batch + offset)
# ---------------------------------------------------------------------------

class TestPersistPage:
    def test_persist_page_atomic(self, repo):
        """persist_page upserts batch AND marks offset in one transaction."""
        batch = [
            make_queue_entry(match_id=1),
            make_queue_entry(match_id=2),
            make_queue_entry(match_id=3),
        ]
        repo.persist_page(batch, offset=100)

        assert repo.count_total() == 3
        assert 100 in repo.get_completed_offsets()


# ---------------------------------------------------------------------------
# Count methods
# ---------------------------------------------------------------------------

class TestCountMethods:
    def test_count_pending_and_total(self, repo):
        """Insert 3 entries (all pending), count_pending==3, count_total==3."""
        batch = [
            make_queue_entry(match_id=1),
            make_queue_entry(match_id=2),
            make_queue_entry(match_id=3),
        ]
        repo.upsert_batch(batch)
        assert repo.count_pending() == 3
        assert repo.count_total() == 3

    def test_count_pending_excludes_scraped(self, repo):
        """Insert 3 entries, mark 1 as scraped, count_pending==2, count_total==3."""
        batch = [
            make_queue_entry(match_id=1),
            make_queue_entry(match_id=2),
            make_queue_entry(match_id=3),
        ]
        repo.upsert_batch(batch)
        repo.conn.execute(
            "UPDATE scrape_queue SET status = 'scraped' WHERE match_id = 1"
        )
        repo.conn.commit()

        assert repo.count_pending() == 2
        assert repo.count_total() == 3


# ---------------------------------------------------------------------------
# Get queue entry
# ---------------------------------------------------------------------------

class TestGetQueueEntry:
    def test_get_queue_entry_found(self, repo):
        """Insert and retrieve, verify all fields."""
        entry_data = make_queue_entry(
            match_id=42,
            url="/matches/42/navi-vs-g2-blast",
            offset=200,
            discovered_at="2026-02-15T14:30:00+00:00",
            is_forfeit=0,
        )
        repo.upsert_batch([entry_data])

        entry = repo.get_queue_entry(42)
        assert entry is not None
        assert entry["match_id"] == 42
        assert entry["url"] == "/matches/42/navi-vs-g2-blast"
        assert entry["offset"] == 200
        assert entry["discovered_at"] == "2026-02-15T14:30:00+00:00"
        assert entry["is_forfeit"] == 0
        assert entry["status"] == "pending"

    def test_get_queue_entry_not_found(self, repo):
        """Returns None for non-existent match_id."""
        assert repo.get_queue_entry(99999) is None


# ---------------------------------------------------------------------------
# Queue management (Phase 5 orchestrator methods)
# ---------------------------------------------------------------------------

class TestQueueManagement:
    def test_get_pending_matches_returns_pending_only(self, repo):
        """Insert 3 pending, mark 1 scraped, get_pending returns only 2."""
        batch = [
            make_queue_entry(match_id=1),
            make_queue_entry(match_id=2),
            make_queue_entry(match_id=3),
        ]
        repo.upsert_batch(batch)
        # Mark match 1 as scraped using the raw SQL
        repo.conn.execute(
            "UPDATE scrape_queue SET status = 'scraped' WHERE match_id = 1"
        )
        repo.conn.commit()

        pending = repo.get_pending_matches(limit=10)
        assert len(pending) == 2
        assert all(p["status"] == "pending" for p in pending)
        assert {p["match_id"] for p in pending} == {2, 3}

    def test_get_pending_matches_respects_limit(self, repo):
        """Insert 5 pending, limit=2 returns exactly 2."""
        batch = [make_queue_entry(match_id=i) for i in range(1, 6)]
        repo.upsert_batch(batch)

        pending = repo.get_pending_matches(limit=2)
        assert len(pending) == 2

    def test_get_pending_matches_ordered_by_match_id(self, repo):
        """Insert with match_ids [300, 100, 200], returned in order [100, 200, 300]."""
        batch = [
            make_queue_entry(match_id=300),
            make_queue_entry(match_id=100),
            make_queue_entry(match_id=200),
        ]
        repo.upsert_batch(batch)

        pending = repo.get_pending_matches(limit=10)
        assert [p["match_id"] for p in pending] == [100, 200, 300]

    def test_update_status_to_scraped(self, repo):
        """update_status transitions entry from pending to scraped."""
        repo.upsert_batch([make_queue_entry(match_id=1)])
        repo.update_status(1, "scraped")

        entry = repo.get_queue_entry(1)
        assert entry["status"] == "scraped"

    def test_update_status_to_failed(self, repo):
        """update_status transitions entry from pending to failed."""
        repo.upsert_batch([make_queue_entry(match_id=1)])
        repo.update_status(1, "failed")

        entry = repo.get_queue_entry(1)
        assert entry["status"] == "failed"

    def test_get_pending_matches_empty(self, repo):
        """Returns empty list when no pending entries exist."""
        assert repo.get_pending_matches(limit=10) == []
