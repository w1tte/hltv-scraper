"""CLI entry point for the HLTV scraper.

Provides ``main()`` as the sync entry point for the ``hltv-scraper``
console script, and ``async_main(args)`` which sets up logging,
initializes all components, runs the pipeline, and prints an
end-of-run summary.

Usage::

    hltv-scraper                     # incremental scrape, offsets 0-9900
    hltv-scraper --end-offset 300    # small test run
    hltv-scraper --full              # full re-discovery (no early stop)
    hltv-scraper --force-rescrape    # re-process completed matches
"""

import argparse
import asyncio
import logging
import time

from scraper.config import ScraperConfig
from scraper.db import Database
from scraper.discovery_repository import DiscoveryRepository
from scraper.http_client import HLTVClient
from scraper.logging_config import setup_logging
from scraper.pipeline import ShutdownHandler, run_pipeline
from scraper.repository import MatchRepository
from scraper.storage import HtmlStorage

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the hltv-scraper CLI."""
    parser = argparse.ArgumentParser(
        prog="hltv-scraper",
        description="Scrape CS2 match data from HLTV.org",
    )
    parser.add_argument(
        "--start-offset",
        type=int,
        default=0,
        help="Start offset for results pagination (default: 0)",
    )
    parser.add_argument(
        "--end-offset",
        type=int,
        default=9900,
        help="End offset for results pagination (default: 9900)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Full scrape -- re-discover all matches in range (disables incremental early termination)",
    )
    parser.add_argument(
        "--force-rescrape",
        action="store_true",
        help="Re-process already-complete matches (resets scraped -> pending)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data",
        help="Data directory for DB, HTML archive, and logs (default: data)",
    )
    return parser


def _format_results(results: dict, wall_time: float, log_file: str) -> str:
    """Format end-of-run results into a human-readable summary string."""
    discovery = results.get("discovery", {})
    overview = results.get("overview", {})
    map_stats = results.get("map_stats", {})
    perf_economy = results.get("perf_economy", {})

    lines = [
        "=" * 60,
        "Pipeline complete",
        "-" * 60,
        "Discovery:   {} matches found ({} new)".format(
            discovery.get("matches_found", 0),
            discovery.get("new_matches", 0),
        ),
        "Overview:    {} parsed, {} failed".format(
            overview.get("parsed", 0),
            overview.get("failed", 0),
        ),
        "Map Stats:   {} parsed, {} failed".format(
            map_stats.get("parsed", 0),
            map_stats.get("failed", 0),
        ),
        "Perf/Econ:   {} parsed, {} failed".format(
            perf_economy.get("parsed", 0),
            perf_economy.get("failed", 0),
        ),
        "-" * 60,
        f"Wall time:   {wall_time:.0f}s",
        f"Log file:    {log_file}",
    ]

    if results.get("halted"):
        lines.append(f"Halted:      {results.get('halt_reason', 'unknown')}")

    lines.append("=" * 60)
    return "\n".join(lines)


async def async_main(args: argparse.Namespace) -> None:
    """Async entry point: set up components, run pipeline, print summary."""
    # 1. Logging
    log_file = setup_logging(data_dir=args.data_dir)

    mode = "full" if args.full else "incremental"
    logger.info(
        "Starting hltv-scraper: offsets %d-%d, mode=%s, data_dir=%s, log=%s",
        args.start_offset, args.end_offset, mode, args.data_dir, log_file,
    )

    # 2. Config
    config = ScraperConfig(
        data_dir=args.data_dir,
        db_path=f"{args.data_dir}/hltv.db",
        start_offset=args.start_offset,
        max_offset=args.end_offset,
    )

    # 3. Shutdown handler
    shutdown = ShutdownHandler()
    shutdown.install()

    # 4. Database
    db = Database(config.db_path)
    db.initialize()

    # 5. Repositories and storage
    match_repo = MatchRepository(db.conn)
    discovery_repo = DiscoveryRepository(db.conn)
    storage = HtmlStorage(config.data_dir)

    results = {}
    start_time = time.monotonic()

    try:
        async with HLTVClient(config) as client:
            results = await run_pipeline(
                client=client,
                match_repo=match_repo,
                discovery_repo=discovery_repo,
                storage=storage,
                config=config,
                shutdown=shutdown,
                incremental=not args.full,
                force_rescrape=args.force_rescrape,
            )
    finally:
        wall_time = time.monotonic() - start_time
        summary_text = _format_results(results, wall_time, str(log_file))

        # Print to console and log file
        logger.info("\n%s", summary_text)

        db.close()
        shutdown.restore()
        logging.shutdown()


def main() -> None:
    """Sync entry point for the hltv-scraper console script."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        pass  # Already handled by ShutdownHandler


if __name__ == "__main__":
    main()
