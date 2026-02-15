"""Unit tests for HtmlStorage results page methods (offset-based storage)."""

import gzip

import pytest

from scraper.storage import HtmlStorage


class TestSaveAndLoadResultsPage:
    """Tests for round-trip save/load of results listing pages."""

    def test_save_and_load_results_page(self, tmp_path):
        """Save results page at offset 0, load it back, assert identical."""
        storage = HtmlStorage(tmp_path)
        original = "<html><body>Results page offset 0</body></html>"
        storage.save_results_page(original, offset=0)
        loaded = storage.load_results_page(offset=0)
        assert loaded == original

    def test_save_and_load_results_page_different_offsets(self, tmp_path):
        """Save pages at offset 0 and 100, load both, verify correct content."""
        storage = HtmlStorage(tmp_path)
        html_0 = "<html><body>Page at offset 0</body></html>"
        html_100 = "<html><body>Page at offset 100</body></html>"

        storage.save_results_page(html_0, offset=0)
        storage.save_results_page(html_100, offset=100)

        assert storage.load_results_page(offset=0) == html_0
        assert storage.load_results_page(offset=100) == html_100


class TestResultsPageExists:
    """Tests for the results_page_exists() check."""

    def test_results_page_exists_true(self, tmp_path):
        """After save, results_page_exists returns True."""
        storage = HtmlStorage(tmp_path)
        storage.save_results_page("<html></html>", offset=0)
        assert storage.results_page_exists(offset=0) is True

    def test_results_page_exists_false(self, tmp_path):
        """Before save, results_page_exists returns False."""
        storage = HtmlStorage(tmp_path)
        assert storage.results_page_exists(offset=0) is False


class TestResultsPageErrors:
    """Tests for error handling in results page methods."""

    def test_load_results_page_missing_raises(self, tmp_path):
        """Load non-existent offset raises FileNotFoundError."""
        storage = HtmlStorage(tmp_path)
        with pytest.raises(FileNotFoundError, match="No saved results page"):
            storage.load_results_page(offset=9999)


class TestResultsPagePathStructure:
    """Tests for correct filesystem path layout."""

    def test_results_page_path_structure(self, tmp_path):
        """Saved file is at base_dir/results/offset-{N}.html.gz."""
        storage = HtmlStorage(tmp_path)
        path = storage.save_results_page("<html></html>", offset=200)
        expected = tmp_path / "results" / "offset-200.html.gz"
        assert path == expected
        assert expected.exists()


class TestResultsPageGzip:
    """Tests for gzip compression of results pages."""

    def test_results_page_gzip_compressed(self, tmp_path):
        """Saved file starts with gzip magic bytes (0x1f, 0x8b)."""
        storage = HtmlStorage(tmp_path)
        path = storage.save_results_page("<html>test</html>", offset=0)
        raw_bytes = path.read_bytes()
        assert raw_bytes[0] == 0x1F
        assert raw_bytes[1] == 0x8B
