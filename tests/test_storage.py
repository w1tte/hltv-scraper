"""Unit tests for the HtmlStorage filesystem layer."""

import gzip

import pytest

from scraper.storage import HtmlStorage


class TestSaveAndLoad:
    """Tests for round-trip save/load of HTML content."""

    def test_save_and_load_overview(self, tmp_path):
        """Save overview HTML, load it back, assert identical."""
        storage = HtmlStorage(tmp_path)
        original = "<html><body>Match overview</body></html>"
        storage.save(original, match_id=12345, page_type="overview")
        loaded = storage.load(match_id=12345, page_type="overview")
        assert loaded == original

    def test_save_and_load_map_stats(self, tmp_path):
        """Save map_stats with mapstatsid, load back, assert identical."""
        storage = HtmlStorage(tmp_path)
        original = "<html><body>Map stats</body></html>"
        storage.save(original, match_id=12345, page_type="map_stats", mapstatsid=67890)
        loaded = storage.load(match_id=12345, page_type="map_stats", mapstatsid=67890)
        assert loaded == original

    def test_save_and_load_map_performance(self, tmp_path):
        """Save map_performance with mapstatsid, load back, assert identical."""
        storage = HtmlStorage(tmp_path)
        original = "<html><body>Performance data</body></html>"
        storage.save(
            original, match_id=12345, page_type="map_performance", mapstatsid=11111
        )
        loaded = storage.load(
            match_id=12345, page_type="map_performance", mapstatsid=11111
        )
        assert loaded == original

    def test_save_and_load_map_economy(self, tmp_path):
        """Save map_economy with mapstatsid, load back, assert identical."""
        storage = HtmlStorage(tmp_path)
        original = "<html><body>Economy data</body></html>"
        storage.save(
            original, match_id=12345, page_type="map_economy", mapstatsid=22222
        )
        loaded = storage.load(
            match_id=12345, page_type="map_economy", mapstatsid=22222
        )
        assert loaded == original


class TestExists:
    """Tests for the exists() check."""

    def test_exists_true(self, tmp_path):
        """After save, exists() returns True."""
        storage = HtmlStorage(tmp_path)
        storage.save("<html></html>", match_id=1, page_type="overview")
        assert storage.exists(match_id=1, page_type="overview") is True

    def test_exists_false(self, tmp_path):
        """Before save, exists() returns False."""
        storage = HtmlStorage(tmp_path)
        assert storage.exists(match_id=1, page_type="overview") is False


class TestErrorHandling:
    """Tests for error cases and validation."""

    def test_load_nonexistent_raises(self, tmp_path):
        """load() for missing file raises FileNotFoundError."""
        storage = HtmlStorage(tmp_path)
        with pytest.raises(FileNotFoundError, match="No saved HTML"):
            storage.load(match_id=99999, page_type="overview")

    def test_invalid_page_type_raises(self, tmp_path):
        """save() with page_type='invalid' raises ValueError."""
        storage = HtmlStorage(tmp_path)
        with pytest.raises(ValueError, match="Unknown page_type"):
            storage.save("<html></html>", match_id=1, page_type="invalid")

    def test_map_type_without_mapstatsid_raises(self, tmp_path):
        """save() with page_type='map_stats' and mapstatsid=None raises ValueError."""
        storage = HtmlStorage(tmp_path)
        with pytest.raises(ValueError, match="requires a mapstatsid"):
            storage.save("<html></html>", match_id=1, page_type="map_stats")

    def test_load_invalid_page_type_raises(self, tmp_path):
        """load() with invalid page_type raises ValueError."""
        storage = HtmlStorage(tmp_path)
        with pytest.raises(ValueError, match="Unknown page_type"):
            storage.load(match_id=1, page_type="nonexistent")

    def test_exists_invalid_page_type_raises(self, tmp_path):
        """exists() with invalid page_type raises ValueError."""
        storage = HtmlStorage(tmp_path)
        with pytest.raises(ValueError, match="Unknown page_type"):
            storage.exists(match_id=1, page_type="nonexistent")


class TestListMatchFiles:
    """Tests for listing saved files for a match."""

    def test_list_match_files_empty(self, tmp_path):
        """list_match_files for non-existent match returns empty list."""
        storage = HtmlStorage(tmp_path)
        assert storage.list_match_files(match_id=99999) == []

    def test_list_match_files_multiple(self, tmp_path):
        """Save 3 files for same match, list returns 3 paths."""
        storage = HtmlStorage(tmp_path)
        storage.save("<html>1</html>", match_id=100, page_type="overview")
        storage.save(
            "<html>2</html>", match_id=100, page_type="map_stats", mapstatsid=200
        )
        storage.save(
            "<html>3</html>",
            match_id=100,
            page_type="map_performance",
            mapstatsid=200,
        )
        files = storage.list_match_files(match_id=100)
        assert len(files) == 3
        # All files should be .html.gz
        assert all(f.name.endswith(".html.gz") for f in files)


class TestGzipCompression:
    """Tests for gzip compression behavior."""

    def test_file_is_gzip_compressed(self, tmp_path):
        """Save HTML, read raw bytes, verify gzip magic bytes (0x1f, 0x8b)."""
        storage = HtmlStorage(tmp_path)
        path = storage.save("<html>test</html>", match_id=1, page_type="overview")
        raw_bytes = path.read_bytes()
        assert raw_bytes[0] == 0x1F
        assert raw_bytes[1] == 0x8B

    def test_file_is_smaller_than_original(self, tmp_path):
        """Gzip-compressed file should be smaller than a large repeated HTML string."""
        storage = HtmlStorage(tmp_path)
        # Repeated content compresses well
        html = "<div class='stat-row'>" * 1000
        path = storage.save(html, match_id=1, page_type="overview")
        assert path.stat().st_size < len(html.encode("utf-8"))


class TestContentIntegrity:
    """Tests for content fidelity across save/load cycles."""

    def test_unicode_roundtrip(self, tmp_path):
        """Save HTML with unicode characters (accents, CJK), load back, assert identical."""
        storage = HtmlStorage(tmp_path)
        html = "<html><body>Niko NiKo - s1mple's AWP - 中文测试 - umlauts: aou</body></html>"
        storage.save(html, match_id=1, page_type="overview")
        loaded = storage.load(match_id=1, page_type="overview")
        assert loaded == html

    def test_large_html_roundtrip(self, tmp_path):
        """Save ~200KB of HTML (realistic HLTV page size), load back, assert identical."""
        storage = HtmlStorage(tmp_path)
        # Build a realistic-sized HTML document
        rows = "".join(
            f'<tr><td class="stat">{i}</td><td>{i * 3.14:.2f}</td></tr>'
            for i in range(5000)
        )
        html = f"<html><body><table>{rows}</table></body></html>"
        assert len(html.encode("utf-8")) > 200_000  # verify size assumption
        storage.save(html, match_id=1, page_type="overview")
        loaded = storage.load(match_id=1, page_type="overview")
        assert loaded == html


class TestDirectoryStructure:
    """Tests for correct filesystem path layout."""

    def test_directory_structure(self, tmp_path):
        """Save overview for match 12345, verify path is base_dir/matches/12345/overview.html.gz."""
        storage = HtmlStorage(tmp_path)
        path = storage.save("<html></html>", match_id=12345, page_type="overview")
        expected = tmp_path / "matches" / "12345" / "overview.html.gz"
        assert path == expected
        assert expected.exists()

    def test_map_stats_path(self, tmp_path):
        """Save map_stats, verify filename includes mapstatsid."""
        storage = HtmlStorage(tmp_path)
        path = storage.save(
            "<html></html>", match_id=12345, page_type="map_stats", mapstatsid=67890
        )
        expected = tmp_path / "matches" / "12345" / "map-67890-stats.html.gz"
        assert path == expected
