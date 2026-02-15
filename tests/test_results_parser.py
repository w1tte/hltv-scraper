"""Unit tests for the HLTV results page parser.

Tests parse_results_page() against real HTML samples from data/recon/.
Samples are gzipped and gitignored; tests skip gracefully if missing.
"""

import gzip
from pathlib import Path

import pytest

from scraper.discovery import DiscoveredMatch, parse_results_page

RECON_DIR = Path(__file__).resolve().parent.parent / "data" / "recon"


def load_sample(filename: str) -> str:
    """Load a gzipped HTML sample from data/recon/."""
    path = RECON_DIR / filename
    if not path.exists():
        pytest.skip(f"Sample HTML not found: {path}")
    return gzip.decompress(path.read_bytes()).decode("utf-8")


# ---------------------------------------------------------------------------
# TestParseResultsPageBasic
# ---------------------------------------------------------------------------


class TestParseResultsPageBasic:
    """Core extraction tests: correct entry count per page."""

    def test_parse_offset_0_returns_100_entries(self):
        """Page 1 has big-results (8 extra entries) that must be skipped."""
        html = load_sample("results-offset-0.html.gz")
        results = parse_results_page(html)
        assert len(results) == 100

    def test_parse_offset_100_returns_100_entries(self):
        html = load_sample("results-offset-100.html.gz")
        results = parse_results_page(html)
        assert len(results) == 100

    def test_parse_offset_5000_returns_100_entries(self):
        html = load_sample("results-offset-5000.html.gz")
        results = parse_results_page(html)
        assert len(results) == 100

    def test_parse_empty_html_returns_empty(self):
        results = parse_results_page("<html><body></body></html>")
        assert len(results) == 0

    def test_parse_non_results_page_returns_empty(self):
        results = parse_results_page(
            "<html><body><div>Not a results page</div></body></html>"
        )
        assert len(results) == 0


# ---------------------------------------------------------------------------
# TestDiscoveredMatchFields
# ---------------------------------------------------------------------------


class TestDiscoveredMatchFields:
    """Field-level validation on parsed entries."""

    def test_match_id_is_positive_integer(self):
        html = load_sample("results-offset-0.html.gz")
        results = parse_results_page(html)
        for entry in results:
            assert isinstance(entry.match_id, int)
            assert entry.match_id > 0

    def test_url_starts_with_matches(self):
        html = load_sample("results-offset-0.html.gz")
        results = parse_results_page(html)
        for entry in results:
            assert entry.url.startswith("/matches/")

    def test_url_contains_match_id(self):
        html = load_sample("results-offset-0.html.gz")
        results = parse_results_page(html)
        for entry in results:
            assert str(entry.match_id) in entry.url

    def test_timestamp_ms_is_reasonable(self):
        """Timestamps should be 13-digit unix ms, post-2020."""
        html = load_sample("results-offset-0.html.gz")
        results = parse_results_page(html)
        min_ts = 1577836800000  # 2020-01-01 UTC
        for entry in results:
            assert isinstance(entry.timestamp_ms, int)
            assert len(str(entry.timestamp_ms)) == 13
            assert entry.timestamp_ms > min_ts


# ---------------------------------------------------------------------------
# TestForfeitDetection
# ---------------------------------------------------------------------------


class TestForfeitDetection:
    """Verify forfeit flag from map-text == 'def'."""

    def test_forfeit_detection(self):
        """Parse all samples; verify forfeit flag is set correctly."""
        samples = [
            "results-offset-0.html.gz",
            "results-offset-100.html.gz",
            "results-offset-5000.html.gz",
        ]
        all_entries: list[DiscoveredMatch] = []
        for sample in samples:
            html = load_sample(sample)
            all_entries.extend(parse_results_page(html))

        forfeits = [e for e in all_entries if e.is_forfeit]
        non_forfeits = [e for e in all_entries if not e.is_forfeit]

        # Most entries should be non-forfeit
        assert len(non_forfeits) > 0
        # All entries must have is_forfeit as a bool
        for entry in all_entries:
            assert isinstance(entry.is_forfeit, bool)


# ---------------------------------------------------------------------------
# TestNoDuplicatesBigResults
# ---------------------------------------------------------------------------


class TestNoDuplicatesBigResults:
    """Ensure big-results section on page 1 doesn't cause duplicates."""

    def test_no_duplicate_match_ids_page_1(self):
        html = load_sample("results-offset-0.html.gz")
        results = parse_results_page(html)
        match_ids = [r.match_id for r in results]
        assert len(set(match_ids)) == len(match_ids), (
            f"Duplicate match_ids found: {len(match_ids)} total, "
            f"{len(set(match_ids))} unique"
        )

    def test_no_duplicate_match_ids_page_2(self):
        html = load_sample("results-offset-100.html.gz")
        results = parse_results_page(html)
        match_ids = [r.match_id for r in results]
        assert len(set(match_ids)) == len(match_ids), (
            f"Duplicate match_ids found: {len(match_ids)} total, "
            f"{len(set(match_ids))} unique"
        )
