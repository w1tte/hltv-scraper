"""Tests for pipeline utilities and the run_pipeline orchestrator.

Tests the three utility classes (ShutdownHandler, ConsecutiveFailureTracker,
ProgressTracker) and the run_pipeline function with mocked stage orchestrators.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scraper.config import ScraperConfig
from scraper.pipeline import (
    ConsecutiveFailureTracker,
    ProgressTracker,
    ShutdownHandler,
    run_pipeline,
)


# ---------------------------------------------------------------------------
# ConsecutiveFailureTracker
# ---------------------------------------------------------------------------


class TestConsecutiveFailureTracker:
    """Tests for ConsecutiveFailureTracker."""

    def test_tracker_initial_state(self):
        """New tracker starts at 0 consecutive failures, not halted."""
        tracker = ConsecutiveFailureTracker(threshold=3)
        assert tracker.consecutive == 0
        assert tracker.should_halt is False

    def test_tracker_under_threshold(self):
        """Two failures with threshold=3 does not trigger halt."""
        tracker = ConsecutiveFailureTracker(threshold=3)
        tracker.record_failure()
        tracker.record_failure()
        assert tracker.consecutive == 2
        assert tracker.should_halt is False

    def test_tracker_at_threshold(self):
        """Three failures with threshold=3 triggers halt; record_failure returns True."""
        tracker = ConsecutiveFailureTracker(threshold=3)
        tracker.record_failure()
        tracker.record_failure()
        result = tracker.record_failure()
        assert result is True
        assert tracker.should_halt is True
        assert tracker.consecutive == 3

    def test_tracker_reset_on_success(self):
        """A success after failures resets the counter to 0."""
        tracker = ConsecutiveFailureTracker(threshold=3)
        tracker.record_failure()
        tracker.record_failure()
        tracker.record_success()
        assert tracker.consecutive == 0
        assert tracker.should_halt is False

    def test_tracker_custom_threshold(self):
        """Threshold of 1 triggers halt on the first failure."""
        tracker = ConsecutiveFailureTracker(threshold=1)
        result = tracker.record_failure()
        assert result is True
        assert tracker.should_halt is True


# ---------------------------------------------------------------------------
# ProgressTracker
# ---------------------------------------------------------------------------


class TestProgressTracker:
    """Tests for ProgressTracker."""

    def test_progress_initial_state(self):
        """New tracker starts with all counts at 0."""
        progress = ProgressTracker(total=10)
        assert progress.completed == 0
        assert progress.failed == 0
        assert progress.skipped == 0

    def test_progress_log_match(self, caplog):
        """log_match increments completed and produces a log message."""
        progress = ProgressTracker(total=5)
        with caplog.at_level(logging.INFO):
            progress.log_match(match_id=12345, status="scraped", elapsed=1.5)
        assert progress.completed == 1
        assert "12345" in caplog.text
        assert "ok" in caplog.text

    def test_progress_log_match_failure(self, caplog):
        """log_match with non-scraped status shows FAIL in log."""
        progress = ProgressTracker(total=5)
        with caplog.at_level(logging.INFO):
            progress.log_match(match_id=99999, status="failed", elapsed=0.5)
        assert progress.completed == 1
        assert "FAIL" in caplog.text

    def test_progress_summary(self):
        """summary() returns dict with correct keys and wall_time >= 0."""
        progress = ProgressTracker(total=0)
        progress.completed = 5
        progress.failed = 2
        progress.skipped = 1
        summary = progress.summary()
        assert summary["completed"] == 5
        assert summary["failed"] == 2
        assert summary["skipped"] == 1
        assert "wall_time" in summary
        assert isinstance(summary["wall_time"], float)
        assert summary["wall_time"] >= 0

    def test_progress_format_summary(self):
        """format_summary() returns a non-empty multiline string."""
        progress = ProgressTracker(total=0)
        progress.completed = 3
        text = progress.format_summary()
        assert isinstance(text, str)
        assert len(text) > 0
        assert "Completed" in text
        assert "3" in text


# ---------------------------------------------------------------------------
# ShutdownHandler
# ---------------------------------------------------------------------------


class TestShutdownHandler:
    """Tests for ShutdownHandler."""

    def test_shutdown_initial_state(self):
        """New handler starts with is_set=False."""
        handler = ShutdownHandler()
        assert handler.is_set is False

    def test_shutdown_set(self):
        """After setting the internal event, is_set is True."""
        handler = ShutdownHandler()
        handler._event.set()
        assert handler.is_set is True


# ---------------------------------------------------------------------------
# run_pipeline
# ---------------------------------------------------------------------------


def _make_stats(batch_size=0, fetched=0, parsed=0, failed=0, fetch_errors=0, **kwargs):
    """Build a stats dict compatible with stage orchestrator return values."""
    stats = {
        "batch_size": batch_size,
        "fetched": fetched,
        "parsed": parsed,
        "failed": failed,
        "fetch_errors": fetch_errors,
    }
    stats.update(kwargs)
    return stats


def _make_discovery_stats(matches_found=0, new_matches=0, pages_fetched=0):
    """Build a stats dict compatible with run_discovery return value."""
    return {
        "matches_found": matches_found,
        "new_matches": new_matches,
        "pages_fetched": pages_fetched,
    }


class TestRunPipeline:
    """Tests for the run_pipeline function with mocked orchestrators."""

    @pytest.mark.asyncio
    @patch("scraper.pipeline.run_performance_economy", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_map_stats", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_match_overview", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_discovery", new_callable=AsyncMock)
    async def test_pipeline_runs_all_stages(
        self, mock_discovery, mock_overview, mock_map_stats, mock_perf_econ
    ):
        """All 4 orchestrators are called when no pending work exists."""
        mock_discovery.return_value = _make_discovery_stats()
        mock_overview.return_value = _make_stats(batch_size=0)
        mock_map_stats.return_value = _make_stats(batch_size=0)
        mock_perf_econ.return_value = _make_stats(batch_size=0)

        config = ScraperConfig()
        shutdown = ShutdownHandler()
        discovery_repo = MagicMock()
        discovery_repo.reset_failed_matches.return_value = 0

        results = await run_pipeline(
            client=MagicMock(),
            match_repo=MagicMock(),
            discovery_repo=discovery_repo,
            storage=MagicMock(),
            config=config,
            shutdown=shutdown,
        )

        mock_discovery.assert_called_once()
        mock_overview.assert_called_once()
        mock_map_stats.assert_called_once()
        mock_perf_econ.assert_called_once()
        assert results["halted"] is False

    @pytest.mark.asyncio
    @patch("scraper.pipeline.run_performance_economy", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_map_stats", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_match_overview", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_discovery", new_callable=AsyncMock)
    async def test_pipeline_loops_until_no_work(
        self, mock_discovery, mock_overview, mock_map_stats, mock_perf_econ
    ):
        """Overview stage loops until batch_size=0 is returned."""
        mock_discovery.return_value = _make_discovery_stats(matches_found=5, new_matches=5)
        # First call: work to do (batch_size=5, parsed=5)
        # Second call: no more work (batch_size=0)
        mock_overview.side_effect = [
            _make_stats(batch_size=5, fetched=5, parsed=5),
            _make_stats(batch_size=0),
        ]
        mock_map_stats.return_value = _make_stats(batch_size=0)
        mock_perf_econ.return_value = _make_stats(batch_size=0)

        config = ScraperConfig()
        shutdown = ShutdownHandler()
        discovery_repo = MagicMock()
        discovery_repo.reset_failed_matches.return_value = 0

        results = await run_pipeline(
            client=MagicMock(),
            match_repo=MagicMock(),
            discovery_repo=discovery_repo,
            storage=MagicMock(),
            config=config,
            shutdown=shutdown,
        )

        assert mock_overview.call_count == 2
        assert results["overview"]["parsed"] == 5
        assert results["halted"] is False

    @pytest.mark.asyncio
    @patch("scraper.pipeline.run_performance_economy", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_map_stats", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_match_overview", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_discovery", new_callable=AsyncMock)
    async def test_pipeline_halts_on_consecutive_failures(
        self, mock_discovery, mock_overview, mock_map_stats, mock_perf_econ
    ):
        """Pipeline sets halted=True when consecutive failure threshold is reached."""
        mock_discovery.return_value = _make_discovery_stats(matches_found=10, new_matches=10)
        # Every overview batch has fetch errors and no successful parses
        mock_overview.return_value = _make_stats(
            batch_size=5, fetched=0, parsed=0, failed=0, fetch_errors=1
        )
        mock_map_stats.return_value = _make_stats(batch_size=0)
        mock_perf_econ.return_value = _make_stats(batch_size=0)

        config = ScraperConfig(consecutive_failure_threshold=3)
        shutdown = ShutdownHandler()
        discovery_repo = MagicMock()
        discovery_repo.reset_failed_matches.return_value = 0

        results = await run_pipeline(
            client=MagicMock(),
            match_repo=MagicMock(),
            discovery_repo=discovery_repo,
            storage=MagicMock(),
            config=config,
            shutdown=shutdown,
        )

        assert results["halted"] is True
        assert "overview" in results["halt_reason"].lower() or "consecutive" in results["halt_reason"].lower()

    @pytest.mark.asyncio
    @patch("scraper.pipeline.run_performance_economy", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_map_stats", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_match_overview", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_discovery", new_callable=AsyncMock)
    async def test_pipeline_respects_shutdown(
        self, mock_discovery, mock_overview, mock_map_stats, mock_perf_econ
    ):
        """Pipeline exits quickly when shutdown is already set."""
        config = ScraperConfig()
        shutdown = ShutdownHandler()
        shutdown._event.set()  # Pre-set shutdown
        discovery_repo = MagicMock()
        discovery_repo.reset_failed_matches.return_value = 0

        results = await run_pipeline(
            client=MagicMock(),
            match_repo=MagicMock(),
            discovery_repo=discovery_repo,
            storage=MagicMock(),
            config=config,
            shutdown=shutdown,
        )

        # Discovery should not be called (shutdown was already set)
        mock_discovery.assert_not_called()
        mock_overview.assert_not_called()
        assert results["halted"] is True
        assert "shutdown" in results["halt_reason"].lower()

    @pytest.mark.asyncio
    @patch("scraper.pipeline.run_performance_economy", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_map_stats", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_match_overview", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_discovery", new_callable=AsyncMock)
    async def test_pipeline_resets_failed_matches(
        self, mock_discovery, mock_overview, mock_map_stats, mock_perf_econ
    ):
        """Pipeline calls reset_failed_matches when force_rescrape=False."""
        mock_discovery.return_value = _make_discovery_stats()
        mock_overview.return_value = _make_stats(batch_size=0)
        mock_map_stats.return_value = _make_stats(batch_size=0)
        mock_perf_econ.return_value = _make_stats(batch_size=0)

        config = ScraperConfig()
        shutdown = ShutdownHandler()
        discovery_repo = MagicMock()
        discovery_repo.reset_failed_matches.return_value = 2

        await run_pipeline(
            client=MagicMock(),
            match_repo=MagicMock(),
            discovery_repo=discovery_repo,
            storage=MagicMock(),
            config=config,
            shutdown=shutdown,
            force_rescrape=False,
        )

        discovery_repo.reset_failed_matches.assert_called_once()

    @pytest.mark.asyncio
    @patch("scraper.pipeline.run_performance_economy", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_map_stats", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_match_overview", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_discovery", new_callable=AsyncMock)
    async def test_pipeline_skips_reset_on_force_rescrape(
        self, mock_discovery, mock_overview, mock_map_stats, mock_perf_econ
    ):
        """Pipeline does NOT call reset_failed_matches when force_rescrape=True."""
        mock_discovery.return_value = _make_discovery_stats()
        mock_overview.return_value = _make_stats(batch_size=0)
        mock_map_stats.return_value = _make_stats(batch_size=0)
        mock_perf_econ.return_value = _make_stats(batch_size=0)

        config = ScraperConfig()
        shutdown = ShutdownHandler()
        discovery_repo = MagicMock()

        await run_pipeline(
            client=MagicMock(),
            match_repo=MagicMock(),
            discovery_repo=discovery_repo,
            storage=MagicMock(),
            config=config,
            shutdown=shutdown,
            force_rescrape=True,
        )

        discovery_repo.reset_failed_matches.assert_not_called()

    @pytest.mark.asyncio
    @patch("scraper.pipeline.run_performance_economy", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_map_stats", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_match_overview", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_discovery", new_callable=AsyncMock)
    async def test_pipeline_accumulates_stats(
        self, mock_discovery, mock_overview, mock_map_stats, mock_perf_econ
    ):
        """Pipeline accumulates parsed/failed counts across multiple loop iterations."""
        mock_discovery.return_value = _make_discovery_stats(matches_found=10, new_matches=10)
        # Two overview batches, then done
        mock_overview.side_effect = [
            _make_stats(batch_size=5, fetched=5, parsed=4, failed=1),
            _make_stats(batch_size=3, fetched=3, parsed=3, failed=0),
            _make_stats(batch_size=0),
        ]
        # Two map_stats batches, then done
        mock_map_stats.side_effect = [
            _make_stats(batch_size=4, fetched=4, parsed=4, failed=0),
            _make_stats(batch_size=0),
        ]
        mock_perf_econ.return_value = _make_stats(batch_size=0)

        config = ScraperConfig()
        shutdown = ShutdownHandler()
        discovery_repo = MagicMock()
        discovery_repo.reset_failed_matches.return_value = 0

        results = await run_pipeline(
            client=MagicMock(),
            match_repo=MagicMock(),
            discovery_repo=discovery_repo,
            storage=MagicMock(),
            config=config,
            shutdown=shutdown,
        )

        assert results["overview"]["parsed"] == 7  # 4 + 3
        assert results["overview"]["failed"] == 1
        assert results["map_stats"]["parsed"] == 4
        assert results["halted"] is False

    @pytest.mark.asyncio
    @patch("scraper.pipeline.run_performance_economy", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_map_stats", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_match_overview", new_callable=AsyncMock)
    @patch("scraper.pipeline.run_discovery", new_callable=AsyncMock)
    async def test_pipeline_returns_summary(
        self, mock_discovery, mock_overview, mock_map_stats, mock_perf_econ
    ):
        """Pipeline result dict includes a summary with wall_time."""
        mock_discovery.return_value = _make_discovery_stats()
        mock_overview.return_value = _make_stats(batch_size=0)
        mock_map_stats.return_value = _make_stats(batch_size=0)
        mock_perf_econ.return_value = _make_stats(batch_size=0)

        config = ScraperConfig()
        shutdown = ShutdownHandler()
        discovery_repo = MagicMock()
        discovery_repo.reset_failed_matches.return_value = 0

        results = await run_pipeline(
            client=MagicMock(),
            match_repo=MagicMock(),
            discovery_repo=discovery_repo,
            storage=MagicMock(),
            config=config,
            shutdown=shutdown,
        )

        assert "summary" in results
        assert "wall_time" in results["summary"]
        assert isinstance(results["summary"]["wall_time"], float)
        assert results["summary"]["wall_time"] >= 0
        assert "completed" in results["summary"]
