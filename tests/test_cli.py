"""Tests for the CLI argument parsing (build_parser).

Tests that default values, individual flags, and combined flags all produce
the correct argparse.Namespace values.
"""

from scraper.cli import build_parser


class TestBuildParser:
    """Tests for CLI argument parsing."""

    def test_default_args(self):
        """Empty argv produces correct defaults."""
        args = build_parser().parse_args([])
        assert args.start_offset == 0
        assert args.end_offset == 9900
        assert args.full is False
        assert args.force_rescrape is False
        assert args.data_dir == "data"

    def test_custom_offsets(self):
        """--start-offset and --end-offset are parsed correctly."""
        args = build_parser().parse_args(["--start-offset", "100", "--end-offset", "500"])
        assert args.start_offset == 100
        assert args.end_offset == 500

    def test_full_flag(self):
        """--full flag sets full=True."""
        args = build_parser().parse_args(["--full"])
        assert args.full is True

    def test_force_rescrape_flag(self):
        """--force-rescrape flag sets force_rescrape=True."""
        args = build_parser().parse_args(["--force-rescrape"])
        assert args.force_rescrape is True

    def test_custom_data_dir(self):
        """--data-dir sets the data directory."""
        args = build_parser().parse_args(["--data-dir", "/tmp/scrape"])
        assert args.data_dir == "/tmp/scrape"

    def test_all_flags_combined(self):
        """All flags provided together produce correct values."""
        args = build_parser().parse_args([
            "--start-offset", "200",
            "--end-offset", "800",
            "--full",
            "--force-rescrape",
            "--data-dir", "/opt/data",
        ])
        assert args.start_offset == 200
        assert args.end_offset == 800
        assert args.full is True
        assert args.force_rescrape is True
        assert args.data_dir == "/opt/data"
